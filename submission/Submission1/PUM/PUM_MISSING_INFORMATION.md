# UIABO preliminary user manual — missing information and decisions

Prepared 7 September 2026. This checklist belongs to the new UIABO PUM draft;
it does not modify the previous team's sample or the existing PTD.

Most overview and feature material was available in the PTD, PRD, URS and TDM.
Missing facts have not been invented. Proposed features with documented use cases
have been described as proposed, rather than left out or presented as working.

## Information not available in the submission documents

| ID | PUM section | Missing information | What to supply |
|---|---|---|---|
| G01 | 2.1–2.3 Installation | Final distribution and access details | The approved checkout/release reference, installation package or download link, production API URL, and any assessor-specific access instructions. The current draft uses the existing local emulator setup. |
| G02 | 2.1 Prerequisites | Validated minimum device and software requirements | Supported Android/API level, minimum RAM/storage, clean-machine Python/Node compatibility and required Expo Go/build version. Current installed versions are recorded as observations, not minimum requirements. |
| G03 | 2.2 Firebase setup | Complete reproducible provisioning for a new Firebase project | Approved Firestore rules, required IAM permissions, deployment steps, indexes actually used and a safe demonstration-account provisioning procedure. The existing project's working configuration is not a complete new-project setup guide. Do not supply secrets in this manual. |
| G04 | 4.2.2, 4.16 Privacy, terms and help | Final team-approved privacy notice, terms and support route | Published text/location, consent flow, support email or contact page and any response expectations. A consent checkbox exists; it does not establish that full linked legal documents exist. The previous team's terms cannot be reused as UIABO policy. |
| G05 | 4.1–4.4, 4.7–4.8, 4.11, 4.16 GUI captures | Complete current-build screenshot set | Sign-in, registration, email verification, validation errors, password reset, text entry/progress/error, unavailable link screen, Profile, Help and native Share. Existing current captures cover Premium Home, saved history and one saved result. TDM mock-ups are used where available and labelled as designs. |
| G06 | 4.12 Subscription | Final commercial and payment decisions | Chosen payment provider, approved price, checkout flow, activation, renewal, cancellation, expiry and billing-period rules. TDM illustrates SGD 20/month; PTD says the price needs validation. A manually granted Premium account is not a paid subscription. |
| G07 | 4.13 Image tools | Implemented image input limits and provider behavior | Supported formats, upload-size/resolution limits, permissions, OCR service, context-analysis service, required deepfake detector, supported outputs and meaningful failure messages. Illustrative mock-up hints are not validated implementation limits. |
| G08 | 4.14–4.15 Operational portal | Actual portal deployment and operating instructions | Portal URL, operational account onboarding, final field/control names, permissions, report states, supported recovery actions and screenshots. Proposed TDM dashboards provide design material only. |
| G09 | 4.10.1, 4.11.1, 4.16.2–4.16.4 | Final retention, deletion, reporting and public-sharing behavior | Implemented account/history deletion, retention rules, report/review forms, shared-link visibility and lifecycle, and related confirmations. Do not borrow the sample's public reviews, likes, real-estate listings or property-agent workflow. |
| G10 | Document Control / final review | Completed review and final submission metadata | Actual reviewers, review dates, approval and final document version. Only the initial draft revision has been recorded. November's exact final-submission date has not been supplied; it is not required to explain the current prototype. |
| G11 | 3.2 and 4.9 Results | Accuracy and usability evidence sufficient for stronger user-facing claims | A labelled assessment evaluation, misleading/incorrect-result analysis and user testing. Current operational tests do not establish accuracy. No guaranteed accuracy percentage, detection rate or validated probability is claimed. |

## Existing material used to fill gaps in the submitted documents

These items were absent as usable installation or operating instructions in the
submission PDFs, but could be filled from the local implementation. They are not
left blank in the manual:

- Backend environment-variable names, virtual-environment commands and Uvicorn launch command.
- Expo launch instructions, Firebase Web configuration fields and emulator host addresses.
- Current free registration, verification-link and password-reset behavior.
- Current display-name editing, read-only email/role and sign-out confirmation.
- Current text limit, result history, interrupted-request guidance and native sharing.
- Current free daily and Premium calendar-month allowance reset behavior.

Sources: `C:/Dev/uiabo/README.md`, `mobile/README.md`, configuration templates,
package/requirements files, account/analysis implementations and mobile screens.
The source map lists the exact relevant files. Installation documentation was
checked against these files; this task did not reinstall or provision a new system.

## Differences requiring a team decision or future implementation

| Topic | Submitted design | Current prototype / PUM treatment |
|---|---|---|
| Prototype breadth | URS uses “initial prototype” for text, public links and static images. | The user narrowed the September prototype to basic Sprint 1. Current working flow is text. Link/image designs remain in the PUM, labelled proposed. Deepfake is still required for the project; audio is excluded. |
| Direct Firestore access | Some PTD development-tool wording describes direct client Firestore access. | The working result/history flow goes through authenticated FastAPI endpoints. Installation and operating instructions follow that implementation. |
| Client HTTP library | PTD/TDM describe Axios. | The current app uses fetch. Users do not need an Axios installation step. |
| Registration | TDM shows Free/Premium selection and continuation to payment. | Current app creates a free account with password confirmation, then verifies email through a link. No OTP or paid registration is claimed. |
| Premium price and period | TDM shows SGD 20/month; URS describes paid subscription expiry/renewal periods. | Price is marked proposed. Current project-granted Premium resets on the first day of the calendar month. Billing alignment remains undecided. |
| Interrupted requests | URS broadly says failed/cancelled/timed-out analyses should not use allowance. | A failed server analysis does not charge. A client timeout may occur after a successful server completion; that completed result does charge. The manual tells users to check Results before resubmitting. There is no working cancellation control during analysis. |
| Sharing | URS UC-15 specifies a public result link. | Current Android Share sends summary text and citation URLs. The manual explicitly identifies the public result-link feature as planned. |
| Session behavior | URS specifies expiry after 30 minutes of inactivity. | No verified implementation of that inactivity rule was established. The manual does not promise it. Align requirements and implementation before release. |
| Account/history controls | URS includes account deletion, history deletion, reviews and reports. | These controls remain planned. Name editing, history viewing and text/source sharing are available. |
| Initial GUI artwork | TDM includes example user names, scores, balances, payments and portal metrics. | These are labelled illustrative designs. They are not evaluation findings, actual subscriber payments or operational statistics. |

## Material intentionally excluded from the sample

Property price predictions, PostgreSQL/PostGIS setup, Flask configuration, estate
agents, CEA licences, property listings, property comparisons, bookmarks and
real-estate marketing content are specific to the previous team. They have been
replaced with the corresponding UIABO functions rather than renamed superficially.

PTD-only sections such as competitor comparisons, risk analysis, team meeting
minutes and the full project schedule are not separate PUM chapters because the
sample PUM contains only Introduction, Installation, Key Features and Initial GUIs.
Useful project overview, audience, feature and technical-stack content was reused.

## Before submission

- Review the cover details copied from the PTD/URS; they are present, not missing.
- Confirm which proposed GUI sections the assessor expects in the preliminary manual.
- Replace design figures with tested-build captures as the corresponding work is completed.
- Fill the missing information above; do not remove an unavailable-feature label until verified.
- Edit the individual Word sections or combined draft consistently. If rebuilding with the
  generator, first preserve any hand edits; generated files will be replaced.
- Refresh the combined Word contents and page fields after further edits, then re-export the PDF.
