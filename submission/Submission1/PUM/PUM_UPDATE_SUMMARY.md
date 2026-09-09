# UIABO PUM update ? 8 September 2026

## Result

The current file is `FYP-26-S3-30_PrelimUserManual_DRAFT.docx`, version 0.2.
It follows the previous team's sample structure and includes only implemented
UIABO functions. No PDF was produced; the existing PDF is unchanged.

| Sample section | UIABO adaptation |
|---|---|
| Cover, Document Control, Table of Contents | UIABO team/project details, dated revision record and refreshed Word contents. |
| 1 Introduction | What the manual covers, reader assumptions, scope and purpose of the working text prototype. |
| 2 Initial Installation Instructions | Current Windows FastAPI/Firebase/provider configuration, then Expo/Android-emulator setup. |
| 3 Key Features | Working account access, text analysis, result/citation display, saved results, sharing, profile-name editing and allowances. |
| 4 Initial GUIs | Sign-in, account creation/verification, errors, recovery, free/Premium Home, text checks, results, history, profile/sign-out, Help and native sharing. |

Only current Android captures are used. The older TDM images, unfinished workflow
instructions and operational-role walkthroughs were removed from this edition.
The real Home screen includes inactive cards; a brief explanation prevents those
cards from being mistaken for working analysis or payment flows.

## Source and verification mapping

| Manual section | Current implementation reference |
|---|---|
| 2 | Repository and mobile READMEs, environment templates, package/requirements files, Firebase loader; earlier PUM installation section. |
| 3 and 4.5?4.6 | HomeScreen.js, account repository and allowance behavior. |
| 4.1?4.4 | AuthScreen.js, VerifyEmailScreen.js, AuthContext.js. |
| 4.7 | TextCheckScreen.js, services/api.js, pipeline input contracts. |
| 4.8 | ResultScreen.js, result contracts and current assessment outputs. |
| 4.9 | ResultsScreen.js, authenticated result routes and owned result store. |
| 4.10 | ProfileScreen.js and AuthContext.js. |
| 4.11?4.12 | InfoScreen.js, SetupScreen.js and ResultScreen.js sharing/source actions. |

Figure 4.1 uses `evaluation/reports/app-integration/home-before-check.png`;
Figure 4.2 uses `home-premium.png`; Figure 4.3 uses `result.png`; Figure 4.4 uses
`history.png`. These are existing 7 September Android captures. Their bytes are
preserved. No fabricated current-screen images or fresh performance claims are
introduced.

The manual has 19 pages, four captures and five editable section files. Numbering,
contents, current-only headings, media preservation, credential exclusion and
unchanged PDF checks passed. Representative pages were rendered directly from
Word. The table layout was adjusted to avoid leaving a single result-definition
row on an otherwise empty page.

Remaining capture, setup, policy and user-validation evidence is recorded in
`PUM_MISSING_INFORMATION.md`. It is separate from the operating instructions.
Original sections remain available; the former combined Word and notes are
backed up locally. Rebuild this edition with `build_implemented_pum.py`, preserving
manual edits first, and refresh fields in Word after edits.
