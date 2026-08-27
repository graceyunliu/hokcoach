"""Production detector workstreams #4–9.

These detectors consume atomic observations from the existing media-specific
extractors and emit only evidence-backed, versioned observations. They do not
consume corpus labels, reviewer speech, captions, or seed metadata.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from core.detector_stage import DetectorContext, DetectorResult
from core.observations import Observation


def _selected(context: DetectorContext, types: set[str]) -> list[Observation]:
    selected = [o for o in context.observations if o.type in types]
    if context.config.get("candidate_window_only") and context.windows:
        selected = [o for o in selected if any(o.start_sec <= end and o.end_sec >= start for start, end in context.windows)]
    return sorted(selected, key=lambda o: (o.start_sec, o.end_sec, o.observation_id))


def _obs(detector: str, kind: str, start: float, end: float, value: Any, *, subject: str = "match", confidence: float | None = 0.0, refs: Iterable[str] = (), status: str = "observed", deps: Iterable[str] = ()) -> Observation:
    return Observation.create(obs_type=kind, start_sec=max(0.0, start), end_sec=max(start, end), subject=subject, value=value, confidence=confidence, detector=detector, evidence_refs=refs, status=status, dependencies=deps)


class ObjectiveTowerFusionDetector:
    name = "objective_tower_fusion"
    version = "objective-tower-v1"
    dependencies = ("audio", "minimap", "hud")

    def run(self, context: DetectorContext) -> DetectorResult:
        out: list[Observation] = []
        objectives = _selected(context, {"objective_visual", "objective_hud", "objective_audio", "objective_activity"})
        if not objectives:
            out.append(_obs(self.name, "objective_state", 0.0, context.duration_sec or 0.0, {"state": "unknown"}, subject="match", confidence=0.0, status="unknown"))
        for source in objectives:
            refs = [source.observation_id]
            if source.type == "objective_audio":
                out.append(_obs(self.name, "objective_activity", source.start_sec, source.end_sec, {"identity": source.value.get("identity") if isinstance(source.value, dict) else None, "basis": "audio_context_only"}, confidence=min(source.confidence or 0.0, .65), refs=refs, deps=refs))
            elif source.type in {"objective_visual", "objective_hud"}:
                value = dict(source.value) if isinstance(source.value, dict) else {"state": source.value}
                output_type = "objective_result" if source.status == "observed" else "objective_state"
                out.append(_obs(self.name, output_type, source.start_sec, source.end_sec, value, subject=str(value.get("identity", "unknown")), confidence=source.confidence if source.status == "observed" else 0.0, refs=refs, status=source.status, deps=refs))
        towers = _selected(context, {"tower_visual", "tower_hud"})
        by_subject: dict[str, list[Observation]] = defaultdict(list)
        for item in towers:
            by_subject[item.subject].append(item)
        for subject, series in by_subject.items():
            previous: Observation | None = None
            for item in series:
                state = item.value.get("state") if isinstance(item.value, dict) else item.value
                out.append(_obs(self.name, "tower_state", item.start_sec, item.end_sec, {"state": state}, subject=subject, confidence=item.confidence, refs=[item.observation_id], status=item.status, deps=[item.observation_id]))
                if previous is not None:
                    previous_state = previous.value.get("state") if isinstance(previous.value, dict) else previous.value
                    if previous_state != state and previous.status == "observed" and item.status == "observed":
                        refs = [previous.observation_id, item.observation_id]
                        out.append(_obs(self.name, "tower_state_transition", item.start_sec, item.end_sec, {"from": previous_state, "to": state}, subject=subject, confidence=item.confidence, refs=refs, deps=refs))
                previous = item
        return DetectorResult(self.name, self.version, out, warnings=["Audio never establishes objective identity or player responsibility."] if any(o.type == "objective_audio" for o in objectives) else []).ordered()


class LifecycleRecallDetector:
    name = "player_lifecycle_recall"
    version = "lifecycle-recall-v1"
    dependencies = ("death", "respawn_hud", "ui")

    def run(self, context: DetectorContext) -> DetectorResult:
        events = _selected(context, {"player_death", "respawn_timer", "recall_start", "recall_complete", "recall_cancelled", "lifecycle_state"})
        if not events:
            end = context.duration_sec or 0.0
            return DetectorResult(self.name, self.version, [_obs(self.name, "lifecycle_state", 0.0, end, {"state": "unknown"}, subject="player", confidence=0.0, status="unknown")])
        out: list[Observation] = []; last_state_by_subject: dict[str, str] = defaultdict(lambda: "unknown")
        for item in events:
            value = item.value if isinstance(item.value, dict) else {"state": item.value}
            state = value.get("state")
            if item.type == "player_death": state = "death_transition"
            elif item.type == "respawn_timer": state = "respawning" if item.status == "observed" else "unknown"
            elif item.type == "recall_start": state = "recalling"
            elif item.type == "recall_complete": state = "recall_completed"
            elif item.type == "recall_cancelled": state = "recall_cancelled"
            if state is None: state = "unreadable" if item.status == "unreadable" else "unknown"
            subject = item.subject or "player"
            if state == "alive" and last_state_by_subject[subject] == "dead": state = "respawn_transition"
            out.append(_obs(self.name, "lifecycle_state", item.start_sec, item.end_sec, {"state": state}, subject=subject, confidence=item.confidence, refs=[item.observation_id], status=item.status, deps=[item.observation_id]))
            last_state_by_subject[subject] = state
        return DetectorResult(self.name, self.version, out).ordered()


class EconomyItemDetector:
    name = "economy_items"
    version = "economy-items-v1"
    dependencies = ("scoreboard", "inventory", "shop")

    def run(self, context: DetectorContext) -> DetectorResult:
        snapshots = _selected(context, {"scoreboard_snapshot", "inventory_snapshot", "shop_snapshot"})
        if not snapshots:
            return DetectorResult(self.name, self.version, [_obs(self.name, "economy_snapshot", 0.0, context.duration_sec or 0.0, {"state": "unknown"}, subject="match", confidence=0.0, status="unknown")])
        out: list[Observation] = []; previous: dict[tuple[str, str], Observation] = {}
        for item in snapshots:
            value = dict(item.value) if isinstance(item.value, dict) else {"raw": item.value}
            out.append(_obs(self.name, "economy_snapshot" if item.type == "scoreboard_snapshot" else "item_snapshot", item.start_sec, item.end_sec, value, subject=item.subject, confidence=item.confidence, refs=[item.observation_id], status=item.status, deps=[item.observation_id]))
            current_items = value.get("items") if isinstance(value.get("items"), dict) else {}
            key = (item.subject or "match", item.type)
            prior = previous.get(key)
            if item.status == "observed" and prior is not None:
                prior_value = prior.value if isinstance(prior.value, dict) else {}
                prior_items = prior_value.get("items", {}) if isinstance(prior_value.get("items"), dict) else {}
                for slot in sorted(set(prior_items) | set(current_items)):
                    before, after = prior_items.get(slot), current_items.get(slot)
                    if before == after: continue
                    kind = "item_added" if before in (None, "empty") else "item_removed" if after in (None, "empty") else "item_replaced"
                    refs = [prior.observation_id, item.observation_id]
                    out.append(_obs(self.name, kind, item.start_sec, item.end_sec, {"slot": slot, "before": before, "after": after}, subject=item.subject, confidence=item.confidence, refs=refs, deps=refs))
            if item.status == "observed": previous[key] = item
        return DetectorResult(self.name, self.version, out).ordered()


class CoarseWaveDetector:
    name = "coarse_wave_state"
    version = "coarse-wave-v1"
    dependencies = ("minimap", "tower_state")

    def run(self, context: DetectorContext) -> DetectorResult:
        clusters = _selected(context, {"minion_cluster", "wave_visual"}); out: list[Observation] = []
        if not clusters:
            return DetectorResult(self.name, self.version, [_obs(self.name, "wave_state", 0.0, context.duration_sec or 0.0, {"state": "unknown"}, subject="match", confidence=0.0, status="unknown")])
        for item in clusters:
            if item.status != "observed":
                out.append(_obs(self.name, "wave_state", item.start_sec, item.end_sec, {"visibility": item.status}, subject=item.subject or "unknown_lane", confidence=0.0, refs=[item.observation_id], status=item.status, deps=[item.observation_id])); continue
            value = dict(item.value) if isinstance(item.value, dict) else {"presence": item.value}
            if "pressure" not in value and value.get("direction") in {"toward_enemy", "toward_friendly", "neutral"}:
                value["pressure"] = {"toward_enemy": "pushing_enemy", "toward_friendly": "pushing_friendly", "neutral": "neutral"}[value["direction"]]
            out.append(_obs(self.name, "wave_state", item.start_sec, item.end_sec, value, subject=item.subject or "unknown_lane", confidence=item.confidence, refs=[item.observation_id], deps=[item.observation_id]))
        return DetectorResult(self.name, self.version, out, warnings=["Wave state is not a tactical-intent or greed judgment."] if out else []).ordered()


class TeamfightDetector:
    name = "teamfight_episodes"
    version = "teamfight-v1"
    dependencies = ("minimap", "kda", "audio", "lifecycle")

    def run(self, context: DetectorContext) -> DetectorResult:
        signals = _selected(context, {"hero_cluster", "player_death", "combat_audio", "objective_activity", "visual_combat"})
        if not signals: return DetectorResult(self.name, self.version, [_obs(self.name, "teamfight_episode", 0.0, context.duration_sec or 0.0, {"state": "unknown"}, confidence=0.0, status="unknown")])
        groups: list[list[Observation]] = []
        for item in signals:
            if not groups or item.start_sec - groups[-1][-1].end_sec > float(context.config.get("episode_gap_sec", 8.0)): groups.append([item])
            else: groups[-1].append(item)
        out: list[Observation] = []
        for group in groups:
            types = {x.type for x in group}
            direct = any(x.type == "visual_combat" and isinstance(x.value, dict) and x.value.get("episode_confirmed") is True for x in group)
            if len(types) < 2 and not direct: continue
            refs = [x.observation_id for x in group]; start, end = min(x.start_sec for x in group), max(x.end_sec for x in group)
            episode = _obs(self.name, "teamfight_episode", start, end, {"signal_types": sorted(types), "uncertainty_sec": float(context.config.get("boundary_uncertainty_sec", 2.0))}, confidence=min(1.0, .45 + .15 * len(types)), refs=refs, deps=refs)
            out.append(episode)
            for pos in _selected(context, {"player_position"}):
                if pos.start_sec <= end and pos.end_sec >= start:
                    state = "present" if pos.status == "observed" else "unknown"
                    out.append(_obs(self.name, "teamfight_membership", max(start, pos.start_sec), min(end, pos.end_sec), {"membership": state}, subject=pos.subject, confidence=pos.confidence if state == "present" else 0.0, refs=[episode.observation_id, pos.observation_id], status=pos.status, deps=[episode.observation_id, pos.observation_id]))
        return DetectorResult(self.name, self.version, out).ordered()


class CooldownReadinessDetector:
    name = "high_value_cooldowns"
    version = "cooldowns-v1"
    dependencies = ("hud", "teamfight_episodes")

    def run(self, context: DetectorContext) -> DetectorResult:
        states = _selected(context, {"cooldown_ui", "cooldown_transition"}); out: list[Observation] = []; previous: dict[tuple[str, str], str] = {}
        if not states:
            return DetectorResult(self.name, self.version, [_obs(self.name, "cooldown_readiness", 0.0, context.duration_sec or 0.0, {"state": "unknown"}, subject="player", confidence=0.0, status="unknown")])
        for item in states:
            value = dict(item.value) if isinstance(item.value, dict) else {"state": item.value}
            skill = str(value.get("skill", item.subject or "unknown_skill")); state = value.get("state", "unknown")
            out.append(_obs(self.name, "cooldown_readiness", item.start_sec, item.end_sec, {"skill": skill, "state": state}, subject=item.subject or "player", confidence=item.confidence if item.status == "observed" else 0.0, refs=[item.observation_id], status=item.status, deps=[item.observation_id]))
            key = (item.subject, skill)
            if key in previous and previous[key] != state:
                transition = "became_ready" if state == "ready" else "used_transition" if state == "on_cooldown" else "unknown"
                out.append(_obs(self.name, "cooldown_transition", item.start_sec, item.end_sec, {"skill": skill, "transition": transition, "from": previous[key], "to": state}, subject=item.subject or "player", confidence=item.confidence, refs=[item.observation_id], deps=[item.observation_id]))
            previous[key] = state
        return DetectorResult(self.name, self.version, out).ordered()


PRODUCTION_DETECTORS = {d.name: d() for d in (ObjectiveTowerFusionDetector, LifecycleRecallDetector, EconomyItemDetector, CoarseWaveDetector, TeamfightDetector, CooldownReadinessDetector)}
