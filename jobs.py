import csv
import email.encoders
import io
import json
import logging
import smtplib
import threading
import time
from datetime import datetime, timedelta, timezone
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from hashlib import sha1
from zoneinfo import ZoneInfo

import db
import webex

log = logging.getLogger(__name__)

OVERLAP_DAYS = 3          # rolling window: pull the last N days every night
MAX_BACKFILL_DAYS = 29    # cdr_feed hard limit is 30 days
CHUNK_HOURS = 12          # API accepts <=12h per request
PACE_START_SECONDS = 62   # cdr_feed allows 1 new request/minute


def local_tz(cfg):
    return ZoneInfo(cfg.get("org_timezone", "Asia/Muscat"))


def month_range_utc(month):
    y, m = int(month[:4]), int(month[5:7])
    tz = local_tz({})
    start = datetime(y, m, 1, tzinfo=tz)
    end = datetime(y + 1, 1, 1, tzinfo=tz) if m == 12 else datetime(y, m + 1, 1, tzinfo=tz)
    return db.to_utc_iso(start), db.to_utc_iso(end)


def previous_month(now=None):
    tz = local_tz({})
    now = now or datetime.now(tz)
    prev = datetime(now.year, now.month, 1, tzinfo=tz) - timedelta(days=1)
    return f"{prev.year:04d}-{prev.month:02d}"


# --------------------------------------------------------------------------- #
# CDR extraction — field names to be verified in Phase 1 against a live
# record; adjust here only.
# --------------------------------------------------------------------------- #

def _first(rec, *keys):
    for k in keys:
        v = rec.get(k)
        if v not in (None, ""):
            return v
    return None


def cdr_identity(rec):
    rid = _first(rec, "recordId", "record_id", "id")
    if not rid:
        rid = sha1(json.dumps(rec, sort_keys=True).encode()).hexdigest()[:32]
    return str(rid)


def cdr_parties(rec):
    """[(party_identifier, 'inbound'|'outbound')]. originating -> outbound,
    terminating -> inbound."""
    parties = []
    orig = _first(rec, "originatingUserId", "originatingUserEmail")
    term = _first(rec, "terminatingUserId", "terminatingUserEmail")
    if orig:
        parties.append((str(orig), "outbound"))
    if term:
        parties.append((str(term), "inbound"))
    return parties


def cdr_answered(rec):
    return bool(_first(rec, "answered", "isAnswered", "answer_indicator"))


def cdr_duration(rec):
    try:
        return int(_first(rec, "duration", "durationSeconds") or 0)
    except (TypeError, ValueError):
        return 0


def cdr_start(rec):
    v = _first(rec, "startTime", "start_time", "callStartTime")
    if not v:
        return None
    return db.to_utc_iso(db.parse_iso(str(v)))


def collect_records(conn, records):
    stored = 0
    for rec in records:
        start = cdr_start(rec)
        if not start:
            continue
        db.upsert_cdr(conn, cdr_identity(rec), start, cdr_duration(rec),
                      cdr_answered(rec), json.dumps(rec, separators=(",", ":")))
        stored += 1
    return stored


# --------------------------------------------------------------------------- #
# Collector
# --------------------------------------------------------------------------- #

def run_collector(cfg):
    db.init(cfg)
    conn = db.connect(cfg)
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=MAX_BACKFILL_DAYS - 1)
    last_end = db.kv_get(conn, "last_collect_end")
    start = (db.parse_iso(last_end) - timedelta(days=1)) if last_end \
        else now - timedelta(days=OVERLAP_DAYS)
    if last_end is None and start < cutoff:
        with conn:
            db.kv_set(conn, "gap_warning", db.to_utc_iso(start))
    start = max(start, cutoff)
    collected = 0
    try:
        while start < now - timedelta(minutes=10):
            end = min(start + timedelta(hours=CHUNK_HOURS), now - timedelta(minutes=10))
            records = webex.fetch_cdr_window(cfg, start, end)
            with conn:
                collected += collect_records(conn, records)
                db.kv_set(conn, "last_collect_end", db.to_utc_iso(end))
            log.info("CDR window %s..%s: +%d records", start, end, len(records))
            start = end
            if start < now - timedelta(minutes=10):
                time.sleep(PACE_START_SECONDS)
        sync_members(cfg, conn)
    finally:
        conn.close()
    log.info("Collector done: %d records stored/updated", collected)
    return collected


def sync_members(cfg, conn):
    today = datetime.now(local_tz(cfg)).strftime("%Y-%m-%d")
    groups = webex.list_groups(cfg)
    by_name = {(g.get("displayName") or g.get("name") or "").lower(): g for g in groups}
    for name in cfg.get("report_groups", []):
        g = by_name.get(name.lower()) or webex.group_by_name(cfg, name)
        if not g:
            log.error("Group not found in Control Hub: %s", name)
            continue
        raw = webex.group_members(cfg, g["id"])
        members = [{"person_id": _first(m, "personId", "id"),
                    "name": _first(m, "displayName", "name"),
                    "email": _first(m, "email")}
                   for m in raw]
        members = [m for m in members if m["person_id"]]
        with conn:
            db.save_members(conn, today, g["id"], members)
        log.info("Group '%s': %d members snapshotted", name, len(members))


# --------------------------------------------------------------------------- #
# Aggregation + report
# --------------------------------------------------------------------------- #

def month_end_date(month):
    y, m = int(month[:4]), int(month[5:7])
    nxt = datetime(y + 1, 1, 1) if m == 12 else datetime(y, m + 1, 1)
    return (nxt - timedelta(days=1)).strftime("%Y-%m-%d")


def aggregate(cfg, month):
    conn = db.connect(cfg)
    try:
        start_iso, end_iso = month_range_utc(month)
        stats = {}
        for m in db.members_at(conn, month_end_date(month)):
            stats[m["person_id"]] = dict(m, inbound=0, outbound=0, talk_s=0)
        for row in db.cdrs_in_window(conn, start_iso, end_iso):
            rec = db.load_json(row["raw"])
            d = cdr_duration(rec)
            for pid, direction in cdr_parties(rec):
                s = stats.get(pid)
                if s:
                    s[direction] += 1
                    s["talk_s"] += d
        rows = [{"name": s["name"], "email": s["email"],
                 "inbound": s["inbound"], "outbound": s["outbound"],
                 "total": s["inbound"] + s["outbound"],
                 "talk_min": round(s["talk_s"] / 60, 1)}
                for s in stats.values()]
        rows.sort(key=lambda r: (r["total"], r["name"] or ""), reverse=True)
        return rows
    finally:
        conn.close()


def make_csv(rows, month):
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Webex Call Report", month])
    w.writerow(["Name", "Email", "Inbound Calls", "Outbound Calls",
                "Total Calls", "Talk Time (min)"])
    for r in rows:
        w.writerow([r["name"], r["email"], r["inbound"], r["outbound"],
                    r["total"], r["talk_min"]])
    w.writerow(["TOTAL", "", sum(r["inbound"] for r in rows),
                sum(r["outbound"] for r in rows),
                sum(r["total"] for r in rows),
                round(sum(r["talk_min"] for r in rows), 1)])
    return out.getvalue().encode("utf-8")


def report_html(cfg, month, rows):
    tot_in = sum(r["inbound"] for r in rows)
    tot_out = sum(r["outbound"] for r in rows)
    parts = [f"<h2>Webex Monthly Call Report — {month}</h2>",
             f"<p><b>Total:</b> {tot_in} inbound, {tot_out} outbound "
             f"({tot_in + tot_out} calls) across {len(rows)} users. "
             "Counts are answered calls only; detail CSV attached.</p>"]
    conn = db.connect(cfg)
    gap = db.kv_get(conn, "gap_warning")
    conn.close()
    if gap:
        parts.append("<p style='color:red'><b>Warning:</b> a data gap older than "
                     "30 days was detected; part of this month could not be "
                     "collected from Webex.</p>")
    parts.append("<table border=1 cellpadding=4 cellspacing=0>"
                 "<tr><th>Name</th><th>Email</th><th>Inbound</th>"
                 "<th>Outbound</th><th>Total</th><th>Talk (min)</th></tr>")
    for r in rows:
        parts.append(f"<tr><td>{r['name']}</td><td>{r['email']}</td>"
                     f"<td>{r['inbound']}</td><td>{r['outbound']}</td>"
                     f"<td>{r['total']}</td><td>{r['talk_min']}</td></tr>")
    parts.append("</table>")
    return "\n".join(parts)


def run_reporter(cfg, month=None, send=True):
    db.init(cfg)
    month = month or previous_month()
    rows = aggregate(cfg, month)
    csv_bytes = make_csv(rows, month)
    conn = db.connect(cfg)
    recipients = db.get_recipients(conn)
    if not rows:
        with conn:
            db.add_report(conn, month, recipients, "skipped", "no data / no members")
        conn.close()
        log.warning("Report %s skipped: no data / no members", month)
        return rows, "skipped"
    if send and recipients:
        try:
            send_email(cfg, month, recipients, report_html(cfg, month, rows), csv_bytes)
            with conn:
                db.add_report(conn, month, recipients, "sent")
            status = "sent"
        except Exception as e:
            log.exception("Email send failed")
            with conn:
                db.add_report(conn, month, recipients, "failed", str(e))
            status = "failed"
    else:
        with conn:
            db.add_report(conn, month, recipients, "not sent", "manual/no recipients")
        status = "not sent"
    conn.close()
    return rows, status


def send_email(cfg, month, recipients, html, csv_bytes):
    s = cfg["smtp"]
    msg = MIMEMultipart()
    msg["From"] = s["from"]
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = f"Webex Call Report {month}"
    msg.attach(MIMEText(html, "html", "utf-8"))
    att = MIMEBase("application", "octet-stream")
    att.set_payload(csv_bytes)
    email.encoders.encode_base64(att)
    att.add_header("Content-Disposition", "attachment",
                   filename=f"webex_call_report_{month}.csv")
    msg.attach(att)
    with smtplib.SMTP(s["host"], int(s["port"]), timeout=60) as server:
        if s.get("use_tls"):
            server.starttls()
        if s.get("user"):
            server.login(s["user"], s["password"])
        server.send_message(msg)


# --------------------------------------------------------------------------- #
# Scheduler — one thread, minute-resolution checks
# --------------------------------------------------------------------------- #

def start_scheduler(cfg):
    stop = threading.Event()
    threading.Thread(target=_loop, args=(cfg, stop), daemon=True).start()
    return stop


def _loop(cfg, stop):
    log.info("Scheduler running (collect 01:00, report on the 2nd 06:00 %s)",
             cfg.get("org_timezone", "Asia/Muscat"))
    while not stop.is_set():
        try:
            now_local = datetime.now(local_tz(cfg))
            today = now_local.strftime("%Y-%m-%d")
            if _collect_due(cfg, now_local, today):
                log.info("Scheduler: running collector")
                run_collector(cfg)
                conn = db.connect(cfg)
                with conn:
                    db.kv_set(conn, "last_collect_date", today)
                conn.close()
            due = previous_month(now_local)
            if now_local.day == 2 and now_local.hour >= 6 and _last_report(cfg) != due:
                log.info("Scheduler: sending monthly report for %s", due)
                run_reporter(cfg, due)
                conn = db.connect(cfg)
                with conn:
                    db.kv_set(conn, "last_report_month", due)
                conn.close()
        except Exception:
            log.exception("Scheduler tick failed")
        stop.wait(60)


def _collect_due(cfg, now_local, today):
    if now_local.hour < 1 and not _stale(cfg):
        return False
    conn = db.connect(cfg)
    last = db.kv_get(conn, "last_collect_date")
    conn.close()
    if _stale(cfg) or last != today:
        return True
    return False


def _stale(cfg):
    conn = db.connect(cfg)
    last_end = db.kv_get(conn, "last_collect_end")
    conn.close()
    if not last_end:
        return True
    return datetime.now(timezone.utc) - db.parse_iso(last_end) > timedelta(hours=40)


def _last_report(cfg):
    conn = db.connect(cfg)
    v = db.kv_get(conn, "last_report_month")
    conn.close()
    return v
