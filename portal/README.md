# UIABO Operational Portal (data engineer + system administrator)

A **staff account** can have **Data Engineer**, **System Admin**, or both permissions.

Incorrect-result investigations support completed text, deepfake, image-context
and link-safety checks. Engineers see each type's original result fields and may
load its saved image through an authenticated, audited report endpoint. Submitted
links are displayed as text. Image scoring and labels retain their existing meanings.
Staff accounts are separate from UIABO app accounts. Use different email addresses
for staff and app access in the existing Firebase project.
Choose the intended portal from **Log in to** on the login screen. The same
email/password works for either portal when both roles have been granted.
To use the other portal, log out and choose it when signing in again.

The backend validates the selection and checks current permissions on every
operational API request. Choosing a dropdown option never grants access.
Data Engineers get report investigation and monitoring; System Admins get
user management and feedback review.

## Screens

| Screen | Covers |
| --- | --- |
| Log in / Register / Forgot password | Firebase authentication, email verification and staff registration; registration itself grants no portal permissions |
| Email verification gate | Verified email required for any operational access |
| Dashboard | UC-41: report totals, trends, label/pipeline breakdowns, analysis health, ingestion health |
| Reports → Report detail | UC-42: investigation view with the user's reason, the generated assessment, evidence and an audited status/note update |
| Pipeline monitoring | UC-43: analysis runs (per-stage timings, failures) and data-ingestion runs (forecast snapshot + source catalogue), clearly separated, with manual re-run and follow-up notes |
| Find users (admin) | Search accounts; view allowance; suspend/restore access; edit Data Engineer and System Admin permissions with a reason |
| Provision staff (admin) | Grant one or both roles to a verified Firebase account by email, preserving existing staff permissions; app accounts cannot be provisioned |
| Audit history (admin) | Read actions, actors, affected accounts, outcomes and permission changes; filter by date range, action, outcome and user ID |
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

## Grant portal access

### Through the portal

1. New staff choose **Create an account** on the portal login screen, enter their
   name/email and choose their own password. They verify the Firebase email and
   select **I have verified - continue**. Use a different email from their mobile
   app account. Existing staff accounts can be reused.
2. An existing System Admin opens **Provision staff**, enters the verified email,
   selects Data Engineer, System Admin or both, and records a reason.
3. Select **Grant portal access** and confirm the named account and permissions.
4. The staff member signs in to the selected portal, or retries portal access
   if already signed in. The admin does not receive or set their password.

Provisioning is additive and retry-safe. It preserves the staff name and
permissions already held. Staff accounts have no app membership or allowance.
App accounts are refused instead of being converted or promoted. Unregistered/unverified accounts
must finish registration first. Disabled, suspended, deleting and deactivated
accounts cannot receive additional access. No invitation email is sent by the
admin form; Firebase sends verification/reset emails from the staff login flow.

To remove or replace permissions, use **Find users**, open the account, change
its **Staff portal access** checkboxes, give a reason, and select **Save
permissions**. Clear both checkboxes to remove all portal access. Concurrent
edits are rejected with a reload instruction instead of overwriting each other.
Revocations take effect at the next protected API request.

Administrators cannot suspend themselves or remove their own System Admin
permission. Another active administrator must do that. Each change rechecks
both accounts in a Firestore transaction; this also prevents simultaneous
mutual revocations from leaving no active administrator.

### Bootstrap the first administrator

The first administrator still needs the local trusted provisioning script.
From `C:\Dev\uiabo-vision\backend`, run:

```powershell
.\.venv\Scripts\python.exe -B -m scripts.create_operational_account --email "operator@example.com" --roles data_engineer system_admin
```

The staff Firebase account must already exist and have a verified email. Replace the
example email with that account's email. To grant only one permission, use
`--role data_engineer` or `--role system_admin`. Subsequent grants can use the
portal. The script does not create Firebase Auth accounts or set passwords.

The server stores `account_type` (`app` or `staff`) and staff permissions in
`users/{uid}`. Both use the existing Firebase project, but separate Auth UIDs
and emails. Ordinary registration/profile requests cannot select or change the
account type. A System Admin can explicitly convert a former staff account to
Free app membership after all portal permissions have been removed.

### Reuse a former staff email in the app

Removing portal permissions does not delete the Firebase login or turn it into
an app account. Trying to register again with that email will therefore fail.

1. Sign in to **System Admin** using another administrator's account.
2. Open **Find users**, search for the former staff member and open their details.
3. Clear both portal permissions, enter a reason and save, if permissions remain.
4. Under **Reuse a former staff account in the app**, enter a conversion reason.
5. Select **Convert to Free app account** and confirm the named account.
6. The person now chooses **Sign in** in the mobile app using their existing email
   and password. They must not choose **Create account** again.

Only active, verified accounts with no portal permissions can be converted.
Self-conversion is blocked. The UID and owned history remain, a Free daily
allowance is created, and the change is recorded atomically in Audit history.
Existing app accounts cannot be converted again to refill allowance. Staff
permissions cannot be granted back to that app account; use a separate staff
email if the person later needs portal access again.

- `PUT /account/me` creates/updates an app profile with Free/Premium membership.
- `PUT /portal/me` creates/updates a staff profile without an app allowance.
- Both reject a UID already assigned to the other account type.
- Staff accounts cannot use app profile, analysis/history, feedback or deletion
  endpoints. Staff investigations use the authorised portal endpoints.
- App accounts cannot access staff functions or receive staff permissions.
- For legacy profiles without `account_type`, a primary `system_admin` or
  `data_engineer` role identifies a staff account. Free/Premium profiles remain
  app accounts, including profiles with stale combined-role grants.
- Staff can have both operational roles. An explicit empty permission list
  revokes access even for a legacy staff role. Profile edits never grant roles.

The existing database was checked read-only: six app accounts and one legacy
System Admin account, with no combined app/portal grants. No bulk migration or
live account changes were performed. Historical documents are retained.

`GET /portal/session?portal_role=data_engineer` (or `system_admin`) validates
the selected portal and returns the account profile. It does not issue a new
Firebase token or persist a role choice as permission. The browser stores
only the selected portal preference in session storage.

Run the automated checks with `node --test tests/*.test.mjs` and `npm run build`
from `portal`. Use test accounts for the authenticated walkthrough.

## Audit history

- Open **Audit history** for the last 24 hours, 7 days or 30 days.
- Filter by action/outcome, or enter an exact Firebase user ID to match either
  the person who acted or the affected account. **View this account's audit
  history** in user details fills that filter automatically.
- **Older events** continues through the selected date window. A filtered page
  can be empty while more events remain; the page says so explicitly.
- Permission grants/changes save before/after roles and the reason in the same
  Firestore transaction as the account change. Audit records are read-only.
- An **Outcome pending** record means the request's final audit update is not
  yet confirmed. A separately committed permission change is shown as saved.
- Names and emails are resolved from current account profiles. Historical audit
  documents retain masked identifiers; deleted accounts may no longer resolve.
- Each page scans at most 300 audit events and returns at most 100 matches. The
  default is 50. Account-name resolution currently scans the small project user
  collection; a larger deployment should use a dedicated lookup index.
- The audit query was checked against this project's Firestore without adding
  composite indexes. Existing Firebase credentials and portal settings are used.

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

1. Choose **System Admin portal**, then log in with `demo.admin@uiabo.test` (`AdminDemo2026`) — the portal opens
   on *Find users*, and the Reports/Monitoring tabs are not shown.
2. **Search (UC-36)**: search by name or leave empty → accounts list;
   open `Demo Suspended User` → account details with allowance.
3. **Restore access**: *Restore access* → status becomes active with
   confirmation. Suspend it again the same way to keep the demo state.
4. **Feedback review**: *User feedback* → two items awaiting review →
   open one → rating stars and comments → *Mark as reviewed* (records
   reviewer and time).
5. **Denied pages**: an account with only System Admin access cannot use
   report/monitoring APIs, and an account with only Data Engineer access
   cannot use admin APIs. A dual-role account can use either portal.
6. Log out from Profile.

App users submit the feedback the admin reviews: in the app, Profile →
*Send feedback* (category, 1–5 rating, comments) → the record appears in
the admin's *User feedback* list as *submitted*.

## Tests

Backend tests cover single-role and dual-role access, selected-portal
validation, legacy accounts, revocation, suspension, profile updates,
provisioning, report lifecycle, monitoring and feedback.

```powershell
cd ..\backend
.\.venv\Scripts\python.exe -B -m pytest tests/accounts tests/portal tests/feedback -q
```

From `portal`, run `node --test tests/*.test.mjs` and `npm run build`.
The frontend tests cover stored portal choices, validated server sessions and audit date windows.

For an authenticated walkthrough, grant both roles to a verified test account:

1. Choose **Data Engineer portal** and sign in. Check Reports and Pipeline monitoring.
2. Log out, choose **System Admin portal**, and sign in with the same credentials.
   Check Find users and User feedback.
3. Confirm the profile lists both permissions and the selected portal.
4. With a single-role account, select the other portal. Access must be denied;
   selecting its permitted portal must work.
5. Provision a verified staff test account using the admin form. Check that it
   has no app allowance. Remove one permission in user details.
6. Confirm the role change is shown in Audit history with the actor, target,
   before/after permissions and reason. Filter to that user and page older events.
7. Try registering a staff account through the portal: registration and
   email verification alone must not grant access to either staff portal.
8. Try an app account in the portal and a staff account in the app: each must
   be refused with instructions to use a separate account.

## Notes

- Monitoring data contains no user content; user text is only visible inside
  a report investigation, behind the role gate and masked user ids.
- `VITE_PROXY_TARGET` changes the backend address the dev server proxies to.
- `npm run build` produces a static bundle in `dist/` for deployment.
