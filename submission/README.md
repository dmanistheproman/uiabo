# UIABO submission documents

This folder contains the UIABO documents added from `C:\Dev\submission` on
7 September 2026. The original local files remain in place; this is the versioned
copy for team review. Changes made to either copy are not automatically synced.

- [PRD](PRD/FYP-26-S3-30_PRD.docx), [URS](URS/FYP-26-S3-30_URS.pdf) and
  [TDM](TDM/FYP-26-S3-30_TDM.pdf): existing team reference documents.
- [Preliminary technical documentation](Submission1/PTD/README.md): updated PDF,
  combined Word document, original section inputs, updated editable chapters,
  comparison summary and remaining gaps.
- [Preliminary user manual](Submission1/PUM/README.md): draft PDF, combined Word
  document, editable sections, illustrations and missing-information notes.

Use the `Submission1` documents for the current preliminary deliverables. They
distinguish implemented prototype behaviour from planned requirements. Previous
teams' samples, redundant older exports, local backups and Word lock files are
excluded. Source references to those local files record comparison provenance.

The Python generators work from this repository layout or the original sibling
folder layout. They require `python-docx`; the PTD also requires `docxcompose`,
and the PUM requires `pypdf` and `Pillow`. Rebuilding overwrites generated Word
documents and sections, so preserve manual edits first. Refresh contents and
page fields in Microsoft Word before exporting a new PDF. The checked-in PDF
exports have already been reviewed; rebuilding is not needed to read or edit
the documents.
