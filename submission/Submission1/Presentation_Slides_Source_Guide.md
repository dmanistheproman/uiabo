# UIABO presentation slide sources

- **Main reference:** updated PTD Word chapters linked below.
- **Section numbers:** refer to the 8 September Word version; the PTD PDF uses the older structure.

## 1. Product Objectives

- **Open:** [PTD - Introduction](PTD/PTDParts_Reformatted/01_Introduction.docx).
- **Go to:** **1.4 Project Objectives**.
- **Points to take:**
  - Complete text-checking journey.
  - Traceable evidence and citations.
  - Better assessment quality.
  - Image-checking functions.
  - Accessible user experience.
- **Background:** **1.1-1.3** for the problem, purpose and vision.
- **Original source:** [PRD](../PRD/FYP-26-S3-30_PRD.docx), **1.1 Overview**, **1.2 Project Scope**, **2. Project Motivation**.
- **Note:** **1.5 Learning Objectives** covers team learning, rather than product goals.

## 2. Research Summary

- **Open:** [PTD - Overview](PTD/PTDParts_Reformatted/02_Overview.docx).
- **Go to:** **2.1.2 Research Findings and Analysis**.
- **Products reviewed:** Full Fact AI, Factiverse, NewsGuard, Google Fact Check Explorer and InVID-WeVerify.
- **Points to take:**
  - What needs these products address.
  - What gaps the team identified.
  - How those gaps motivated UIABO.
- **Supporting sections:** **2.1.1** for context; **2.3 Conceptualization of Ideas** for UIABO's approach.
- **Original source:** [PRD](../PRD/FYP-26-S3-30_PRD.docx), **1.3 Research Finding Analysis**, especially **1.3.3**.
- **Note:** describe the team's documented research; competitor capabilities have not been rechecked for this guide.

## 3. Similar Product Comparison

- **Open:** [PTD - Overview](PTD/PTDParts_Reformatted/02_Overview.docx).
- **Go to:** **2.2 Product Comparison Matrix** ? comparison spans two tables.
- **Suggested comparison rows:**
  - Claim analysis.
  - Evidence retrieval and citations.
  - Handling uncertainty.
  - Image verification.
- **Original source:** [PRD](../PRD/FYP-26-S3-30_PRD.docx), **1.3.2 Product Comparison**.
- **Check:** use the matrix's definitions of **Yes / Partial / No**.
- **Update UIABO's status:** check [PTD 7.5 Current Implementation Status](PTD/PTDParts_Reformatted/07_Functional_Requirements.docx); the older matrix labels some now-working functions as planned.

## 4. Unique Selling Point of the Proposed Product

- **Open:** [PTD - Overview](PTD/PTDParts_Reformatted/02_Overview.docx).
- **Go to:** **2.5 Unique Selling Point**.
- **Points to take:**
  - Accessible checking for older Android users.
  - Claim-based evidence and citations.
  - Readable results with explicit uncertainty.
  - Separate factual checking and image-authenticity checking.
- **Original source:** [PRD](../PRD/FYP-26-S3-30_PRD.docx), **1.5 Business Model ? Value Proposition** and **1.3.4 Selected Scope for uiabo**.
- **Note:** label image functions as planned; higher accuracy than competitors has not been established.

## 5. Overall Product Hierarchy / Functionality WBS

- **Edit the diagram:** [draw.io WBS](Presentation/UIABO_Functionality_WBS.drawio).
- **Insert into PowerPoint:** [SVG image](Presentation/UIABO_Functionality_WBS.svg) or [PNG image](Presentation/UIABO_Functionality_WBS.png).
- **Six modules shown:**
  - Account access.
  - Content checking.
  - Results and evidence.
  - Allowances and plans.
  - Feedback and administration.
  - Data engineering.
- **Status:** working and planned functions are marked in the diagram.
- **Main source:** [PTD - Functional Requirements](PTD/PTDParts_Reformatted/07_Functional_Requirements.docx), **7.1 Functional Hierarchy** and **7.2 Basic Feature Access Levels**.
- **Original diagram:** [URS](../URS/FYP-26-S3-30_URS.pdf), **page 6, 2.2 Product Features**; details on **pages 7-9**.
- **URS roles:** Free User, Premium User, System Administrator and Data Engineer.
- **Use for this slide:** product functions. PTD **5.3 Work Breakdown Structure** also includes project tasks such as documentation and evaluation.

## 6. Development Tools Chosen

- **Open:** [PTD - Technical Stack](PTD/PTDParts_Reformatted/12_Technical_Stack.docx).
- **Tools and sections:**
  - **12.1 Frontend Framework:** JavaScript, React Native and Expo.
  - **12.2 Backend Framework:** Python, FastAPI and Uvicorn.
  - **12.3 Database:** Cloud Firestore.
  - **12.4 Machine Learning Libraries and Analysis Components:** Ollama Cloud and analysis components.
  - **12.5 APIs:** Firebase Authentication, Google Fact Check and Tavily.
- **For each tool:** give its name, purpose and one reason for choosing it.
- **Original sources:** [PRD](../PRD/FYP-26-S3-30_PRD.docx), **5. Development Tools**; [TDM](../TDM/FYP-26-S3-30_TDM.pdf), **3.1 System Environment**.
- **Note:** use the updated PTD for current providers and implementation.

## 7. Development Methodology Chosen

- **Open:** [PTD - Development Methodologies](PTD/PTDParts_Reformatted/11_Development_Methodologies.docx).
- **Go to:** **11.5 Development Methodology Chosen: Scrum**.
- **Points to take:**
  - Why Scrum suits the project.
  - Sprint cycle: select backlog tasks ? develop and test ? review ? adjust the next sprint.
  - How prototyping and Kanban support Scrum.
- **Alternative methods:** earlier sections of Chapter 11 compare Waterfall, Prototyping and Kanban.
- **Original source:** [PRD](../PRD/FYP-26-S3-30_PRD.docx), **4.2.1 Development Methodology Chosen: Scrum**, including the justification and proposed use.
- **Note:** distinguish the proposed process from practices the team has actually followed.

## Final slide checks

- **Planned features:** label unfinished functions as planned.
- **Working demo:** check [PTD 7.5](PTD/PTDParts_Reformatted/07_Functional_Requirements.docx) and the [implemented-only PUM](PUM/FYP-26-S3-30_PrelimUserManual_DRAFT.docx).
- **Slide notes:** record the source document and section number.
- **Research citations:** use [PTD 19.3 References](PTD/PTDParts_Reformatted/19_Appendix.docx) and the PRD reference list.
- **Source locations checked:** 8 September 2026.
