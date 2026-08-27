"""Shared production detector stage contract and cache identity."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Protocol

from core.observations import Observation, sort_observations, stable_observation_id

STAGE_SCHEMA_VERSION = "detector-stage-v1"


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def content_hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


@dataclass(frozen=True)
class DetectorContext:
    source_id: str
    media_hash: str | None = None
    duration_sec: float | None = None
    windows: tuple[tuple[float, float], ...] = ()
    observations: tuple[Observation, ...] = ()
    config: dict[str, Any] = field(default_factory=dict)
    model_version: str | None = None

    def windowed(self, start: float, end: float) -> "DetectorContext":
        return DetectorContext(self.source_id, self.media_hash, self.duration_sec, ((start, end),), tuple(o for o in self.observations if o.start_sec <= end and o.end_sec >= start), self.config, self.model_version)


@dataclass
class DetectorResult:
    detector: str
    detector_version: str
    observations: list[Observation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    runtime_ms: float = 0.0
    cache_key: str | None = None

    def ordered(self) -> "DetectorResult":
        self.observations = sort_observations(self.observations)
        return self

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": STAGE_SCHEMA_VERSION, "detector": self.detector, "detector_version": self.detector_version, "cache_key": self.cache_key, "observations": [o.to_dict() for o in self.ordered().observations], "warnings": self.warnings, "errors": self.errors, "runtime_ms": round(self.runtime_ms, 3)}


class Detector(Protocol):
    name: str
    version: str
    dependencies: tuple[str, ...]

    def run(self, context: DetectorContext) -> DetectorResult: ...


def _cache_input(value: Any) -> Any:
    if isinstance(value, Observation):
        return value.to_dict()
    if isinstance(value, (list, tuple)):
        return [_cache_input(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _cache_input(item) for key, item in value.items()}
    return value


def cache_key(detector: str, version: str, context: DetectorContext, relevant_inputs: Iterable[Any] = ()) -> str:
    payload = {"schema_version": STAGE_SCHEMA_VERSION, "source_id": context.source_id, "media_hash": context.media_hash, "detector": detector, "detector_version": version, "config": _cache_input(context.config), "model_version": context.model_version, "windows": context.windows, "observations": [_cache_input(o) for o in sort_observations(context.observations)], "upstream": _cache_input(list(relevant_inputs))}
    return content_hash(payload)


class DetectorCache:
    """Content-addressed JSON cache for one detector stage."""

    def __init__(self, directory: Path):
        self.directory = directory

    def path_for(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def load(self, key: str) -> DetectorResult | None:
        path = self.path_for(key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return DetectorResult(detector=data["detector"], detector_version=data["detector_version"], observations=[Observation.from_dict(x) for x in data.get("observations", [])], warnings=data.get("warnings", []), errors=data.get("errors", []), runtime_ms=data.get("runtime_ms", 0.0), cache_key=data.get("cache_key"))
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            return None

    def save(self, result: DetectorResult) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.path_for(result.cache_key or "uncached")
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)


def run_detector(detector: Detector, context: DetectorContext, relevant_inputs: Iterable[Any] = (), cache: DetectorCache | None = None, version_override: str | None = None) -> DetectorResult:
    effective_version = version_override or detector.version
    key = cache_key(detector.name, effective_version, context, relevant_inputs)
    if cache is not None:
        cached = cache.load(key)
        if cached is not None:
            return cached
    started = time.perf_counter()
    try:
        result = detector.run(context).ordered()
    except Exception as exc:  # one detector must not terminate unrelated stages
        result = DetectorResult(detector.name, effective_version, errors=[str(exc)])
    raw_observations = list(result.observations)
    id_map: dict[str, str] = {}
    for observation in raw_observations:
        id_map[observation.observation_id] = stable_observation_id(observation.detector, observation.type, observation.start_sec, observation.end_sec, observation.subject, observation.value, observation.confidence, observation.evidence_refs, observation.status, observation.schema_version, observation.dependencies, effective_version)
    versioned: list[Observation] = []
    for observation in raw_observations:
        refs = tuple(id_map.get(ref, ref) for ref in observation.evidence_refs)
        deps = tuple(id_map.get(dep, dep) for dep in observation.dependencies)
        observation_id = stable_observation_id(observation.detector, observation.type, observation.start_sec, observation.end_sec, observation.subject, observation.value, observation.confidence, refs, observation.status, observation.schema_version, deps, effective_version)
        versioned.append(Observation(observation_id, observation.type, observation.start_sec, observation.end_sec, observation.subject, observation.value, observation.confidence, observation.detector, effective_version, refs, observation.status, observation.schema_version, deps))
    result.observations = versioned
    result.detector_version = effective_version
    result.cache_key = key
    result.runtime_ms = (time.perf_counter() - started) * 1000
    if cache is not None:
        cache.save(result)
    return result
