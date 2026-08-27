"""Adapters from existing detector outputs to the normalized timeline."""
from __future__ import annotations

from typing import Any, Iterable

from core.observations import Observation


def death_events_to_observations(events: Iterable[dict[str, Any]], detector: str = "kda_death_adapter_v1") -> list[Observation]:
    result = []
    for index, event in enumerate(events):
        start = float(event.get("ts", 0.0) or 0.0)
        window = event.get("window") or (start, start)
        end = float(window[1] or start)
        result.append(Observation.create(obs_type="player_death", start_sec=start, end_sec=max(start, end), subject="player", value={"kda_before": event.get("kda_before"), "kda_after": event.get("kda_after"), "location": event.get("location")}, confidence=1.0 if event.get("kda_after") is not None else None, detector=detector, evidence_refs=[f"death_event:{index}"], status="observed"))
    return result


def audio_events_to_observations(events: Iterable[dict[str, Any]], detector: str = "audio_adapter_v1") -> list[Observation]:
    result = []
    for index, event in enumerate(events):
        start = float(event.get("ts", event.get("start_sec", 0.0)) or 0.0)
        end = float(event.get("end_sec", start) or start)
        category = event.get("category")
        event_type = "objective_audio" if category == "objective" else "combat_audio" if category == "combat" or event.get("event") in {"combat", "kill", "death"} else "audio_event"
        result.append(Observation.create(obs_type=event_type, start_sec=start, end_sec=max(start, end), subject="match", value=dict(event), confidence=event.get("confidence"), detector=detector, evidence_refs=[f"audio_event:{index}"], status="observed"))
    return result


def corpus_fixture_to_observations(rows: Iterable[dict[str, Any]]) -> list[Observation]:
    """Consume corpus predictions/windows without importing corpus ownership."""
    return [Observation.from_dict(row) for row in rows]
