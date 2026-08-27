"""Compact match-wide evidence timeline shared by all replay detectors."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from core.observations import Observation, sort_observations


@dataclass
class EvidenceTimeline:
    observations: list[Observation] = field(default_factory=list)

    def add(self, observation: Observation, *, deduplicate: bool = True) -> Observation:
        if deduplicate:
            # Stable IDs include status, confidence, provenance, and dependency
            # identity. Never collapse independent detectors merely because
            # their value/time happen to match.
            for existing in self.observations:
                if existing.observation_id == observation.observation_id:
                    return existing
        self.observations.append(observation)
        self.observations = sort_observations(self.observations)
        return observation

    def extend(self, observations: Iterable[Observation], *, deduplicate: bool = True) -> None:
        for observation in observations:
            self.add(observation, deduplicate=deduplicate)

    def between(self, start_sec: float, end_sec: float, types: set[str] | None = None) -> list[Observation]:
        return [o for o in self.observations if o.start_sec <= end_sec and o.end_sec >= start_sec and (types is None or o.type in types)]

    def by_type(self, obs_type: str) -> list[Observation]:
        return [o for o in self.observations if o.type == obs_type]

    def to_jsonl(self) -> str:
        return "".join(o.to_json() + "\n" for o in sort_observations(self.observations))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_jsonl(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "EvidenceTimeline":
        timeline = cls()
        if not path.exists():
            return timeline
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                timeline.add(Observation.from_dict(json.loads(line)), deduplicate=False)
        timeline.observations = sort_observations(timeline.observations)
        return timeline

    def metrics(self) -> dict[str, int | float]:
        return {"observation_count": len(self.observations), "observed_count": sum(o.status == "observed" for o in self.observations), "unknown_count": sum(o.status == "unknown" for o in self.observations), "unreadable_count": sum(o.status == "unreadable" for o in self.observations), "detector_count": len({o.detector for o in self.observations})}
