"""Generate README screenshots with demo data (dev helper, not run in prod).

Usage: .venv\\Scripts\\python.exe tools\\make_screenshots.py
Leaves docs/screenshots/*.png; cleans up its demo config/data afterwards.
"""
import json
import pathlib
import random
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import db
import jobs
from playwright.sync_api import sync_playwright

PORT = 8910
MONTH = "2026-09"
OUT = ROOT / "docs" / "screenshots"

MEMBERS = [
    ("p1", "Aisha Al Balushi", "aisha.albalushi"),
    ("p2", "Mohammed Al Ajmi", "mohammed.ajmi"),
    ("p3", "Sara Al Hinai", "sara.hinai"),
    ("p4", "Khalid Al Harthy", "khalid.harthy"),
    ("p5", "Fatma Al Siyabi", "fatma.siyabi"),
    ("p6", "Omar Al Farsi", "omar.farsi"),
    ("p7", "Salim Al Jabri", "salim.jabri"),
    ("p8", "Nadia Al Zadjali", "nadia.zadjali"),
]


def seed():
    db.init({"data_dir": "data"})
    conn = db.connect({"data_dir": "data"})
    db.save_members(conn, "2026-09-30", "g1",
                    [{"person_id": p, "name": n, "email": f"{e}@nf-oman.om"}
                     for p, n, e in MEMBERS])
    rng = random.Random(42)
    n = 0
    for pid, name, email in MEMBERS:
        for _ in range(rng.randint(14, 52)):        # inbound
            n += 1
            day = f"2026-09-{rng.randint(1, 30):02d}"
            secs = f"{rng.randint(7, 19):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}"
            dur = rng.randint(30, 2400)
            rec = {"recordId": f"demo-i{n}", "startTime": f"{day}T{secs}Z",
                   "duration": dur, "answered": True,
                   "originatingUserId": "external", "terminatingUserId": pid}
            run(db, conn, rec)
        for _ in range(rng.randint(20, 85)):       # outbound
            n += 1
            day = f"2026-09-{rng.randint(1, 30):02d}"
            secs = f"{rng.randint(7, 19):02d}:{rng.randint(0, 59):02d}:{rng.randint(0, 59):02d}"
            dur = rng.randint(15, 1800)
            rec = {"recordId": f"demo-o{n}", "startTime": f"{day}T{secs}Z",
                   "duration": dur, "answered": True,
                   "originatingUserId": pid, "terminatingUserId": "external"}
            run(db, conn, rec)
    # a skipped report so history looks real
    db.add_report(conn, MONTH, ["manager@nf-oman.om"], "sent", "")
    db.set_recipients(conn, ["manager@nf-oman.om", "it-admin@nf-oman.om"])
    conn.commit()
    conn.close()
    print(f"seeded {n} demo CDRs")


def run(db, conn, rec):
    db.upsert_cdr(conn, rec["recordId"], jobs.cdr_start(rec), rec["duration"],
                  True, json.dumps(rec))


def main():
    cfg = {"data_dir": "data", "admin_password": "demo", "dashboard_port": PORT}
    (ROOT / "config.json").write_text(json.dumps(cfg, indent=2))
    seed()
    app = ROOT / "app.py"
    proc = subprocess.Popen([sys.executable, str(app), "--port", str(PORT)],
                            cwd=ROOT, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    try:
        for _ in range(40):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{PORT}/login", timeout=2)
                break
            except OSError:
                time.sleep(0.5)
        OUT.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 800},
                                    device_scale_factor=2)
            page.goto(f"http://127.0.0.1:{PORT}/login")
            page.screenshot(path=str(OUT / "login.png"))
            page.fill("input[name=password]", "demo")
            page.click("button[type=submit]")
            page.wait_for_selector("canvas", timeout=30000)
            page.wait_for_timeout(1500)  # chart animation
            page.screenshot(path=str(OUT / "dashboard.png"), full_page=True)
            page.goto(f"http://127.0.0.1:{PORT}/reports")
            page.wait_for_selector("table", timeout=20000)
            page.screenshot(path=str(OUT / "reports.png"))
            browser.close()
        print("screenshots ->", OUT)
    finally:
        proc.terminate()
        shutil.rmtree("data", ignore_errors=True)
        for f in ("config.json", ".secret_key"):
            (ROOT / f).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
