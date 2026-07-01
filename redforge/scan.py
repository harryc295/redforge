"""Scan orchestration: profile in, findings + reports out."""

import json

from . import objectives as obj_mod
from . import scoring, search
from .providers import build_provider

STRATEGY_PARAMS = {
    "pair": lambda p: {"max_iters": p.get("max_iters", 8)},
    "tap": lambda p: {"depth": p.get("depth", 4), "branching": p.get("branching", 3),
                      "width": p.get("width", 3), "ontopic_min": p.get("ontopic_min", 3)},
    "single_shot": lambda p: {},
}


def load_profile(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _apply_override(profile: dict, provider: str | None, model: str | None):
    """--provider/--model rewrite all three roles to one backend (self-red-team)."""
    if not provider:
        return
    if provider == "ollama":
        spec = {"kind": "openai", "base_url": "http://localhost:11434/v1",
                "model": model or "qwen2.5:7b"}
    else:
        spec = {"kind": provider}
        if model:
            spec["model"] = model
    for role in ("attacker", "target", "judge"):
        profile[role] = {**profile.get(role, {}), **spec}


def run_scan(profile: dict, provider=None, model=None) -> dict:
    _apply_override(profile, provider, model)
    canary = profile.get("canary", "PELICAN-7731")
    objectives = obj_mod.by_name(profile.get("objectives"), canary)
    strategies = profile.get("strategies", ["single_shot", "pair", "tap"])
    params = profile.get("params", {})
    fail_on = profile.get("fail_on", "high")

    a_spec = profile.get("attacker", {"kind": "mock"})
    t_spec = profile.get("target", {"kind": "mock"})
    j_spec = profile.get("judge", {"kind": "mock"})

    results = []
    for obj in objectives:
        # Rebuild mocks per objective so the simulated target guards THIS canary.
        atk = build_provider({**a_spec, "secret": obj.canary}, "attacker")
        tgt = build_provider({**t_spec, "secret": obj.canary}, "target")
        jdg = build_provider({**j_spec, "secret": obj.canary}, "judge")
        for strat in strategies:
            kwargs = STRATEGY_PARAMS[strat](params)
            results.append(search.STRATEGIES[strat](obj, atk, tgt, jdg, **kwargs))

    findings = scoring.findings_from(results, objectives)
    risk = scoring.risk_score(findings)
    passed, exit_code = scoring.gate(findings, fail_on)

    return {"target": t_spec.get("model", t_spec.get("kind", "mock")),
            "results": results, "findings": findings, "risk": risk,
            "passed": passed, "exit_code": exit_code, "fail_on": fail_on,
            "objectives": objectives}
