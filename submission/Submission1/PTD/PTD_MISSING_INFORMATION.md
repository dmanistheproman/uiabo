# UIABO PTD — remaining information and work

Updated 7 September 2026. The previous checklist is preserved in `backups/`.
This file matches the updated UIABO PDF and `PTDParts_Updated/`; older section
drafts and historical evaluation reports may describe an earlier implementation.

## Resolved since the previous checklist

- Real claim classification/extraction is connected to Ollama Cloud.
- Real Google Fact Check/Tavily discovery, extraction and scoped search are connected.
- An initial trusted-source catalogue, citation validation and bounded provider failures exist.
- Android text submission, cited results, private history and Firestore ownership are connected.
- Free/Premium allowances, atomic charging and idempotent retries are implemented.
- The latest recorded backend suite is **262 passed**, with Android export and focused live checks.
- Deepfake/static-image detection is required; audio is excluded. It is no longer an unresolved scope question.
- Learning objectives, SWOT, stakeholder coverage, data collection, requirements traceability,
  a WBS, a proposed charter and a glossary have been drafted.
- The requested PDF is compiled as UIABO; the former destination was still a previous-team sample.

## Information and evidence still required

| PTD location | Item | What is still needed |
|---|---|---|
| 2.2, 2.6, 2.8–2.10 | Draft analysis and objectives | Team review of the new learning objectives, measurable acceptance criteria, SWOT and consolidated stakeholder/vision statements. These are proposals, not prior approvals. |
| 5.2, 8.5, 15.4 | Non-functional acceptance | Load tests against 100 concurrent users / 100 requests per minute, UI load/interaction measurements, storage-warning behavior and meaningful latency distributions. Do not report planned numbers as measured results. |
| 5.2, 7.1, 14.5 | Security/privacy/lifecycle | Confirm the 30-minute inactivity rule, final privacy notice/terms, retention/deletion policies, provider-processing arrangements, rules/IAM provisioning, backup/recovery and broader adversarial/access testing. Focused auth/ownership checks are not complete security or compliance certification. |
| 5.8, 6.5–6.6 | Release and deployment | Final build/release version, Android package or distribution link, production HTTPS API if required, supported-device matrix, physical-device checks and clean-machine setup verification. |
| 5.9 | History scaling | Implement an indexed ordered query when needed, arrange required index administration, and verify cursor/performance behavior on larger owned histories. Current backend sorting works but reads all matching user records. |
| 6.3, 8.5–8.6, 14.6 | Assessment accuracy | Completed labelled dataset, independent annotation/reconciliation, held-out metrics and agreed thresholds. Evaluate temporal context, amounts/eligibility, paraphrases, myth quotes and unrelated negation. Retain the recorded Great Wall failure case. |
| 6.6, 10.2, 16.1 | Required image/deepfake delivery | Named owners/dates, chosen detector and OCR/context services, supported formats/size limits, implemented pipelines, failure behavior and detector-specific evaluation. |
| 1.1, 15.4 | Direct webpage analysis | Implement and test public-page retrieval, malicious-link screening and clear unsupported/inaccessible-page handling. Current copied-text checking is not the completed link feature. |
| 1.1, 15.4 | Remaining consumer/operational features | Payments/renewal/cancellation; account/history deletion; reports/reviews; public result links; system-administrator and data-engineer portals. Confirm delivery priority without treating required features as completed. |
| 6.5, 9.2 | Project website / portal | Decide whether a website is an assessed deliverable. If required, provide deployment address, purpose, hosting and screenshots. A private source repository is not a public product website. |
| 8.5 | Older-user usability | Participant/recruitment basis, consent/review process as applicable, tasks, comprehension/accessibility results and changes made after testing. No interviews or study results are inferred from intended audience descriptions. |
| 9.3–9.4, 16 | Management process and charter | Confirm communication cadence, escalation, revision and acceptance process. Add real approvals/signatures only if they exist. No committed budget has been provided. |
| 10 | Final dates and schedule | Confirm the exact November 2026 submission deadline, remaining sprint dates, named owners and rebaselined Gantt/WBS. September 12 is the user-provided prototype deadline. |
| 11 | Contribution record | Reconcile component ownership with actual repository contributions, integration fixes and reassigned live retrieval work. Do not attribute all work to an original owner by default. |
| 12 | Official minutes | Meeting date/time/location, chair/minute taker, attendees/absences, decisions, owner/deadline, supervisor feedback and next meeting. The technical progress reports are not substitutes for these records. |
| 13 | Final references | Review the final reference style and refresh time-sensitive market claims if the team intends to present them as current rather than dated PRD research. |

## Important distinctions for the report

- **Operational success is not accuracy.** Live requests returning results, 262 passing
  tests and successful Android export do not establish factual-verdict accuracy.
- **A completed NEI result consumes allowance.** A failed server run does not. A client
  timeout can occur after server completion; inspect saved history before retrying.
- **Premium grant is not billing.** The current 60-check calendar-month entitlement
  does not prove paid subscription, renewal or cancellation behavior. Align paid
  billing periods with the final allowance policy when implemented.
- **Framework minimums are not device validation.** Expo SDK 57 documentation gives
  platform prerequisites; the UIABO device/performance test matrix remains incomplete.
- **Historical minutes stay historical.** The August scope-sensitive deepfake note is
  annotated with the later requirement clarification, not rewritten as an old approval.

## Final document review

- Confirm the copied cover details against final institutional requirements.
- Review the new proposed content and outstanding decisions above.
- Keep the combined Word source and updated section files consistent after edits.
- Update the automatic contents and page numbers, export and inspect the final PDF.
- Keep the sample PDFs, API secrets and service-account contents out of submission content.
