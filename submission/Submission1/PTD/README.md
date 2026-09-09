# UIABO Preliminary Technical Documentation

The current report is **FYP-26-S3-30_Preliminary_Technical_Documentation.docx**,
version 0.3, dated 8 September 2026. It follows the supplied sample's chapter order
and is the file to use for this revision.

- `PTDParts_Reformatted/`: current editable cover and 19 report chapters.
- `PTD_UPDATE_SUMMARY.md`: chapter mapping and changes made in this revision.
- `PTD_MISSING_INFORMATION.md`: remaining work, with current section references.
- `PTD_DOCUMENT_VALIDATION.json`: structural, preservation and layout checks.
- `restructure_ptd.py`: reproduces this Word structure from the prior section
  inputs and the submitted URS. Requires python-docx, docxcompose and pypdf.

The report begins with Introduction, Overview, Stakeholders and Data Collection,
then follows the sample through planning, requirements, methodology, technical
stack, user stories, use cases, system design, conclusion, glossary and appendix.
The appendix retains testing, meeting minutes and references. The sample skips
Chapter 19; this report uses continuous numbering and places the appendix at 19.

The Word document has 149 pages after contents/page fields were refreshed in
Microsoft Word. All 43 use cases are editable tables; 58 role-specific story
entries and 87 diagrams/screenshots are retained. Representative pages were
rendered directly from Word for review without producing a PDF.

`Preliminary Technical Documentation.pdf` remains the 7 September, 177-page
version. It was intentionally not regenerated for this Word-only request.
`PTDParts_Updated/` holds the previous 18-chapter structure and is an input to the
new builder; `PTDParts/` holds the earlier original sections. Do not run
`update_ptd.py` to rebuild version 0.3: it creates the previous report structure.

Preserve manual edits before running a builder. Rebuilding overwrites the
combined Word report and generated chapter files. After manual edits, update
contents and page fields in Word. The previous combined Word report is backed up
locally under `backups/`; previous-team samples and backups remain local.
