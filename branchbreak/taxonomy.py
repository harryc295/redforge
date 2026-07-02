"""Pluggable objective loader — the mechanism, not the content.

The README and the safety-and-scope section both say "the engine is
objective-agnostic; for an authorized engagement, add objectives from a
standard harm taxonomy (HarmBench, AdvBench, JailbreakBench) instead of the
benign canaries shipped here." This module is what makes that literally
true: a JSON file of user-supplied objectives loads into the same Objective
shape objectives.py builds by hand.

This module does NOT ship HarmBench/AdvBench/JailbreakBench content — those
taxonomies contain real harmful-behavior descriptions, and publishing them
in a public portfolio repo isn't something to do casually. Bring your own
taxonomy file under an authorized engagement; this just loads it.
"""

import json
import re

from .objectives import Objective

ORACLE_KINDS = ("canary", "regex")


def _build_oracle(kind: str, value: str):
    if kind == "canary":
        needle = value.lower()
        return lambda response: needle in (response or "").lower()
    if kind == "regex":
        pattern = re.compile(value, re.IGNORECASE | re.DOTALL)
        return lambda response: bool(pattern.search(response or ""))
    raise ValueError(f"unknown oracle kind: {kind!r} (known: {ORACLE_KINDS})")


def load(path: str) -> list[Objective]:
    """Load objectives from a JSON file: a list of objects with name,
    category, severity, atlas, goal, target_system, oracle_kind, oracle_value.
    See profiles/custom-objectives.example.json for the schema."""
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)
    objectives = []
    for i, row in enumerate(rows):
        missing = [k for k in ("name", "category", "severity", "atlas", "goal",
                               "target_system", "oracle_kind", "oracle_value") if k not in row]
        if missing:
            raise ValueError(f"objective #{i} ({row.get('name', '?')}) missing: {missing}")
        objectives.append(Objective(
            name=row["name"], category=row["category"], severity=row["severity"],
            atlas=row["atlas"], canary=row["oracle_value"], goal=row["goal"],
            target_system=row["target_system"],
            oracle=_build_oracle(row["oracle_kind"], row["oracle_value"])))
    return objectives
