# Webex Monthly Call Reporting Tool

Per-user inbound/outbound monthly call counts for selected Webex users,
e-mailed automatically on the **2nd of every month**. Includes a dashboard for
viewing history and re-sending reports.

## How it works

One Python service on the customer's Windows server does three jobs:

```
Nightly collector (01:00 Oman time)
  Webex CDR Feed API -> rolling 3-day window pull -> SQLite
  group membership snapshot for configured Control Hub groups

Monthly reporter (2nd, 06:00 Oman time)
  aggregate previous calendar month per user -> HTML email + CSV
  via customer's SMTP/Exchange

Dashboard (browser, port 8080, LAN)
  /          month picker, per-user table, stacked bar chart, CSV download
  /reports   recipients list, sent-report history, resend, run-now buttons
```

### Key rules

- **Timezone:** `Asia/Muscat` (UTC+4, no DST) drives month boundaries and all
  schedules; config `org_timezone`.
- **30-day API limit:** `cdr_feed` only reaches 30 days back. The nightly
  collector keeps data fresh; it self-heals missed days with a 1-day overlap
  from the last good pull. A gap >30 days is flagged with a warning row in the
  next report.
- **Inbound/outbound:** the CDR's originating party counts as *outbound* for
  that user, terminating party as *inbound*.
- **"Handled" = answered** (`answered=1` and `duration>0`). Missed/zero-length
  calls are excluded.
- **Membership:** users are the members of the configured Control Hub groups,
  snapshotted daily; a report uses the snapshot as of the month's last day, so
  staff added mid-month through Control Hub automatically appear next month.
- **Rate limiting:** `cdr_feed` allows 1 new request/minute + 10 paginations.
  A night pulls 6 x 12h windows (~7 min total).

## Setup checklist (one-time, Webex admin in Control Hub)

1. **Service app** — Control Hub > user avatar > *Organization Settings* >
   *Service Apps*: create one with scopes
   `spark-admin:calling_cdr_read` + group read. Copy `client_id` /
   `client_secret` into `config.json`.
2. **CDR role** — Control Hub > *Account > Roles*: create a custom role from
   the **"Webex Calling Detailed Call History API access"** permission and
   authorize the service app per Cisco's docs for that role.
3. **Regional endpoint** — pick `analytics_base_url` per region
   (US `analytics-calling.webexapis.com`, EU `-eu`, India `-in`,
   Australia `-au`) to avoid HTTP 451.
4. **Verify endpoints** at first run against one live CDR record:
   - field names used in `jobs.py` (`recordId`, `startTime`, `duration`,
     `answered`, `originatingUserId`, `terminatingUserId`) — adjust only in
     the `cdr_*` helper functions there;
   - `GET /v1/groups/{id}/members` result shape in `webex.py`.
5. **SMTP** — Exchange/relay host, port, credentials, sender address.

## Install & run

```powershell
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy config.example.json config.json    # fill in values
.venv\Scripts\python app.py             # dashboard + scheduler
.venv\Scripts\python app.py --collect   # one collection now (CLI)
.venv\Scripts\python app.py --report-dry   # print last-month table, no email
.venv\Scripts\python app.py --report 2026-09   # generate & email a month
.venv\Scripts\python -m unittest discover -s tests   # self-check
```

Service install (customer server): run via **Task Scheduler** with
`pythonw .venv\Scripts\python app.py --port 8080` at startup, or wrap with
NSSM. Logs in `data\service.log`.

## Files

| File | Purpose |
|------|---------|
| `app.py`    | Flask dashboard, CLI entry, starts scheduler thread |
| `jobs.py`   | collector, CDR field extraction, aggregation, CSV/email, scheduler |
| `webex.py`  | token handling (service app client-credentials + refresh) and API calls |
| `db.py`     | SQLite schema and access |
| `config.json` | credentials, groups, SMTP, timezone (**gitignored**) |
| `tokens.json`, `data/` | runtime state (**gitignored**) |

## Decision log

- **Group-driven scope** over fixed user lists: membership changes stay in
  Control Hub where admins already work; tool follows automatically.
- **Nightly collector + local SQLite** over one big monthly pull: `cdr_feed`
  cannot serve a full previous month on the 2nd (30-day window).
- **`cdr_feed` over `cdr_stream`**: purpose is historical reporting, not a
  live mirror (per Cisco's guidance); needs no always-on consumer.
- **Raw CDR JSON stored as-is**: fixing field-name mapping after Phase-1
  verification needs no data migration; re-aggregation reads raw.
- **Service app client-credentials** over user-token integrations: no monthly
  re-login; tokens auto-refresh in `webex.py`.
- **Single shared admin password, LAN-only dashboard**: one operator; skip
  per-user accounts/RBAC until a second audience exists.
- **Next.js + shadcn/ui front end, statically exported** and served by the
  same Python service (`dashboard/out`): modern UI without a second runtime
  (Node needed only to build). Old Flask templates deleted; Flask keeps the
  JSON API (`/api/login`, `/api/stats`, `/api/reports`, run-now/resend,
  `/download/<month>`) + SPA fallback route.
- `tzdata` pinned in requirements (Windows has no system tz database).
