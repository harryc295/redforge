"""Scan orchestration: profile in, findings + reports out."""

import json
from concurrent.futures import ThreadPoolExecutor

from . import objectives as obj_mod
from . import scoring, search, taxonomy
from .providers import build_provider

STRATEGY_PARAMS = {
    "pair": lambda p: {"max_iters": p.get("max_iters", 8)},
    "tap": lambda p: {"depth": p.get("depth", 4), "branching": p.get("branching", 3),
                      "width": p.get("width", 3), "ontopic_min": p.get("ontopic_min", 3)},
    "single_shot": lambda p: {},
    "crescendo": lambda p: {"max_turns": p.get("max_turns", 6)},
}


def load_profile(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def apply_provider_override(profile: dict, provider: str | None, model: str | None):
    """--provider/--model rewrite all three roles to one backend (self-red-team).
    Public (and idempotent) so the CLI can apply it before validate() runs —
    otherwise a --provider anthropic override wouldn't be visible to the
    preflight API-key check, which only sees the profile file's own blocks."""
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


def _load_objectives(profile: dict, canary: str) -> list:
    if profile.get("objectives_file"):
        return taxonomy.load(profile["objectives_file"])
    return obj_mod.by_name(profile.get("objectives"), canary)


def _run_one(obj, strat, params, converter_names, a_spec, t_spec, j_spec):
    atk = build_provider({**a_spec, "secret": obj.canary}, "attacker")
    tgt = build_provider({**t_spec, "secret": obj.canary}, "target")
    jdg = build_provider({**j_spec, "secret": obj.canary}, "judge")
    kwargs = STRATEGY_PARAMS[strat](params)
    kwargs["converter_names"] = converter_names
    return search.STRATEGIES[strat](obj, atk, tgt, jdg, **kwargs)


def run_scan(profile: dict, provider=None, model=None,
             max_queries: int | None = None, parallel: int = 1) -> dict:
    apply_provider_override(profile, provider, model)
    canary = profile.get("canary", "PELICAN-7731")
    objectives = _load_objectives(profile, canary)
    strategies = profile.get("strategies", ["single_shot", "pair", "tap"])
    params = profile.get("params", {})
    fail_on = profile.get("fail_on", "high")
    converter_names = profile.get("converters")

    a_spec = profile.get("attacker", {"kind": "mock"})
    t_spec = profile.get("target", {"kind": "mock"})
    j_spec = profile.get("judge", {"kind": "mock"})

    jobs = [(obj, strat) for obj in objectives for strat in strategies]

    if max_queries is None:
        # No budget tracking needed: run everything, optionally in parallel.
        if parallel > 1:
            with ThreadPoolExecutor(max_workers=parallel) as ex:
                results = list(ex.map(
                    lambda job: _run_one(job[0], job[1], params, converter_names,
                                         a_spec, t_spec, j_spec),
                    jobs))
        else:
            results = [_run_one(obj, strat, params, converter_names, a_spec, t_spec, j_spec)
                      for obj, strat in jobs]
    else:
        # Budget tracking is inherently sequential: each job's cost is only
        # known after it runs, so parallel execution can't honor a running
        # total without over-spending past the cap mid-batch.
        results, spent = [], 0
        for obj, strat in jobs:
            if spent >= max_queries:
                results.append(search.Result(strat, obj.name, False, 0, None, [], 0,
                                             skipped=True))
                continue
            r = _run_one(obj, strat, params, converter_names, a_spec, t_spec, j_spec)
            spent += r.queries
            results.append(r)

    findings = scoring.findings_from(results, objectives)
    risk = scoring.risk_score(findings)
    passed, exit_code = scoring.gate(findings, fail_on)

    return {"target": t_spec.get("model", t_spec.get("kind", "mock")),
            "results": results, "findings": findings, "risk": risk,
            "passed": passed, "exit_code": exit_code, "fail_on": fail_on,
            "objectives": objectives}
