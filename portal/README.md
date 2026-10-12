# UIABO Operational Portal (data engineer + system administrator)

One portal, two operational roles. The login screen is shared; after sign-in
the role decides which pages appear — data engineers get report
investigation and pipeline monitoring, system administrators get user
management and feedback review. Each role only ever sees and can only call
its own pages and APIs (enforced again server-side on every route).

Web portal for the **data engineer** role: investigate reported incorrect
results, monitor the analysis pipeline and data-ingestion jobs, and manage the
operator account. Built with Vite + React and the Firebase web SDK; all data
goes through the FastAPI backend (no direct Firestore access from the browser).

System-administrator pages are a separate workstream; this portal deliberately
denies non-data-engineer accounts.

## Screens

| Screen | Covers |
| --- | --- |
| Log in / Forgot password | UC-36, UC-38 (Firebase auth, neutral reset confirmation) |
| Email verification gate | Verified email required for any operational access |
| Dashboard | UC-41: report totals, trends, label/pipeline breakdowns, analysis health, ingestion health |
| Reports → Report detail | UC-42: investigation view with the user's reason, the generated assessment, evidence and an audited status/note update |
| Pipeline monitoring | UC-43: analysis runs (per-stage timings, failures) and data-ingestion runs (forecast snapshot + source catalogue), clearly separated, with manual re-run and follow-up notes |
| Find users (admin) | Search accounts by name/email, open account details with allowance, suspend or restore access with confirmation |
| User feedback (admin) | List feedback with status filters, read ratings and comments, mark feedback as reviewed (records who and when) |
| Profile | UC-39, UC-40: view/update name, password-reset email, log out with confirmation |
| Idle auto-logout | UC-37 S1: session ends after 30 minutes of inactivity |

## Setup

1. Backend: follow `../backend` setup (Python venv, `.env` keys, Firestore).
2. This folder:

   ```bash
   cd portal
   cp .env.example .env
   # Fill VITE_FIREBASE_* with the same Firebase web-app values as mobile/.env
   npm install
   ```

3. Start backend + portal (two terminals):

   ```bash
   # terminal 1
   cd backend && .venv/bin/python -m uvicorn app.main:app --reload
   # terminal 2
   cd portal && npm run dev
   ```

   Open <http://localhost:5174>. Vite proxies `/analysis`, `/account`,
   `/portal` and `/admin` to the backend, so no CORS changes are needed.

## Provision an operational account

Accounts are created from Firebase Auth + a Firestore role. Two ways:

**Seed script (fastest, also loads demo data):**

```bash
cd ../backend
python -m scripts.seed_portal_demo
# Creates demo.engineer@uiabo.test (EngineerDemo2026, data_engineer),
# demo.admin@uiabo.test (AdminDemo2026, system_admin), app-side demo users
# (incl. a suspended one) plus demo reports, runs, and feedback.
# --clean removes it all.
```

**Manual (for your own account):**

1. Register once with the working email (mobile app or the `web-dev` console)
   and verify the email.
2. From `backend`:

   ```bash
   python -m scripts.create_operational_account \
     --email engineer@example.com --role data_engineer   # or --role system_admin
   ```

3. Log in to the portal with that account.

## Demo walkthrough (reproducible end to end)

Run `python -m scripts.seed_portal_demo` from `backend` first — it creates the
demo data-engineer account **and** seeded data (reports in all four statuses,
completed/failed analysis runs with stage timings, ingestion runs including a
failure with a follow-up and a stale catalogue refresh).

1. **Denied access**: log in with a normal free account → "Access denied".
   A suspended data engineer gets "Account unavailable".
   `demo.plain@uiabo.test` (password `PlainDemo2026`) is pre-seeded as a
   free-role account for this check; `demo.mobile@uiabo.test`
   (`MobileDemo2026`) is a free account and `demo.premium@uiabo.test`
   (`PremiumDemo2026`) a server-granted premium account for testing the app side.
2. **Seed a report**: in the mobile app (or `web-dev` console), submit a text
   check with a free account, open the saved result → *Report a problem with
   this result* → choose a reason, describe the problem, send.
3. **Dashboard**: log in as the data engineer → the report appears in the
   totals, trend and status breakdown.
4. **Investigate (UC-42)**: Reports → open the report → compare the user's
   reason with the generated assessment and evidence → set status
   *reviewing* with a note → save. The history trail records the change.
   Repeat to *resolved*.
5. **Analysis monitoring (UC-43)**: Pipeline monitoring → see the run created
   in step 2 with per-stage timings; submit a bad check (e.g. no API keys) to
   see a failed run with its failure stage. Filters and summary update.
6. **Ingestion monitoring**: "Run now" on *Official weather forecast snapshot*
   (needs internet; a provider outage yields a failed run). Mark *stale* by
   waiting past the freshness window or compare with *Trusted-source catalogue
   refresh*. Record a follow-up on any run.
7. **Logout**: Profile → Log out (with confirmation).

### Administrator walkthrough (same seed data)

1. Log in with `demo.admin@uiabo.test` (`AdminDemo2026`) — the portal opens
   on *Find users*, and the Reports/Monitoring tabs are not shown.
2. **Search (UC-36)**: search by name or leave empty → accounts list;
   open `Demo Suspended User` → account details with allowance.
3. **Restore access**: *Restore access* → status becomes active with
   confirmation. Suspend it again the same way to keep the demo state.
4. **Feedback review**: *User feedback* → two items awaiting review →
   open one → rating stars and comments → *Mark as reviewed* (records
   reviewer and time).
5. **Denied pages**: as admin, the app-side data-engineer APIs stay
   forbidden (`/portal/*` returns 403) and vice versa — the UI hides the
   other role's pages and the backend enforces it.
6. Log out from Profile.

App users submit the feedback the admin reviews: in the app, Profile →
*Send feedback* (category, 1–5 rating, comments) → the record appears in
the admin's *User feedback* list as *submitted*.

## Tests

Backend tests cover the role gate, report lifecycle, monitoring, the admin
routes and denied access for every route (both directions — a data engineer
cannot call `/admin`, an administrator cannot call `/portal`):

```bash
cd ../backend
.venv/bin/python -m pytest tests/portal tests/accounts/test_admin_routes.py tests/feedback -q
```

The frontend has no automated tests yet; the walkthrough above is the
acceptance script.

## Notes

- Monitoring data contains no user content; user text is only visible inside
  a report investigation, behind the role gate and masked user ids.
- `VITE_PROXY_TARGET` changes the backend address the dev server proxies to.
- `npm run build` produces a static bundle in `dist/` for deployment.
