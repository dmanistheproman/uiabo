# UIABO PUM — source map and adaptation notes

The supplied previous-team sample is
`../FYP-26-S2-XX_PrelimUserManual.pdf` (33 PDF pages). It supplies the four-part
structure, document-control layout and screen-tour approach, not UIABO facts.

## Authoritative team documents

Paths below are relative to `C:/Dev/submission`.

- **PTD:** `Submission1/PTD/PTDParts/` — editable team adaptations, especially
  `00_Cover_and_Contents.docx`, `01_Product_Functionality_Overview.docx`,
  `02_Project_Overview.docx`, `05_Project_Design.docx`, `06_Project_Implementation.docx`.
- **PRD:** `PRD/FYP-26-S3-30_PRD.docx` — title/team, scope, overview and business model.
- **URS:** `URS/FYP-26-S3-30_URS.pdf` — user roles, constraints and UC-01 through UC-43.
- **TDM:** `TDM/FYP-26-S3-30_TDM.pdf` — environment and proposed UI figures.

The existing PTD missing-information file predates the completed text integration.
Its older claims that retrieval and mobile history are unfinished were not copied
as the current status. This PUM has its own dated gap list.

## Section mapping

| PUM section / output | Reused team material | Adaptation / complementary source |
|---|---|---|
| 00 Cover, Document Control and Contents | PTD cover; PRD cover; URS cover and 1.2 | Correct UIABO team, CSIT-26-S3-30 topic, FYP-26-S3-30 group, supervisor and assessor. New draft revision only; sample team's revision history excluded. |
| 1 Introduction | PTD 1, 2.1 and 2.3; PRD 1.2 and 1.4; URS 1, 2.1, 2.3–2.7 | User-oriented scope, target readers and reading guidance; user-confirmed Sprint 1 text prototype, deepfake required, audio excluded. |
| 2 Installation | PTD 6.2; TDM 3.1/7.10; URS 2.4–2.5 | Submitted documents explain the stack but not a runnable setup. Commands, placeholders and current versions come from the repository files listed below. G01–G03 record what is still missing. |
| 3 Key Features | PTD 1 and 2; PRD 1.2/1.4/1.5; URS 2.2–2.3 and UC-10/11/24 | Feature/role tables, result meanings and current/proposed status distinction. |
| 4.1 Sign-in | URS UC-01/04; TDM 6.1, PDF p. 56 | Current control wording from AuthScreen; proposed TDM login image. |
| 4.2 Registration/verification | URS UC-16/18; TDM 6.1, PDF p. 56 | Current free-account form, eight-character minimum, password confirmation and email link. Payment design clearly qualified. |
| 4.3 Sign-in errors / 4.4 Recovery | URS UC-01 alternatives and UC-04 | Current app messages and neutral reset confirmation. No separate submission GUI captures found. |
| 4.5 Free Home | PTD 1/2.4; URS UC-07/08/11; TDM 6.2, PDF p. 57 | Six-card design retained, audio excluded, current availability stated. |
| 4.6 Premium Home | URS 2.3/UC-11; TDM 6.3 | Current Android capture and implemented monthly allowance; no invented payment. |
| 4.7 Text | URS UC-07; TDM 6.2, PDF p. 57 | Current Check this text control, 5,000-character limit and safe retry guidance. |
| 4.8 Webpage | URS UC-08, 2.4–2.5; TDM 6.2, PDF p. 57 | Proposed direct-link workflow; current copied-text alternative explicitly identified. |
| 4.9 Results | URS UC-10; TDM 6.2, PDF p. 58 | Current Android capture; explain risk/uncertainty, null score for NEI and separate image-authenticity output. |
| 4.10 History | URS UC-09/10/12; TDM 6.2, PDF p. 58 | Current history capture; deletion/report filters marked planned. |
| 4.11 Profile | URS UC-02/03/05/06 | Current name-only edit, read-only email/tier, sign-out; account deletion remains proposed. |
| 4.12 Subscription | PTD 2.4; URS UC-17–20; TDM 6.2–6.3, PDF pp. 58/60 | Proposed SGD 20 figure distinguished from approved price and working billing. G06 covers remaining decisions. |
| 4.13 Images | PTD 1/2.1; URS UC-21–24; TDM 6.3, PDF pp. 59–60 | Four proposed workflows and figures, including required deepfake. Formats/limits/detector details not invented. |
| 4.14 Administrator | URS UC-25–35; TDM 6.4, PDF pp. 61–62 | Proposed dashboard, account management, operational account creation and feedback review. |
| 4.15 Data engineer | URS UC-36–43; TDM 6.5, PDF pp. 63–64 | Proposed report investigation and pipeline monitoring with provenance. |
| 4.16 Help/share/feedback | URS 2.6 and UC-13–15 | Current Help and Android Share; reports/reviews/public result links remain proposed. Missing consumer forms and support details logged. |

**Page convention:** TDM physical PDF pages 56–64 correspond to printed pages
53–61. The manual uses physical PDF page references to avoid ambiguity.

## Implementation sources used only to clarify current behavior

All paths below are relative to `C:/Dev/uiabo`:

- `README.md`, `mobile/README.md`, `.env.instructions`, `mobile/.env.example`.
- `backend/requirements.txt`, `mobile/package.json`, `mobile/package-lock.json`.
- `backend/app/firebase.py`, `backend/app/accounts/repository.py`,
  `backend/app/analyses/store.py`, `backend/app/routers/analysis.py`.
- `mobile/App.js`, `mobile/src/services/api.js`, `mobile/src/auth/AuthContext.js`.
- `mobile/src/screens/AuthScreen.js`, `VerifyEmailScreen.js`, `HomeScreen.js`,
  `TextCheckScreen.js`, `ResultsScreen.js`, `ResultScreen.js`, `ProfileScreen.js`,
  `InfoScreen.js`.
- `evaluation/reports/app-integration/README.md` and its existing emulator captures.

Python 3.14.3 and Node v24.14.0 were read from the current environment during this
task. They are not a validated minimum-version policy.

## Figure provenance

- `../assets/TDM_pdfNNN_figureNN.png`: extracted unchanged from the submitted TDM's
  embedded images. These are proposed designs, including illustrative names,
  balances, scores, dates and portal metrics.
- `../assets/current_home_premium.png`: copy of the existing `home-premium.png`
  Android integration capture.
- `../assets/current_history.png`: copy of the existing `history.png` capture.
- `../assets/current_result.png`: copy of the existing `result.png` capture.
- The small floating developer control in current captures belongs to the Expo
  development environment. Current result captures illustrate UI, not assessment accuracy.

No previous team's real-estate screenshots were reused. No API secrets, login
passwords or service-account contents were inserted into the document.

## Outputs and editing

The five section files are editable Word documents. The combined Word draft uses
the same content and includes a page-numbered table of contents after Word updates
its fields. The PDF is a review copy of that draft, not a claim of final approval.

The separate `../PUM_MISSING_INFORMATION.md` records missing facts and differences.
The generator `../build_pum_sections.py` supports rebuilding the draft, but it will
overwrite generated Word files; preserve manual edits before rerunning it.
