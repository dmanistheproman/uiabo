# UIABO PUM ? remaining documentation information

Updated 8 September 2026 for the implemented-only Word manual, version 0.2.
These are documentation and evidence gaps. They are not instructions for users
to operate unfinished functions.

| Current location | Missing information or evidence | Treatment in this edition |
|---|---|---|
| 2.1?2.3 Installation | Independent clean-machine setup record and compatibility matrix | Uses the existing Windows/Android-emulator configuration and recorded versions; no fresh-install certification claimed. |
| 2.2 Firebase | Complete reproducible new-project rules/IAM provisioning procedure | Instructions use the team's already configured project and privately supplied credentials. |
| 4.1?4.4 Account access | Current Android captures for sign-in, registration, verification, validation errors and password recovery | Exact actions and labels checked against AuthScreen, VerifyEmailScreen and AuthContext; no design mock-ups substituted. |
| 4.2 Registration | Final privacy notice and accessible policy page | The current checkbox is documented accurately; no separate policy-page workflow is claimed. |
| 4.7 Text checking | Current captures of the input form, progress and error states | Current TextCheckScreen controls and errors are described in text. |
| 4.8 Results | Expanded captures showing all citations, a Not Enough Information outcome and a failed check | Existing result capture retained; other implemented states described from ResultScreen and saved-result contracts. |
| 4.10 Profile | Current captures of profile editing and sign-out confirmation | Name-only editing and exact confirmation controls described from ProfileScreen. |
| 4.11?4.12 Help and sharing | Current Help and Android share-sheet captures; confirmed support contact if one is to be published | Current controls documented; no invented contact address or feedback form. |
| Whole manual | Older-user comprehension/usability study and final team review | Intended audience and usage instructions do not imply completed usability validation. |

## Content reserved for a later manual

As requested, the Word manual omits walkthroughs for direct webpage analysis,
image/caption analysis, OCR, context/deepfake analysis, paid subscription upgrade,
renewal/cancellation, account/history deletion, incorrect-result reports,
reviews, public result links and administrator/data-engineer portals. Document
these only after implementation and verification for the final manual.

The genuine Home captures still show inactive cards and a promotional banner.
The manual explains their current unavailable state briefly so users are not
misled by the screenshot. It gives no instructions for using them. The current
webpage tab's copied-text route is described as text checking, not URL analysis.

Premium account badges and monthly text allowances are implemented and therefore
included. This does not establish a payment or subscription lifecycle.

## Evidence limits

The account, text/result, history, allowance, Help and sharing descriptions were
checked against the current repository code. Four existing Android captures
and prior integration records were reused. No emulator was running during this
revision, so no new screen-capture session or end-to-end execution is claimed.
The existing PDF remains unchanged and has the previous broader scope.
