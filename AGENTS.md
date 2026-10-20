# Project Memory: Webex Reporting Tool

## Overview
Webex Calling monthly reporting tool. Extracts per-user inbound and outbound handled call counts and talk times for configured Webex Control Hub groups, sent on the 2nd of each month via email (SMTP / Microsoft 365 Outlook), accompanied by an administrative Next.js + Flask dashboard.

## Key Architectural Decisions & Constraints
- **Webex Calling CDR Feed Retention:** The Cisco Detailed Call History API (`/v1/cdr_feed`) only retains records for up to 30 days. Query windows cannot exceed 12 hours. Rate limits are 1 new query/minute + up to 10 paginations.
- **Nightly Collector:** Nightly collector runs at 01:00 (Oman time, `Asia/Muscat`), rolling 3-day window pull into SQLite (`data/app.db`).
- **Handled Call Definition:** Answered calls only (`answered = 1` and `duration > 0`). Originating party = outbound, terminating party = inbound.
- **Reporting Date:** 2nd of every month at 06:00 (Oman time). Covers full previous calendar month.
- **n8n Workflow Integration (`n8n-webex-monthly-report.json`):**
  - Triggers on `0 6 2 * *` (2nd of every month at 06:00).
  - Can orchestrate either directly via Webex APIs or via the local reporting service API (`/api/stats`, `/download/<month>`).
  - Prepares executive HTML summary cards and table, builds CSV attachment.
  - Sends email via Microsoft 365 Outlook (`n8n-nodes-base.microsoftOutlook` or Microsoft Graph API).
