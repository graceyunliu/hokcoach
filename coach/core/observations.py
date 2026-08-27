"""Versioned, detector-independent observation primitives."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

OBSERVATION_SCHEMA_VERSION = "observation-v1"
OBSERVED_STATUSES = {"observed", "unknown", "unreadable"}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def stable_observation_id(detector: str, obs_type: str, start_sec: float, end_sec: float, subject: str, value: Any, confidence: float | None = None, evidence_refs: Iterable[str] = (), status: str = "observed", schema_version: str = OBSERVATION_SCHEMA_VERSION, dependencies: Iterable[str] = (), detector_version: str | None = None) -> str:
    payload = {"schema_version": schema_version, "detector": detector, "detector_version": detector_version or detector, "type": obs_type, "start_sec": start_sec, "end_sec": end_sec, "subject": subject, "value": value, "confidence": confidence, "evidence_refs": sorted(set(evidence_refs)), "status": status, "dependencies": sorted(set(dependencies))}
    return f"obs_{hashlib.sha256(_canonical(payload)).hexdigest()[:20]}"


@dataclass(frozen=True)
class Observation:
    observation_id: str
    type: str
    start_sec: float
    end_sec: float
    subject: str
    value: Any
    confidence: float | None
    detector: str
    detector_version: str = ""
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    status: str = "observed"
    schema_version: str = OBSERVATION_SCHEMA_VERSION
    dependencies: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.observation_id or not self.type or not self.detector:
            raise ValueError("observation_id, type, and detector are required")
        if self.start_sec < 0 or self.end_sec < self.start_sec:
            raise ValueError("observation time range must be nonnegative and ordered")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if self.status not in OBSERVED_STATUSES:
            raise ValueError(f"invalid observation status: {self.status}")
        if self.status != "observed" and self.confidence not in (None, 0.0):
            raise ValueError("unknown/unreadable observations cannot carry positive confidence")

    @classmethod
    def create(cls, *, obs_type: str, start_sec: float, end_sec: float, subject: str, value: Any, confidence: float | None, detector: str, detector_version: str | None = None, evidence_refs: Iterable[str] = (), status: str = "observed", dependencies: Iterable[str] = ()) -> "Observation":
        refs = tuple(sorted(set(evidence_refs)))
        deps = tuple(sorted(set(dependencies)))
        effective_version = detector_version or detector
        oid = stable_observation_id(detector, obs_type, start_sec, end_sec, subject, value, confidence, refs, status, OBSERVATION_SCHEMA_VERSION, deps, effective_version)
        return cls(oid, obs_type, float(start_sec), float(end_sec), subject, value, confidence, detector, effective_version, refs, status, OBSERVATION_SCHEMA_VERSION, deps)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["evidence_refs"] = list(self.evidence_refs)
        result["dependencies"] = list(self.dependencies)
        return result

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Observation":
        return cls(observation_id=data["observation_id"], type=data["type"], start_sec=float(data["start_sec"]), end_sec=float(data["end_sec"]), subject=data["subject"], value=data.get("value"), confidence=data.get("confidence"), detector=data["detector"], detector_version=data.get("detector_version", data["detector"]), evidence_refs=tuple(data.get("evidence_refs", ())), status=data.get("status", "observed"), schema_version=data.get("schema_version", OBSERVATION_SCHEMA_VERSION), dependencies=tuple(data.get("dependencies", ())))


def sort_observations(observations: Iterable[Observation]) -> list[Observation]:
    return sorted(observations, key=lambda x: (x.start_sec, x.end_sec, x.type, x.subject, x.observation_id))
