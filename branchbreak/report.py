"""Scan reports in three shapes: JSON (for CI), Markdown (for the repo), and a
self-contained HTML report (for a human)."""

import html
import json
from collections import defaultdict

from . import atlas


def _asr_by_strategy(results) -> dict:
    # Skipped runs (query budget exhausted) were never actually tested and
    # would silently deflate the ASR if counted as a denominator miss.
    total, hits = defaultdict(int), defaultdict(int)
    for r in results:
        if r.skipped:
            continue
        total[r.strategy] += 1
        hits[r.strategy] += int(r.success)
    return {s: {"success": hits[s], "total": total[s], "asr": hits[s] / total[s]}
            for s in total}


def to_json(summary) -> str:
    asr = _asr_by_strategy(summary["results"])
    return json.dumps({
        "target": summary["target"],
        "risk_score": summary["risk"],
        "passed": summary["passed"],
        "fail_on": summary["fail_on"],
        "asr_by_strategy": asr,
        "findings": [{
            "objective": f.objective, "severity": f.severity, "category": f.category,
            "atlas": atlas.describe(f.atlas), "strategy": f.strategy, "queries": f.queries,
        } for f in summary["findings"]],
        "runs": [{
            "objective": r.objective, "strategy": r.strategy, "success": r.success,
            "queries": r.queries, "pruned": r.pruned,
            "best_score": r.best.score if r.best else 0,
        } for r in summary["results"]],
    }, indent=2)


def to_markdown(summary) -> str:
    asr = _asr_by_strategy(summary["results"])
    L = [f"# branchbreak scan — {summary['target']}", "",
         f"**Risk score:** {summary['risk']}/100  |  "
         f"**Gate:** {'PASS' if summary['passed'] else 'FAIL'} (fail-on: {summary['fail_on']})", "",
         "## Attack success rate by strategy", "",
         "| strategy | success / total | ASR |", "|---|---|---|"]
    for s in ("single_shot", "pair", "tap"):
        if s in asr:
            a = asr[s]
            L.append(f"| {s} | {a['success']}/{a['total']} | {a['asr']:.0%} |")
    L += ["", "## Findings", ""]
    if not summary["findings"]:
        L.append("No objectives were broken.")
    else:
        L.append("| objective | severity | ATLAS | broken by | queries |")
        L.append("|---|---|---|---|---|")
        for f in summary["findings"]:
            t = atlas.describe(f.atlas)
            L.append(f"| {f.objective} | {f.severity} | [{t['id']}]({t['url']}) {t['name']} "
                     f"| {f.strategy} | {f.queries} |")
    return "\n".join(L) + "\n"


_CSS = """
body{font-family:system-ui,sans-serif;background:#0d1117;color:#e6edf3;margin:0;padding:2rem;max-width:1000px}
h1{font-size:1.5rem}h2{font-size:1.1rem;margin-top:2rem;border-bottom:1px solid #30363d;padding-bottom:.3rem}
.tiles{display:flex;gap:1rem;flex-wrap:wrap;margin:1rem 0}
.tile{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:1rem 1.3rem;min-width:130px}
.tile .n{font-size:1.8rem;font-weight:700}.tile .l{color:#8b949e;font-size:.8rem}
table{border-collapse:collapse;width:100%;margin-top:.6rem}
th,td{border:1px solid #30363d;padding:.45rem .6rem;text-align:left;font-size:.9rem;vertical-align:top}
th{background:#161b22}
.pass{color:#3fb950}.fail{color:#f85149}
.sev-high,.sev-critical{color:#f85149;font-weight:600}.sev-medium{color:#d29922}.sev-low{color:#8b949e}
details{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:.6rem 1rem;margin:.5rem 0}
pre{white-space:pre-wrap;background:#0d1117;padding:.6rem;border-radius:6px;font-size:.82rem;overflow-x:auto}
a{color:#58a6ff}
"""


def to_html(summary) -> str:
    e = html.escape
    asr = _asr_by_strategy(summary["results"])
    gate = ("<span class='pass'>PASS</span>" if summary["passed"]
            else "<span class='fail'>FAIL</span>")

    tiles = [("Risk score", f"{summary['risk']}/100"),
             ("Findings", str(len(summary["findings"]))),
             ("Objectives", str(len({r.objective for r in summary['results']}))),
             ("Gate", gate)]
    tile_html = "".join(f"<div class='tile'><div class='n'>{v}</div>"
                        f"<div class='l'>{k}</div></div>" for k, v in tiles)

    rows = ""
    for s in ("single_shot", "pair", "tap"):
        if s in asr:
            a = asr[s]
            rows += (f"<tr><td>{s}</td><td>{a['success']}/{a['total']}</td>"
                     f"<td>{a['asr']:.0%}</td></tr>")

    finds = ""
    for f in summary["findings"]:
        t = atlas.describe(f.atlas)
        finds += (
            f"<details><summary><span class='sev-{f.severity}'>{e(f.severity.upper())}</span> "
            f"&mdash; {e(f.objective)} &middot; broken by <b>{e(f.strategy)}</b> "
            f"in {f.queries} queries &middot; "
            f"<a href='{t['url']}'>{t['id']} {e(t['name'])}</a></summary>"
            f"<p><b>Winning attack prompt</b></p><pre>{e(f.prompt)}</pre>"
            f"<p><b>Target response</b></p><pre>{e(f.response)}</pre></details>")
    if not finds:
        finds = "<p>No objectives were broken.</p>"

    return (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>branchbreak — {e(summary['target'])}</title><style>{_CSS}</style></head><body>"
            f"<h1>branchbreak scan &middot; {e(summary['target'])}</h1>"
            f"<div class='tiles'>{tile_html}</div>"
            f"<p>Gate {gate} at fail-on <b>{e(summary['fail_on'])}</b>. "
            f"Ground-truth success is decided by each objective's oracle; the judge only ranks.</p>"
            f"<h2>Attack success rate by strategy</h2>"
            f"<table><tr><th>strategy</th><th>success / total</th><th>ASR</th></tr>{rows}</table>"
            f"<h2>Findings</h2>{finds}</body></html>")
