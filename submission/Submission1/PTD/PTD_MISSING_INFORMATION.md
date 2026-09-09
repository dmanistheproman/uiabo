# UIABO PTD — remaining information and work

Updated 8 September 2026 for the sample-aligned Word report (version 0.3).
Use the combined Word document and `PTDParts_Reformatted/`. The existing PDF and
`PTDParts_Updated/` retain the 7 September structure; no new PDF was requested.
Historical evaluation reports may describe an earlier implementation.

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
| 8, 6.6, 19.1.5 | Non-functional acceptance | Load tests against 100 concurrent users / 100 requests per minute, UI load/interaction measurements, storage-warning behavior and meaningful latency distributions. Do not report planned numbers as measured results. |
| 8.2, 10.1, 4.5, 9.2 | Security/privacy/lifecycle | Confirm the 30-minute inactivity rule, final privacy notice/terms, retention/deletion policies, provider-processing arrangements, rules/IAM provisioning, backup/recovery and broader adversarial/access testing. Focused auth/ownership checks are not complete security or compliance certification. |
| 5.8, 6.5–6.6 | Release and deployment | Final build/release version, Android package or distribution link, production HTTPS API if required, supported-device matrix, physical-device checks and clean-machine setup verification. |
| 16.7 | History scaling | Implement an indexed ordered query when needed, arrange required index administration, and verify cursor/performance behavior on larger owned histories. Current backend sorting works but reads all matching user records. |
| 6.3, 8.5–8.6, 14.6 | Assessment accuracy | Completed labelled dataset, independent annotation/reconciliation, held-out metrics and agreed thresholds. Evaluate temporal context, amounts/eligibility, paraphrases, myth quotes and unrelated negation. Retain the recorded Great Wall failure case. |
| 12.8.1, 5.3, 5.6 | Required image/deepfake delivery | Named owners/dates, chosen detector and OCR/context services, supported formats/size limits, implemented pipelines, failure behavior and detector-specific evaluation. |
| 7.5, 6.6 | Direct webpage analysis | Implement and test public-page retrieval, malicious-link screening and clear unsupported/inaccessible-page handling. Current copied-text checking is not the completed link feature. |
| 7.5, 6.6 | Remaining consumer/operational features | Payments/renewal/cancellation; account/history deletion; reports/reviews; public result links; system-administrator and data-engineer portals. Confirm delivery priority without treating required features as completed. |
| 12.6?12.8, 19.4 | Project website / portal | Decide whether a website is an assessed deliverable. If required, provide deployment address, purpose, hosting and screenshots. A private source repository is not a public product website. |
| 8.3, 19.1.5 | Older-user usability | Participant/recruitment basis, consent/review process as applicable, tasks, comprehension/accessibility results and changes made after testing. No interviews or study results are inferred from intended audience descriptions. |
| 9.3–9.4, 16 | Management process and charter | Confirm communication cadence, escalation, revision and acceptance process. Add real approvals/signatures only if they exist. No committed budget has been provided. |
| 5 | Final dates and schedule | Confirm the exact November 2026 submission deadline, remaining sprint dates, named owners and rebaselined Gantt/WBS. September 12 is the user-provided prototype deadline. |
| 3.2?3.3 | Contribution record | Reconcile component ownership with actual repository contributions, integration fixes and reassigned live retrieval work. Do not attribute all work to an original owner by default. |
| 19.2 | Official minutes | Meeting date/time/location, chair/minute taker, attendees/absences, decisions, owner/deadline, supervisor feedback and next meeting. The technical progress reports are not substitutes for these records. |
| 19.3 | Final references | Review the final reference style and refresh time-sensitive market claims if the team intends to present them as current rather than dated PRD research. |

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
- Refresh automatic contents and page numbers after edits. This revision is Word-only; export a new PDF only when it is needed for submission.
- Keep the sample PDFs, API secrets and service-account contents out of submission content.
