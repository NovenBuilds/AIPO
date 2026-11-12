"""SQLite（单文件数据库）里的任务、来源进度和事件。"""

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

CST = timezone(timedelta(hours=8))

QUEUED = "等待"
RUNNING = "执行中"
WAITING = "等待用户"
DONE = "已完成"
FAILED = "失败"

PHASE_QUEUED = "已排队"
PHASE_INTERRUPTED = "中断待恢复"
PHASE_COLLECT = "取证"
PHASE_WAIT = "等待补充"
PHASE_DONE = "定稿"
PHASE_FAIL = "失败"


def now():
    return datetime.now(CST).isoformat(timespec="seconds")


class Store:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init()

    def _init(self):
        self._conn.executescript("""
        CREATE TABLE IF NOT EXISTS researches (
          id TEXT PRIMARY KEY,
          request_id TEXT,
          question TEXT NOT NULL,
          platforms_json TEXT NOT NULL,
          params_hash TEXT NOT NULL,
          status TEXT NOT NULL,
          phase TEXT NOT NULL,
          intent TEXT,
          plan_json TEXT,
          mode TEXT NOT NULL,
          error TEXT,
          archive_path TEXT,
          answer TEXT,
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_researches_request
          ON researches(request_id) WHERE request_id IS NOT NULL;
        CREATE TABLE IF NOT EXISTS source_runs (
          research_id TEXT NOT NULL,
          ordinal INTEGER NOT NULL,
          source TEXT NOT NULL,
          platforms_json TEXT NOT NULL,
          capabilities_json TEXT NOT NULL,
          status TEXT NOT NULL,
          reason TEXT,
          path TEXT,
          mode TEXT,
          version TEXT,
          read_depth TEXT,
          batch_path TEXT,
          attempts INTEGER NOT NULL DEFAULT 0,
          started_at TEXT,
          finished_at TEXT,
          PRIMARY KEY (research_id, ordinal)
        );
        CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          research_id TEXT NOT NULL,
          at TEXT NOT NULL,
          kind TEXT NOT NULL,
          detail TEXT NOT NULL
        );
        """)
        self._conn.commit()

    def recover_running(self):
        with self._lock:
            rows = list(self._conn.execute("SELECT id FROM researches WHERE status=?", (RUNNING,)))
            stamp = now()
            self._conn.execute(
                "UPDATE researches SET status=?, phase=?, updated_at=? WHERE status=?",
                (QUEUED, PHASE_INTERRUPTED, stamp, RUNNING),
            )
            for row in rows:
                self._conn.execute(
                    "INSERT INTO events(research_id, at, kind, detail) VALUES (?,?,?,?)",
                    (row["id"], stamp, "interrupted", "进程中断。已完成批次仍在归档目录，可按原任务编号恢复。"),
                )
            self._conn.commit()
            return len(rows)

    def find_request(self, request_id):
        with self._lock:
            row = self._conn.execute("SELECT * FROM researches WHERE request_id=?", (request_id,)).fetchone()
            return dict(row) if row else None

    def insert_research(self, research_id, request_id, question, platforms, params_hash, mode, intent):
        stamp = now()
        with self._lock:
            try:
                self._conn.execute(
                    """INSERT INTO researches
                    (id, request_id, question, platforms_json, params_hash, status, phase, intent, mode, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (research_id, request_id, question, json.dumps(platforms, ensure_ascii=False), params_hash,
                     QUEUED, PHASE_QUEUED, intent, mode, stamp, stamp),
                )
                self._conn.execute(
                    "INSERT INTO events(research_id, at, kind, detail) VALUES (?,?,?,?)",
                    (research_id, stamp, "created", "任务已创建，等待执行。"),
                )
                self._conn.commit()
                return {"created": True}
            except sqlite3.IntegrityError:
                self._conn.rollback()
                row = self._conn.execute("SELECT * FROM researches WHERE request_id=?", (request_id,)).fetchone()
                return dict(row) if row else None
        return None

    def get(self, research_id):
        with self._lock:
            row = self._conn.execute("SELECT * FROM researches WHERE id=?", (research_id,)).fetchone()
            return dict(row) if row else None

    def update(self, research_id, **fields):
        if not fields:
            return
        fields["updated_at"] = now()
        keys = list(fields)
        sql = "UPDATE researches SET " + ", ".join("%s=?" % key for key in keys) + " WHERE id=?"
        with self._lock:
            self._conn.execute(sql, [fields[key] for key in keys] + [research_id])
            self._conn.commit()

    def event(self, research_id, kind, detail):
        with self._lock:
            self._conn.execute(
                "INSERT INTO events(research_id, at, kind, detail) VALUES (?,?,?,?)",
                (research_id, now(), kind, detail),
            )
            self._conn.commit()

    def events(self, research_id, limit=30):
        with self._lock:
            rows = self._conn.execute(
                "SELECT at, kind, detail FROM events WHERE research_id=? ORDER BY id DESC LIMIT ?",
                (research_id, limit),
            ).fetchall()
            return [dict(row) for row in reversed(rows)]

    def claim(self, research_id):
        stamp = now()
        with self._lock:
            cur = self._conn.execute(
                "UPDATE researches SET status=?, phase=?, updated_at=? WHERE id=? AND status=? AND phase=?",
                (RUNNING, PHASE_COLLECT, stamp, research_id, QUEUED, PHASE_QUEUED),
            )
            if cur.rowcount:
                self._conn.execute(
                    "INSERT INTO events(research_id, at, kind, detail) VALUES (?,?,?,?)",
                    (research_id, stamp, "claimed", "开始执行未完成步骤。"),
                )
            self._conn.commit()
            return cur.rowcount == 1

    def requeue(self, research_id):
        self.update(research_id, status=QUEUED, phase=PHASE_QUEUED, error=None)

    def ensure_sources(self, research_id, jobs):
        with self._lock:
            for job in jobs:
                self._conn.execute(
                    """INSERT OR IGNORE INTO source_runs
                    (research_id, ordinal, source, platforms_json, capabilities_json, status, attempts)
                    VALUES (?,?,?,?,?,?,0)""",
                    (research_id, job["ordinal"], job["source"], json.dumps(job["platforms"], ensure_ascii=False),
                     json.dumps(job["capabilities"], ensure_ascii=False), "pending"),
                )
            self._conn.commit()

    def sources(self, research_id):
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM source_runs WHERE research_id=? ORDER BY ordinal",
                (research_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def save_source(self, research_id, ordinal, **fields):
        fields["finished_at"] = fields.get("finished_at") or now()
        keys = list(fields)
        sql = "UPDATE source_runs SET " + ", ".join("%s=?" % key for key in keys) + " WHERE research_id=? AND ordinal=?"
        with self._lock:
            self._conn.execute(sql, [fields[key] for key in keys] + [research_id, ordinal])
            self._conn.commit()

    def next_queued(self):
        with self._lock:
            row = self._conn.execute(
                "SELECT id FROM researches WHERE status=? AND phase=? ORDER BY created_at LIMIT 1",
                (QUEUED, PHASE_QUEUED),
            ).fetchone()
            return row["id"] if row else None
