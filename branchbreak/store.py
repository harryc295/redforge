"""SQLite scan history. Every scan, its per-strategy runs, and its findings.

ponytail: SQLite, not a service — a red-team scanner's history is a local
artifact, and this keeps trend queries ("is our ASR going up release over
release?") one SQL statement away with zero infrastructure.
"""

import csv
import os
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY, ts TEXT, target TEXT, profile TEXT,
    risk INTEGER, passed INTEGER
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY, scan_id INTEGER REFERENCES scans(id),
    objective TEXT, strategy TEXT, success INTEGER, queries INTEGER,
    pruned INTEGER, best_score INTEGER
);
CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY, scan_id INTEGER REFERENCES scans(id),
    objective TEXT, severity TEXT, atlas TEXT, strategy TEXT,
    prompt TEXT, response TEXT
);
"""


def connect(path="branchbreak.db"):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save_scan(conn, target, profile, results, findings, risk, passed) -> int:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cur = conn.execute(
        "INSERT INTO scans (ts, target, profile, risk, passed) VALUES (?,?,?,?,?)",
        (ts, target, profile, risk, int(passed)))
    scan_id = cur.lastrowid
    for r in results:
        conn.execute(
            "INSERT INTO runs (scan_id, objective, strategy, success, queries, pruned, best_score)"
            " VALUES (?,?,?,?,?,?,?)",
            (scan_id, r.objective, r.strategy, int(r.success), r.queries, r.pruned,
             r.best.score if r.best else 0))
    for f in findings:
        conn.execute(
            "INSERT INTO findings (scan_id, objective, severity, atlas, strategy, prompt, response)"
            " VALUES (?,?,?,?,?,?,?)",
            (scan_id, f.objective, f.severity, f.atlas, f.strategy, f.prompt, f.response))
    conn.commit()
    return scan_id


def scan_history(conn, limit: int = 20) -> list[sqlite3.Row]:
    """Most recent scans first — the release-over-release trend the README
    promises is one query away."""
    return conn.execute(
        "SELECT id, ts, target, profile, risk, passed FROM scans "
        "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()


def asr_trend(conn, limit: int = 20) -> list[dict]:
    """Per-scan attack success rate by strategy, most recent first — the
    numbers a trend dashboard or CI comment would actually want."""
    scans = conn.execute(
        "SELECT id, ts, target, risk FROM scans ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for s in scans:
        rows = conn.execute(
            "SELECT strategy, AVG(success) AS asr, COUNT(*) AS n FROM runs "
            "WHERE scan_id = ? GROUP BY strategy", (s["id"],)).fetchall()
        out.append({"scan_id": s["id"], "ts": s["ts"], "target": s["target"],
                    "risk": s["risk"],
                    "by_strategy": {r["strategy"]: {"asr": r["asr"], "n": r["n"]} for r in rows}})
    return out


def export_csv(conn, out_dir: str) -> list[str]:
    """Dump scans/runs/findings to CSV for compliance evidence packaging
    (SOC 2 / ISO 27001-style audit trail) — same pattern as fleetwatch's
    audit export, applied to scan history instead of policy events."""
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for table in ("scans", "runs", "findings"):
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        path = os.path.join(out_dir, f"{table}.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            if rows:
                w = csv.writer(f)
                w.writerow(rows[0].keys())
                w.writerows(tuple(r) for r in rows)
        written.append(path)
    return written
