# Backend fixes — 2 November 2026

Working folder: `C:\Dev\uiabo-vision`

Branch: `feature/evidence-label-consistency`

Implementation notes from local development. See Git history for the current commit and publication status.

## Completed

- Image checks enforce active Premium membership on the server.
- A failed image check never consumes allowance, including failure after caption extraction.
- Gemini/Tavily outages are failures, not completed uncertain/insufficient-evidence results.
- Image submissions have bounded upload size, pixel count, processing time and concurrency. A timed-out native worker keeps its slot until it actually stops.
- Existing private image storage is included. Saving and charging follow a successful upload. Interrupted commits are checked before removing an image.
- Image context accepts an optional caption. The same feature handles image + caption and screenshot-caption extraction. A changed caption cannot reuse an old request key.
- Directional image-context conclusions require a relevant evidence relationship and an exact quotation from a retrieved passage. This validates citation grounding, not model accuracy or reverse-image provenance.
- Text run IDs match saved result IDs. Text/link monitoring reports completion only after result storage succeeds.
- Portal monitoring and investigation-save failures are visible.
- Operational API access/actions have durable audit records. If the initial audit write fails, the request is refused. A failed final audit update leaves a started event for reconciliation.
- Account suspension requires a reason, records the actor, revokes sessions and disallows self-suspension. Transactional actor/target checks prevent two active administrators from concurrently suspending one another and leaving none active.
- Account deletion has a backend endpoint and a Profile entry point.

## Connected app functions

| Action | Endpoint | Behaviour |
| --- | --- | --- |
| Image with optional caption | `POST /analysis/image-context` | Multipart `image`, optional `filename`, optional `caption` (5,000 characters). Omit caption for screenshot extraction. Premium required. |
| Delete own account | `DELETE /account/me` | Recent Firebase authentication within five minutes is required. Returns 202 after durable acceptance, not after all cleanup has finished. |

All endpoints use the existing Firebase Bearer token. No UID, role or quota supplied by a client grants access. Account deletion does not require a new API key.

The app now connects these functions:

- **Check image context:** select an image and optionally enter its caption. A blank caption uses screenshot extraction. The duplicate Image + Caption home tile was removed.
- **Profile: Delete my account:** enter the current password, confirm, reauthenticate with Firebase, then request deletion. An accepted request locks the session and signs out; it does not claim that all cleanup has finished.
- Image selection recovery returns to OCR, image context or deepfake according to the original screen and signed-in account. Image checks block duplicate submissions and navigation while processing.
- Premium access labels and Help describe the implemented features. Real payments remain deferred; a zero-charge demo checkout is now available when explicitly enabled.

## Image/link reporting and demo checkout

- Completed text, deepfake, image-context and link-safety results have the shared report form, including when reopened from history.
- Report snapshots retain the result's own label. Image and link reports do not invent a misinformation score.
- Data Engineers can inspect image explanations, caption evidence and link-threat details. Saved images require authenticated, audited access through an existing report; raw storage paths are not exposed in portal assessment responses.
- Free app users can review and complete demo checkout. The backend grants Premium and its monthly allowance with a zero-charge receipt in one transaction. Retrying does not refill allowance. Staff, unavailable accounts and accounts with a running analysis cannot upgrade.
- `DEMO_PAYMENTS_ENABLED=1` enables the simulation; real payments and recurring billing are not implemented. See [demo checkout setup and testing](DEMO_PREMIUM_SETUP.md).
- Offline tests no longer read developer `.env` files. Pipeline modes are selected explicitly in tests, including coverage of both legacy and JEV V3 wiring. Provider mocks and account fixtures do not require real Firebase/Gemini credentials.
- Image scoring and label meanings have been retained as requested.

## Separate staff and app accounts

**3 November follow-up:** System Admin now provides an explicit former-staff
conversion action under Find users. After all portal permissions are removed,
an active, verified staff login can become a Free app account with the same
email/password. The person signs in rather than registering again. Registration
itself never converts accounts. Self-conversion, active staff permissions,
suspended/deactivated accounts and repeated allowance resets are blocked.
The account, allowance and conversion audit commit together. No live account
was converted during development. See the portal README for the walkthrough.
Verification: 173 account/auth/portal/feedback tests passed, including conversion
eligibility, retained login identity, blocked portal access, retry allowance
protection and transaction rollback if audit storage fails. All 66 mobile and
seven portal tests passed, and the portal production build passed.

- Staff use a different email/UID from their UIABO app account, within the same
  Firebase project. No new Firebase project or environment keys are required.
- `/portal/me` registers and edits staff profiles; `/account/me` registers and
  edits app profiles. Neither endpoint converts an existing account type; the
  separate administrator conversion endpoint is the only supported exception.
- Staff accounts cannot access app allowance, checks, history, feedback or
  self-deletion. App accounts cannot receive staff permissions or use portals.
- System Admin and Data Engineer remain two permissions on the same staff
  account. Revoking both does not turn it into an app account.
- Current live account types were checked read-only. Existing app users and the
  legacy admin remain usable; no combined grants required migration and no live
  user documents were changed during implementation.

## Dual-role portal access

- Login now includes a Data Engineer / System Admin dropdown.
- The backend validates the selected portal and checks membership on each API request.
- `operational_roles` can contain both roles on a separate staff account. Old single-role profiles remain supported.
- The provisioning script accepts `--roles data_engineer system_admin` and adds staff permissions without granting app membership or allowance.
- Profile edits preserve permissions; ordinary clients cannot self-grant roles. Suspension and revocation still block operational access. Audit entries identify the permission used.
- No live user's permissions were changed during implementation. See [portal setup](portal/README.md#grant-portal-access) for the command.

## Staff provisioning and audit history

- System Admin now has **Provision staff** and **Audit history** tabs.
- Staff can register directly in the portal, choose their own password and
  verify their email. Registration creates a staff-only account with no allowance; it does not
  grant a role. The admin grants access by verified email in the portal.
- Find users now includes permission checkboxes, a required reason, concurrent
  edit detection and a shortcut to the account's audit history.
- Self-suspension and self-removal of System Admin access are blocked. Acting
  administrator and target are rechecked together in the transaction to prevent
  simultaneous mutual revocations from removing the final active admin.
- Role changes and their audit details commit together. The read-only history
  has date/action/outcome/user filters and pagination. It resolves current
  account names without retaining them in historical audit documents.
- No live accounts were created, granted permissions, suspended or deleted
  during development. See [portal instructions](portal/README.md#grant-portal-access).

## Account deletion

1. Reject requests from operational accounts and requests while a check has an active reservation.
2. Save a durable deletion job and deactivate the app account in a transaction.
3. Allow five minutes for requests already admitted to settle. The backend worker polls every 30 seconds while the server runs.
4. Disable/revoke Firebase access; delete owned image objects, results, associated run records, feedback, incorrect-result reports, allowance and locks.
5. Delete Firebase Authentication and the profile. Retain a minimal hashed deletion receipt to prevent a late profile request recreating the account.

Cleanup failures leave a retryable job. Restarting the backend resumes pending jobs. No real account was deleted during development tests. Cloud Storage soft-delete/versioning or Firestore backups may retain recoverable copies under the project's configured retention policies; this endpoint removes live application data, not backups. Operational security audits retain pseudonymous identifiers and no submitted claim/image content.

## Webpage extraction deferred

URL-to-text extraction has been removed from the app and backend at the team's request. There is no webpage-text endpoint or extraction dependency in the project requirements. Copy the relevant article text into Check text instead. Check link safety remains available for malicious-link screening. Previously saved webpage-text results remain readable.

## Image storage and maintenance

The existing local storage settings were copied from `uiabo-integration` into this worktree's ignored `.env`: `SAVE_ANALYSIS_IMAGES=1` and the existing bucket name. The original integration changes were preserved.

For confirmed old orphan uploads, run `python -m scripts.cleanup_orphan_images` with the backend environment loaded. It is a dry run by default; `--apply` removes only uploads over one hour old with no matching saved object path/generation. A database read failure aborts cleanup. This maintenance tool was not run against the real bucket.

## Verification

- Evidence preview update (3 November): text results now render Markdown as
  native headings, emphasis, lists, quotations, links and tables. Wide tables
  scroll horizontally, with readable wrapping and column labels for screen
  readers. Remote source images are represented by their captions rather than
  loaded automatically. Source HTML is not executed.
- Existing public-change inference results show a short explanation and an
  expandable **Read the evidence** section with the original quotation and
  publisher link. The credibility note no longer repeats the quotation. Saved
  evidence, scores and verdicts are unchanged; reopening a saved result applies
  the new display. Other result types retain their existing explanations.
- **77 mobile tests passed**, including preservation of table amounts/ranges,
  footnotes, negations, link handling, old-record fallback and unchanged stored
  data. Android export passed. Verified the existing CHAS subsidy result in the
  Pixel 7 emulator: compact explanation, expanded table, bold/italic text and
  horizontal scrolling all work. Expo was restarted with a fresh cache on 8082.
- Groupmates should run `npm ci` in `mobile` after pulling the updated lockfile
  (adds `markdown-it`), then restart Expo. No new `.env` setting is required.

- Text retrieval update (3 November): added disclosed Singapore jurisdiction,
  responsible-agency routing, wrong-country rejection, preserved year-only
  dates, bounded coverage recovery and exact-sentence inference quotations.
  **1,411 backend tests passed, three skipped, no failures.**
- Live diagnostics for the three recent messages used no Firestore writes or
  app allowance. The subsidy message returned **Likely misinformation**; police
  fines and the graduate-unemployment causal claim remained **Not enough
  evidence** because their specific evidence gaps were not filled. An earlier
  overconfident one-statute police verdict was caught and guarded against.
  Model/source selection still varies. See the
  [retrieval diagnostic guide](evaluation/retrieval_scope/README.md) for commands,
  latest observations and limits. These checks are not an accuracy benchmark.

- Saved-image display fix (3 November): the Android native image request still returned 401 after the source-array workaround. Saved images now use the normal authenticated API fetch and an in-memory data URI. Authentication and ownership checks remain enabled; no public storage URLs or URL tokens are created. The native blob is released after conversion, and server/authentication errors are shown instead of a generic failure.
- **70 mobile tests passed** after this fix, covering authenticated image bytes, missing images, authentication failures, invalid/oversized responses and interrupted reads. Reopened the existing deepfake result in the Android emulator: its image was visible and the image endpoint returned **200 OK**. Image-context results use the same component. Expo Go emits a development performance warning for React Native Blob conversion; downloads remain limited to the backend's 10 MB image limit.

- Latest report/demo-checkout update: **1,365 backend tests passed, three live/fixture-dependent tests skipped, no failures**. The four earlier pipeline-default failures are resolved; the test suite no longer loads developer `.env` configuration.
- **66 mobile tests and seven portal tests passed**. Android export and portal production build passed. Tests cover image/link reports and investigation views, protected image access, demo checkout consent/access checks, transaction rollback, concurrent retries and preservation of consumed allowance.
- A real-account checkout/report walkthrough is still an acceptance check. No live user was upgraded, charged or deleted during development testing.

- Separate-account update: 190 targeted account/portal/feedback/history/OCR
  tests passed. The complete suite reported 1,337 passed, two skipped and the
  same four existing claim/retrieval default-configuration failures.
- Four portal tests and 62 mobile tests passed; portal production build and
  Android export passed. Read-only checks against the existing database confirm
  six app accounts, one staff account, no staff allowance, and admin access.
- Live registration/provisioning with a designated test account remains an
  acceptance check; no real user account was created or changed in these tests.

- Staff provisioning update: 126 account/portal/feedback tests passed; four
  portal tests and the production build passed. Firestore audit queries and
  pagination were also checked read-only against the configured project.
- Latest broad backend run: 1,329 passed, two skipped, the same four existing
  claim/retrieval configuration tests failed. No new backend test failures.
- The running portal exposes the new admin tabs. Full staff registration and
  role-grant walkthroughs remain for testing with a designated test account.

- Dual-role update: 103 account, portal and feedback tests passed; all three portal permission/session tests passed. Portal production build passed.
- Latest full backend run: 1,306 passed, two skipped, four existing claim/retrieval default-configuration tests failed. Those failures are outside the portal changes.
- Latest mobile run: 62 tests passed and Android export passed.
- Backend restarted on port 8002; health and the new `/portal/session` schema are available. Portal responds on port 5174. Browser automation was unavailable, so the authenticated dropdown walkthrough remains pending.

- After URL extraction removal: 101 targeted backend tests passed for text analysis, OCR, saved-result access and link safety. API schema inspection confirms the extraction route is absent and historical webpage result types remain readable.
- Earlier full offline backend suite: 1,307 passed, three live-provider tests skipped. The later broad run before URL extraction was removed reported four failures in claim/retrieval tests; those remain outside this removal change.
- Mobile tests: 62 passed after URL extraction was removed, including mocked API transport, password/deletion sequencing, image limits and Android picker recovery. Android export passed. The portal production build passed during the earlier backend work.
- Tests cover ownership, retries, allowance, provider failures, quotation checks, account deletion/recovery and operational access safeguards.
- Live Firebase deletion, live image-provider accuracy and the final authenticated emulator walkthrough remain for acceptance testing. Automated tests do not establish detection accuracy.

Use this worktree for the backend, portal and Expo. No real account was deleted or granted portal permissions during testing.
# Retrieval coverage and numerical evidence — 3 November 2026

The v21 retrieval/assessment update adds:

- Separate current-rule and alleged-announcement searches for policing claims,
  with stronger priority for the actual behaviour and triggering condition.
- Bounded official-document replacements and selective advanced extraction.
- Classified coverage issues. Unrelated/resolved page failures do not by
  themselves block an otherwise eligible public-change inference. Failed searches,
  missing essential coverage and unknown warnings still do.
- Source-bound numerical comparisons for compound claims about doubling, halving,
  tripling or a percentage change. Values, periods, population and measurement
  must be grounded; arithmetic is calculated in code. Negated, qualified and
  forecast comparisons continue through ordinary semantic assessment.
- Separate diagnostics for wrong/missing scope, low confidence, insufficient
  source quality, ungrounded comparisons and missing causal evidence.
- Clearer guidance when a claim omits comparison periods or confuses rates and
  counts. The app does not call every rejected finding a scope mismatch.

No new keys or packages are required. Advanced extraction uses existing Tavily
quota and is capped at two pages per retrieval. Restart the backend and submit a
new check; existing saved assessments are not recalculated. See
[retrieval diagnostic notes](evaluation/retrieval_scope/README.md) for observed
outcomes and remaining chart/source-selection limitations.
