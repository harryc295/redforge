"""Prompt converters — transform an attack prompt before it reaches the
target, the way PyRIT's Converter classes do. Tests whether an encoding or
obfuscation evades a keyword-based guardrail that the plain-text prompt
would otherwise trip. The attacker's own reasoning/history always sees the
original, un-converted prompt; only the call to the target is transformed —
converters are a delivery-layer transform, not something the attacker itself
is aware of, matching how PyRIT wires them in.
"""

import base64
import codecs


def _base64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def _rot13(text: str) -> str:
    return codecs.encode(text, "rot_13")


def _leetspeak(text: str) -> str:
    table = str.maketrans({"a": "4", "e": "3", "i": "1", "o": "0", "s": "5"})
    return text.translate(table)


REGISTRY = {"base64": _base64, "rot13": _rot13, "leetspeak": _leetspeak}


def apply(prompt: str, names: list[str] | None) -> str:
    """Apply converters in the given order. Raises on an unknown name —
    a typo'd converter in a profile should fail the scan, not silently
    apply nothing while looking like it worked."""
    for name in names or []:
        if name not in REGISTRY:
            raise ValueError(f"unknown converter: {name!r} (known: {sorted(REGISTRY)})")
        prompt = REGISTRY[name](prompt)
    return prompt
