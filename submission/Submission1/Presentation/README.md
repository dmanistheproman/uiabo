# UIABO functionality WBS

Open **UIABO_Functionality_WBS.drawio** in draw.io / diagrams.net to edit the
diagram. All boxes, text and connectors are editable. The file has one widescreen
1920 × 1080 page for the presentation's **Overall Product Hierarchy** requirement.

Use **UIABO_Functionality_WBS.svg** as a scalable image in PowerPoint. It matches
the generated draw.io content. After editing the draw.io file, export a fresh
image from draw.io to keep the slide version consistent.

**UIABO_Functionality_WBS.png** is a 1920 × 1080 preview rendered from the SVG
and can also be inserted directly into PowerPoint.

The six modules follow PTD Section 7.1. Their 28 function groups cover individual
account access, content checking, results, allowances, feedback/administration and
data-engineering functions. Related actions are grouped to keep the slide readable.
For the detailed requirements, use PTD 7.1–7.5 and URS 2.2, pages 6–9.

- **Working / green:** available in the current text prototype, with its existing
  accuracy and operational limitations.
- **Planned / amber with dashed borders:** required or selected product scope
  that is not implemented yet.

Image functions apply to the Premium tier. Static-image deepfake remains required;
audio and video are excluded. The Premium monthly allowance works for enabled
accounts, while subscription payment, renewal and cancellation remain planned.
Administration and data-engineering portal access remain planned even though
individual account access and the backend evidence pipeline are working.

This is a functional decomposition, so connector lines show which functions belong
to each module. They do not show processing order, scheduling or dependencies.

`generate_functionality_wbs.py` reproduces the initial draw.io and SVG files from
the same content. Running it overwrites those outputs; preserve manual edits first.
