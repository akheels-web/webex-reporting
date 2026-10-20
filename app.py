import argparse
import json
import logging
import pathlib
import secrets
import sys
import threading

from flask import (Flask, Response, abort, jsonify, redirect, request,
                   send_from_directory, session)

import db
import jobs

log = logging.getLogger(__name__)

HERE = pathlib.Path(__file__).parent
CFG_FILE = HERE / "config.json"
SPA = HERE / "dashboard" / "out"


def load_config():
    if not CFG_FILE.exists():
        print("config.json not found — copy config.example.json to config.json "
              "and fill it in.")
        sys.exit(1)
    return json.loads(CFG_FILE.read_text(encoding="utf-8"))


app = Flask(__name__, static_folder=None)
app.cfg = load_config()
_db = (HERE / ".secret_key")
if not _db.exists():
    _db.write_text(secrets.token_hex(32))
app.secret_key = _db.read_text()
_scheduler_stop = None


def admin_required(fn):
    def wrapper(*a, **kw):
        if not session.get("admin"):
            if request.path.startswith("/api/"):
                return jsonify(error="unauthorized"), 401
            return redirect("/login/")
        return fn(*a, **kw)
    wrapper.__name__ = fn.__name__
    return wrapper


# --------------------------------------------------------------------------- #
# SPA (Next.js static export)
# --------------------------------------------------------------------------- #

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def spa(path=""):
    p = SPA / path
    if path and p.is_file():
        return send_from_directory(SPA, path)
    index = p / "index.html"
    if index.is_file():
        return send_from_directory(SPA, index.relative_to(SPA).as_posix())
    return send_from_directory(SPA, "index.html")


# old pre-dashboards links
@app.route("/login")
@app.route("/reports")
def legacy_redirect():
    return redirect("/")


# --------------------------------------------------------------------------- #
# JSON API
# --------------------------------------------------------------------------- #

@app.route("/api/login", methods=["POST"])
def api_login():
    body = request.get_json(force=True, silent=True) or {}
    pw = body.get("password") or request.form.get("password")
    if pw == app.cfg.get("admin_password"):
        session["admin"] = True
        return jsonify(ok=True)
    return jsonify(error="wrong password"), 401


@app.route("/api/logout", methods=["POST", "GET"])
def api_logout():
    session.clear()
    if request.method == "GET":
        return redirect("/login/")
    return jsonify(ok=True)


@app.route("/api/stats")
@admin_required
def api_stats():
    conn = db.connect(app.cfg)
    months = db.months_available(conn) or [jobs.previous_month()]
    conn.close()
    month = request.args.get("month") or months[0]
    rows = jobs.aggregate(app.cfg, month)
    return jsonify(months=months, month=month, rows=rows)


@app.route("/api/reports")
@admin_required
def api_reports():
    conn = db.connect(app.cfg)
    data = {"history": db.list_reports(conn),
            "recipients": "; ".join(db.get_recipients(conn))}
    conn.close()
    return jsonify(**data)


@app.route("/api/recipients", methods=["POST"])
@admin_required
def api_recipients():
    emails = []
    for e in (request.get_json() or {}).get("emails", "").replace("\n", ";").split(";"):
        if e.strip():
            emails.append(e)
    conn = db.connect(app.cfg)
    with conn:
        db.set_recipients(conn, emails)
    conn.close()
    return jsonify(ok=True)


@app.route("/api/run/collect", methods=["POST"])
@admin_required
def api_run_collect():
    threading.Thread(target=lambda: jobs.run_collector(app.cfg),
                     daemon=True).start()
    return jsonify(started=True)


@app.route("/api/run/report", methods=["POST"])
@admin_required
def api_run_report():
    body = request.get_json(silent=True) or {}
    month = body.get("month") or jobs.previous_month()
    threading.Thread(
        target=lambda: jobs.run_reporter(app.cfg, month), daemon=True).start()
    return jsonify(started=True, month=month)


@app.route("/api/report/<int:report_id>/resend", methods=["POST"])
@admin_required
def api_report_resend(report_id):
    conn = db.connect(app.cfg)
    rep = db.get_report(conn, report_id)
    conn.close()
    if not rep:
        abort(404)
    threading.Thread(
        target=lambda: jobs.run_reporter(app.cfg, rep["month"]),
        daemon=True).start()
    return jsonify(started=True)


@app.route("/download/<month>")
@admin_required
def download(month):
    rows = jobs.aggregate(app.cfg, month)
    data = jobs.make_csv(rows, month)
    return Response(data, mimetype="text/csv",
                    headers={"Content-Disposition":
                             f"attachment; filename=webex_call_report_{month}.csv"})


@app.route("/download/<month>/pdf")
@admin_required
def download_pdf(month):
    rows = jobs.aggregate(app.cfg, month)
    data = jobs.make_pdf(app.cfg, month, rows)
    return Response(data, mimetype="application/pdf",
                    headers={"Content-Disposition":
                             f"attachment; filename=webex_call_report_{month}.pdf"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true",
                    help="run the nightly collection now and exit")
    ap.add_argument("--report", metavar="YYYY-MM",
                    help="aggregate + send report for a month and exit")
    ap.add_argument("--report-dry", "--dry", metavar="YYYY-MM", nargs="?",
                    const="auto",
                    help="print last month's table without emailing")
    ap.add_argument("--port", type=int, default=None)
    args = ap.parse_args()

    data_dir = HERE / "data"
    data_dir.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(data_dir / "service.log"),
                  logging.StreamHandler()])
    db.init(app.cfg)
    if args.collect:
        jobs.run_collector(app.cfg)
    elif args.report:
        rows, status = jobs.run_reporter(app.cfg, args.report)
        print(f"status={status} rows={len(rows)}")
    elif args.report_dry:
        month = args.report_dry if args.report_dry != "auto" else jobs.previous_month()
        rows, _ = jobs.run_reporter(app.cfg, month, send=False)
        for r in rows:
            print(r)
    else:
        global _scheduler_stop
        _scheduler_stop = jobs.start_scheduler(app.cfg)
        port = args.port or app.cfg.get("dashboard_port", 8080)
        if not SPA.exists():
            log.warning("dashboard/out not found — build it: "
                        "cd dashboard && npm install && npm run build")
        log.info("Dashboard http://0.0.0.0:%s (Ctrl+C to stop)", port)
        app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
