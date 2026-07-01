"""SQLite scan history. Every scan, its per-strategy runs, and its findings.

ponytail: SQLite, not a service — a red-team scanner's history is a local
artifact, and this keeps trend queries ("is our ASR going up release over
release?") one SQL statement away with zero infrastructure.
"""

import json
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


def connect(path="redforge.db"):
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
