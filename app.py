import argparse
import json
import logging
import pathlib
import secrets
import sys
import threading

from flask import (Flask, abort, flash, redirect, render_template, request,
                   session, url_for)

import db
import jobs

log = logging.getLogger(__name__)

HERE = pathlib.Path(__file__).parent
CFG_FILE = HERE / "config.json"


def load_config():
    if not CFG_FILE.exists():
        print("config.json not found — copy config.example.json to config.json "
              "and fill it in.")
        sys.exit(1)
    return json.loads(CFG_FILE.read_text(encoding="utf-8"))


app = Flask(__name__)
app.cfg = load_config()
_db = (HERE / ".secret_key")
if not _db.exists():
    _db.write_text(secrets.token_hex(32))
app.secret_key = _db.read_text()
_scheduler_stop = None


def require_admin(fn):
    def wrapper(*a, **kw):
        if not session.get("admin"):
            return redirect(url_for("login"))
        return fn(*a, **kw)
    wrapper.__name__ = fn.__name__
    return wrapper


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("password") == app.cfg.get("admin_password"):
            session["admin"] = True
            return redirect(url_for("index"))
        flash("Wrong password")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@require_admin
def index():
    conn = db.connect(app.cfg)
    months = db.months_available(conn) or [jobs.previous_month()]
    conn.close()
    month = request.args.get("month") or months[0]
    rows = jobs.aggregate(app.cfg, month)

    def sum_fn(rows_, key):
        return sum(r[key] for r in rows_)

    top = sorted(rows, key=lambda r: r["total"], reverse=True)[:15]
    chart_data = {
        "labels": [r["name"] or r["email"] for r in top],
        "inbound": [r["inbound"] for r in top],
        "outbound": [r["outbound"] for r in top],
    }
    return render_template("index.html", months=months, month=month, rows=rows,
                           sum_fn=sum_fn, chart_data=chart_data)


@app.route("/reports", methods=["GET", "POST"])
@require_admin
def reports():
    conn = db.connect(app.cfg)
    if request.method == "POST":
        if request.form.get("action") == "recipients":
            db.set_recipients(conn, request.form.get("emails", "").split(";"))
            flash("Recipients updated")
        conn.commit()
    history = db.list_reports(conn)
    recipients = "; ".join(db.get_recipients(conn))
    conn.close()
    return render_template("reports.html", history=history,
                           recipients=recipients)


@app.route("/api/stats")
def api_stats():
    month = request.args.get("month") or jobs.previous_month()
    rows = jobs.aggregate(app.cfg, month)
    top = sorted(rows, key=lambda r: r["total"], reverse=True)[:15]
    return {
        "labels": [r["name"] or r["email"] for r in top],
        "inbound": [r["inbound"] for r in top],
        "outbound": [r["outbound"] for r in top],
    }


@app.route("/download/<month>")
@require_admin
def download(month):
    rows = jobs.aggregate(app.cfg, month)
    data = jobs.make_csv(rows, month)
    from flask import Response
    return Response(data, mimetype="text/csv",
                    headers={"Content-Disposition":
                             f"attachment; filename=webex_call_report_{month}.csv"})


@app.route("/runcollect", methods=["POST"])
@require_admin
def runcollect():
    threading.Thread(target=lambda: jobs.run_collector(app.cfg), daemon=True).start()
    flash("Collection started in background (takes a few minutes)")
    return redirect(url_for("index"))


@app.route("/sendreport", methods=["POST"])
@require_admin
def sendreport():
    month = request.form.get("month") or jobs.previous_month()
    threading.Thread(
        target=lambda: jobs.run_reporter(app.cfg, month), daemon=True).start()
    flash(f"Monthly report for {month} is being generated and sent")
    return redirect(url_for("reports"))


@app.route("/resend/<int:report_id>", methods=["POST"])
@require_admin
def resend(report_id):
    conn = db.connect(app.cfg)
    rep = db.get_report(conn, report_id)
    conn.close()
    if not rep:
        abort(404)
    threading.Thread(
        target=lambda: jobs.run_reporter(app.cfg, rep["month"]), daemon=True).start()
    flash(f"Report {rep['month']} queued for resend")
    return redirect(url_for("reports"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--collect", action="store_true",
                    help="run the nightly collection now and exit")
    ap.add_argument("--report", metavar="YYYY-MM",
                    help="aggregate + send report for a month and exit")
    ap.add_argument("--report-dry", "--dry", metavar="YYYY-MM", nargs="?", const="auto",
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
        log.info("Dashboard http://0.0.0.0:%s (Ctrl+C to stop)", port)
        app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
