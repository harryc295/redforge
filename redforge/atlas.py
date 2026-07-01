"""MITRE ATLAS mapping.

ATLAS (Adversarial Threat Landscape for AI Systems) is the framework AI red
teams and buyers reference. Every objective carries an ATLAS technique id so
findings speak the language an enterprise already uses. IDs and names follow
https://atlas.mitre.org/ ; extend the catalog as you add objectives.
"""

CATALOG = {
    "AML.T0051": {"name": "LLM Prompt Injection", "tactic": "Initial Access / Execution"},
    "AML.T0054": {"name": "LLM Jailbreak", "tactic": "Defense Evasion / Privilege Escalation"},
    "AML.T0056": {"name": "LLM Meta Prompt Extraction", "tactic": "Discovery"},
    "AML.T0057": {"name": "LLM Data Leakage", "tactic": "Exfiltration"},
}

BASE = "https://atlas.mitre.org/techniques/"


def describe(technique_id: str) -> dict:
    info = CATALOG.get(technique_id, {"name": "Unknown", "tactic": "Unmapped"})
    return {"id": technique_id, "url": BASE + technique_id, **info}


def is_known(technique_id: str) -> bool:
    return technique_id in CATALOG
