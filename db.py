import json
import pathlib
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS cdrs(
  record_id  TEXT PRIMARY KEY,
  start_utc  TEXT NOT NULL,
  duration_s INTEGER NOT NULL DEFAULT 0,
  answered   INTEGER NOT NULL DEFAULT 0,
  raw        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cdrs_start ON cdrs(start_utc);

CREATE TABLE IF NOT EXISTS member_snapshots(
  snap_date TEXT NOT NULL,
  group_id  TEXT NOT NULL,
  person_id TEXT NOT NULL,
  name      TEXT,
  email     TEXT,
  PRIMARY KEY (snap_date, group_id, person_id)
);

CREATE TABLE IF NOT EXISTS reports(
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  month      TEXT NOT NULL,
  sent_at    TEXT NOT NULL,
  recipients TEXT NOT NULL,
  status     TEXT NOT NULL,
  detail     TEXT
);

CREATE TABLE IF NOT EXISTS email_recipients(
  email TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS kv(
  key   TEXT PRIMARY KEY,
  value TEXT
);
"""


def db_file(cfg):
    d = pathlib.Path(cfg.get("data_dir", "data"))
    d.mkdir(exist_ok=True)
    return d / "app.db"


def connect(cfg):
    conn = sqlite3.connect(db_file(cfg))
    conn.row_factory = sqlite3.Row
    return conn


def init(cfg):
    conn = connect(cfg)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def kv_get(conn, key, default=None):
    row = conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def kv_set(conn, key, value):
    conn.execute(
        "INSERT INTO kv(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))


def upsert_cdr(conn, record_id, start_utc, duration_s, answered, raw):
    conn.execute(
        "INSERT INTO cdrs(record_id,start_utc,duration_s,answered,raw) VALUES(?,?,?,?,?) "
        "ON CONFLICT(record_id) DO UPDATE SET duration_s=excluded.duration_s,"
        "answered=excluded.answered,start_utc=excluded.start_utc",
        (record_id, start_utc, duration_s, int(answered), raw))


def save_members(conn, snap_date, group_id, members):
    conn.execute("DELETE FROM member_snapshots WHERE snap_date=? AND group_id=?",
                 (snap_date, group_id))
    conn.executemany(
        "INSERT OR IGNORE INTO member_snapshots(snap_date,group_id,person_id,name,email) "
        "VALUES(?,?,?,?,?)",
        [(snap_date, group_id, m["person_id"], m.get("name"), m.get("email")) for m in members])


def members_at(conn, asof_date):
    row = conn.execute(
        "SELECT MAX(snap_date) AS d FROM member_snapshots WHERE snap_date<=?",
        (asof_date,)).fetchone()
    if not row or not row["d"]:
        return []
    return [dict(r) for r in conn.execute(
        "SELECT DISTINCT person_id,name,email FROM member_snapshots WHERE snap_date=? "
        "ORDER BY name", (row["d"],))]


def cdrs_in_window(conn, start_utc, end_utc):
    return [dict(r) for r in conn.execute(
        "SELECT raw FROM cdrs WHERE start_utc>=? AND start_utc<? AND answered=1 AND duration_s>0",
        (start_utc, end_utc))]


def add_report(conn, month, recipients, status, detail=""):
    conn.execute("INSERT INTO reports(month,sent_at,recipients,status,detail) VALUES(?,?,?,?,?)",
                 (month, utcnow_iso(), ", ".join(recipients), status, detail))


def list_reports(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM reports ORDER BY sent_at DESC")]


def get_report(conn, report_id):
    row = conn.execute("SELECT * FROM reports WHERE id=?", (report_id,)).fetchone()
    return dict(row) if row else None


def get_recipients(conn):
    return [r["email"] for r in
            conn.execute("SELECT email FROM email_recipients ORDER BY email")]


def set_recipients(conn, emails):
    conn.execute("DELETE FROM email_recipients")
    conn.executemany("INSERT OR IGNORE INTO email_recipients(email) VALUES(?)",
                     [(e.strip().lower(),) for e in emails if e.strip()])


def months_available(conn):
    rows = conn.execute("SELECT DISTINCT substr(start_utc,1,7) AS m FROM cdrs ORDER BY m DESC")
    return [r["m"] for r in rows]


def utcnow_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_utc_iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    s = s.strip().replace("Z", "").split(".")[0]
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        dt = datetime.fromisoformat(s.replace("+0000", "00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_json(raw):
    return json.loads(raw)
