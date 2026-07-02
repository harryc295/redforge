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

BASE = "https://atlas.mitre.org/"
# ponytail: MITRE's ATLAS site is a client-rendered SPA on GitHub Pages with
# no server-side fallback for deep links (they 404 on direct navigation, even
# their own robots.txt does), so every technique links to the root site
# instead of a per-technique URL that's currently guaranteed to 404.


def describe(technique_id: str) -> dict:
    info = CATALOG.get(technique_id, {"name": "Unknown", "tactic": "Unmapped"})
    return {"id": technique_id, "url": BASE, **info}


def is_known(technique_id: str) -> bool:
    return technique_id in CATALOG
