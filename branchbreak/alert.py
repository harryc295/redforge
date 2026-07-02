"""Webhook alerting on a failed gate — Slack-compatible payload shape, works
with any webhook that accepts {"text": "..."} (Slack, Mattermost, Discord via
a compatible adapter). Stdlib only, best-effort: a broken webhook shouldn't
crash a scan that otherwise succeeded, so failures here are caught and
printed, not raised.
"""

import json
import urllib.error
import urllib.request


def build_message(summary: dict) -> str:
    lines = [f"*branchbreak scan failed* — target `{summary['target']}` — "
            f"risk {summary['risk']}/100"]
    for f in summary["findings"]:
        lines.append(f"  • [{f.severity}] {f.objective} — broken by {f.strategy} "
                     f"({f.atlas})")
    return "\n".join(lines)


def send(webhook_url: str, summary: dict, timeout: int = 10) -> bool:
    """Returns True on a successful post, False on any failure (logged, not raised)."""
    payload = {"text": build_message(summary)}
    req = urllib.request.Request(
        webhook_url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"webhook alert failed (non-fatal): {e}")
        return False
