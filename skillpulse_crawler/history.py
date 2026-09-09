import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  issue_number INTEGER,
  status TEXT,
  summary_json TEXT
);
CREATE TABLE IF NOT EXISTS seen_keys (
  key TEXT PRIMARY KEY,
  seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS errors (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  source_id TEXT,
  error TEXT
);
"""


class History:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.conn.close()

    def has_seen(self, section, source, source_id) -> bool:
        key = f"{section}|{source}|{source_id}"
        cur = self.conn.execute("SELECT 1 FROM seen_keys WHERE key=?", (key,))
        return cur.fetchone() is not None

    def record_seen(self, section, source, source_id):
        key = f"{section}|{source}|{source_id}"
        self.conn.execute(
            "INSERT OR IGNORE INTO seen_keys(key, seen_at) VALUES (?, ?)",
            (key, datetime.now(timezone.utc).isoformat())
        )
        self.conn.commit()

    def start_run(self, issue_number):
        cur = self.conn.execute(
            "INSERT INTO runs(started_at, issue_number, status) VALUES (?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(), issue_number, "running")
        )
        self.conn.commit()
        return cur.lastrowid

    def complete_run(self, run_id, summary):
        import json
        self.conn.execute(
            "UPDATE runs SET finished_at=?, status=?, summary_json=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), "success", json.dumps(summary), run_id)
        )
        self.conn.commit()

    def get_run(self, run_id):
        cur = self.conn.execute("SELECT * FROM runs WHERE id=?", (run_id,))
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0], "started_at": row[1], "finished_at": row[2],
            "issue_number": row[3], "status": row[4], "summary": row[5]
        }