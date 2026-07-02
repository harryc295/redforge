"""Profile schema validation — catch a bad profile.json with a clear message
listing every problem, instead of a raw KeyError mid-scan."""

from . import converters as converters_mod

REQUIRED_TOP = ("canary", "strategies")
KNOWN_STRATEGIES = ("single_shot", "pair", "tap", "crescendo")
KNOWN_PROVIDER_KINDS = ("mock", "openai", "anthropic")
KNOWN_SEVERITIES = ("low", "medium", "high", "critical")


def _check_provider_spec(role: str, spec) -> list[str]:
    errors = []
    if not isinstance(spec, dict):
        return [f"{role}: must be an object, got {type(spec).__name__}"]
    kind = spec.get("kind", "mock")
    if kind not in KNOWN_PROVIDER_KINDS:
        errors.append(f"{role}.kind: unknown provider {kind!r} (known: {KNOWN_PROVIDER_KINDS})")
    if kind == "openai" and "model" not in spec:
        errors.append(f"{role}: kind 'openai' requires a 'model'")
    return errors


def validate(profile: dict) -> list[str]:
    """Returns a list of problems; empty list means the profile is valid."""
    errors = []

    for key in REQUIRED_TOP:
        if key not in profile:
            errors.append(f"missing required key: {key!r}")

    for strat in profile.get("strategies", []):
        if strat not in KNOWN_STRATEGIES:
            errors.append(f"strategies: unknown strategy {strat!r} (known: {KNOWN_STRATEGIES})")

    if profile.get("fail_on") not in (None, *KNOWN_SEVERITIES):
        errors.append(f"fail_on: unknown severity {profile['fail_on']!r} "
                      f"(known: {KNOWN_SEVERITIES})")

    for role in ("attacker", "target", "judge"):
        if role in profile:
            errors += _check_provider_spec(role, profile[role])

    for name in profile.get("converters", []):
        if name not in converters_mod.REGISTRY:
            errors.append(f"converters: unknown converter {name!r} "
                          f"(known: {sorted(converters_mod.REGISTRY)})")

    if profile.get("objectives_file") and profile.get("objectives"):
        errors.append("objectives_file and objectives are mutually exclusive "
                      "(objectives_file replaces the built-in objective set)")

    return errors
