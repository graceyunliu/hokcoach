"""Safe presentation helpers for cooldown observations.

These messages never turn unknown or unreadable evidence into a positive claim.
"""
from __future__ import annotations

from typing import Iterable

from core.observations import Observation


def cooldown_message(observation: Observation) -> str:
    value = observation.value if isinstance(observation.value, dict) else {}
    if value.get("reason") in {"unsupported_source", "unsupported_layout"}:
        return "This replay layout is not yet supported"
    skill = str(value.get("skill", "Cooldown"))
    if observation.status != "observed":
        return "Cooldown state could not be read"
    state = str(value.get("state", "unknown"))
    labels = {
        ("ultimate", "ready"): "Ultimate appeared ready",
        ("ultimate", "on_cooldown"): "Ultimate appeared on cooldown",
        ("summoner_flash", "ready"): "Flash appeared ready",
        ("summoner_flash", "on_cooldown"): "Flash appeared on cooldown",
    }
    return labels.get((skill, state), f"{skill} appeared {state.replace('_', ' ')}")


def cooldown_messages(observations: Iterable[Observation]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for observation in observations:
        if observation.type != "cooldown_ui":
            continue
        messages.append(
            {
                "observation_id": observation.observation_id,
                "skill": str((observation.value or {}).get("skill", "unknown")) if isinstance(observation.value, dict) else "unknown",
                "status": observation.status,
                "message": cooldown_message(observation),
            }
        )
    return messages
