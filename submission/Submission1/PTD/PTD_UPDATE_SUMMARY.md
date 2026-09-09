# UIABO PTD structure revision ? 8 September 2026

## Current output

**FYP-26-S3-30_Preliminary_Technical_Documentation.docx**, version 0.3, is the
current report. It has been reorganized to follow the report format of
`FYP-26-S2-XX_PrelimTechDocs.pdf`, adapted throughout to UIABO.

The previous revision covered the sample's topics while retaining an older
UIABO chapter structure. This revision follows the sample's chapter sequence
and most subsection groupings instead. The existing PDF is unchanged as requested.

## Chapter structure and source mapping

| Current chapter | Main reused source and treatment |
|---|---|
| 1. Introduction | Previous overview: problem, purpose, vision and objectives, with learning objectives retained. |
| 2. Overview | PRD competitor research, comparison matrix, concept rationale, SWOT, differentiators, users and business model. |
| 3. Stakeholders | Consolidated stakeholders, original team roles and current Sprint 1 ownership record. |
| 4. Data Collection | Previous data/evidence chapter moved forward: sources, types, methods, preprocessing, privacy and evaluation dataset plan. |
| 5. Project Timeline | Milestones, original Gantt, WBS, proposed charter, communication management and scope statement grouped as in the sample. |
| 6. Requirement Definition | Stakeholder identification, gathering methods, analysis, needs, tools, traceability and acceptance. |
| 7. Functional Requirements | Functional hierarchy, detailed baseline requirements, access levels, dependencies, inputs/outputs and current implementation status. |
| 8. Non-functional Requirements | Original performance, security, usability, capacity and storage requirements; targets remain distinct from measurements. |
| 9. Other Requirements | Existing user/environment, privacy, source-reuse and operating constraints; unresolved compliance review remains explicit. |
| 10. Risk Management | Original risk register and observed current mitigation/follow-up record. |
| 11. Development Methodologies | Existing Waterfall, Prototyping, Kanban and Scrum discussion and figures. |
| 12. Technical Stack | Frontend, backend, database, AI components, APIs, hosting, server and deployment in the sample's order. |
| 13. User Stories | All 58 role-specific story entries transcribed into editable text from URS pages 15, 34, 44 and 57. Shared IDs remain shared. |
| 14. Use Case Descriptions | All 43 URS descriptions converted from facsimile pages into editable tables. Names, IDs, goals, descriptions, actors, triggers, preconditions, main flows, sub-flows and alternatives are preserved. |
| 15. Use Case Diagram | Four original URS role diagrams: free, premium, system administrator and data engineer. |
| 16. System Design | Original data-flow, architecture, database and wireframe material, followed by sequence/activity diagrams and current authentication/persistence design. |
| 17. Conclusion | Existing completion summary and remaining deliverables. |
| 18. Glossary | Existing UIABO definitions. |
| 19. Appendix | Dated test summary, actual meeting records, references and project-website/submission status. |

The sample numbers its appendix as 20 after 18. UIABO uses 19 to avoid reproducing
that numbering gap. The real-estate Property Agent role is replaced by UIABO's
Data Engineer where role-based organization is useful. Unregistered access is
explained using the existing registration/recovery cases; no additional role
diagram or new approved use-case ID is invented.

## Formatting and preservation

- Cover, contents, document control, numbered chapters/subsections and continuous
  page numbers provide the same broad academic-report format as the sample.
- The report uses consistent Arial body text and bold black numbered headings.
  Existing UIABO table formatting and original design figures are retained.
- The automatic Word contents and page fields were refreshed. There are 149 pages
  and no empty pages in the Word pagination check.
- All 43 use-case tables were compared field by field with the submitted URS text.
- All 87 remaining diagram/screenshot media files were checked against the source
  sections. The old report's 49 rasterized story/description/introduction pages
  were replaced by editable text and tables rather than repeated as images.
- The previous combined Word document and previous revision notes are preserved
  in local `backups/`. Original `PTDParts/` and `PTDParts_Updated/` are unchanged.
- The existing PDF hash was checked before and after the revision: unchanged.
- Provider-key scanning found no live credentials in the revised report.

## Evidence boundaries

The current text pipeline, Android flow, Firestore ownership and allowance
behavior remain documented. Recorded tests and known assessment errors retain
their original dates and limitations. Reformatting is not a new implementation
or accuracy evaluation. Deepfake/static-image detection remains required; audio
and video remain excluded. The prototype date is 12 September 2026, and the exact
November final-submission date is still unknown.

Current functionality, planned functions and proposed management material remain
distinct. No interviews, formal approvals, paid billing, detector implementation
or individual contribution percentages are invented. The companion gap list has
been remapped to the new chapter numbers.

## Editing

Edit the combined Word document or the corresponding files in
`PTDParts_Reformatted/`, keeping those copies consistent. `restructure_ptd.py`
rebuilds from the prior read-only sections and URS, so preserve manual edits
before running it. Refresh contents and page fields after edits. No new PDF is
required for this revision.
