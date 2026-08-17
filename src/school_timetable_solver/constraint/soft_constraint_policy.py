from __future__ import annotations

SOFT_CONSTRAINT_PRIORITY_POLICY: dict[str, int] = {
    "S12": 100,
    "S11": 90,
    "S13": 80,
    "S14": 80,
    "S15": 70,
    "S18": 60,
    "S10": 60,
    "S23": 50,
    "S17": 40,
    "S22": 40,
    "S21": 30,
    "S16": 20,
    "S19": 10,
    "S20": 10,
}


def soft_constraint_priority(rule_id: str) -> int:
    """Return the single authoritative optimization priority for one Soft Constraint."""
    try:
        return SOFT_CONSTRAINT_PRIORITY_POLICY[rule_id]
    except KeyError as exc:
        raise ValueError(f"Soft Constraint priority is not registered: {rule_id}") from exc
