# UIABO APIs and services

Reference for the currently implemented features. Updated 17 September 2026.

For installation and startup instructions, follow the [teammate setup guide](TEAMMATE_SETUP.md).

## Overview

| API / service | Purpose in UIABO | Credentials needed |
| --- | --- | --- |
| Ollama Cloud | Claim classification, extraction, evidence relevance and assessment | `OLLAMA_API_KEY` |
| Google Fact Check Tools API | Finding existing published fact-checks | `GOOGLE_FACT_CHECK_API_KEY` |
| Tavily Search and Extract | Searching for evidence and extracting webpage text | `TAVILY_API_KEY` |
| Google Web Risk Lookup API | Screening links for known phishing, malware and unwanted software | `WEB_RISK_API_KEY` |
| Firebase Authentication | Registration, login and identity verification | Firebase app configuration and backend Admin credentials |
| Cloud Firestore | Saving accounts, Premium status, allowances and assessment history | Same Firebase project and backend Admin credentials |
| NEA/MSS four-day forecast API | Comparing Singapore temperature claims with official forecasts | No key needed for the current integration |

## Links and setup

### 1. Ollama Cloud

- [Documentation](https://docs.ollama.com/cloud)
- [Create or manage API keys](https://ollama.com/settings/keys)
- Configuration: `OLLAMA_API_KEY`.
- The current pipeline uses cloud models; a local Ollama installation is not required.

### 2. Google Fact Check Tools API

- [Documentation](https://developers.google.com/fact-check/tools/api)
- [Enable the API in Google Cloud](https://console.cloud.google.com/apis/library/factchecktools.googleapis.com)
- [Manage Google Cloud credentials](https://console.cloud.google.com/apis/credentials)
- Configuration: `GOOGLE_FACT_CHECK_API_KEY`.
- UIABO uses claim search to discover published fact-checks.

### 3. Tavily Search and Extract

- [Quickstart](https://docs.tavily.com/documentation/quickstart)
- [Create or manage API keys](https://app.tavily.com/)
- [Search API documentation](https://docs.tavily.com/documentation/api-reference/endpoint/search)
- [Extract API documentation](https://docs.tavily.com/documentation/api-reference/endpoint/extract)
- Configuration: `TAVILY_API_KEY`.
- One key covers both search and extraction.

### 4. Google Web Risk Lookup API

- [Documentation](https://docs.cloud.google.com/web-risk/docs/lookup-api)
- [Enable the API in Google Cloud](https://console.cloud.google.com/apis/library/webrisk.googleapis.com)
- [Manage Google Cloud credentials](https://console.cloud.google.com/apis/credentials)
- Configuration: `WEB_RISK_API_KEY`.
- Used by **Check link safety**. It checks known security threats, not whether a webpage's claims are true.
- [Project setup instructions](backend/WEB_RISK_SETUP.md)

### 5. Firebase Authentication

- [Documentation](https://firebase.google.com/docs/auth)
- [Firebase Console](https://console.firebase.google.com/)
- Uses the mobile app's Firebase configuration and the backend's Firebase Admin credentials.
- Handles registration, login and identity verification.

### 6. Cloud Firestore

- [Documentation](https://firebase.google.com/docs/firestore)
- [Firebase Console](https://console.firebase.google.com/)
- Uses the same Firebase project as Authentication.
- The backend uses Admin credentials, rather than a separate Firestore API key.
- Stores account details, Premium status, usage allowances and saved results.

### 7. NEA/MSS four-day forecast API

- [Dataset and API information](https://data.gov.sg/datasets/d_f131f6e343bf8168e4057a04c4326a0a/view)
- [Live API endpoint](https://api-open.data.gov.sg/v2/real-time/api/four-day-outlook)
- [Readable MSS forecast page](https://www.weather.gov.sg/weather-forecast-4dayoutlook/)
- No API key is used by the current integration.
- The structured integration covers Singapore air temperature within the available four-day forecast.

## Credentials checklist

- [ ] Ollama Cloud: `OLLAMA_API_KEY`
- [ ] Google Fact Check: `GOOGLE_FACT_CHECK_API_KEY`
- [ ] Tavily: `TAVILY_API_KEY`
- [ ] Google Web Risk: `WEB_RISK_API_KEY`
- [ ] Firebase app configuration
- [ ] Firebase backend Admin credentials

The checkboxes are a setup checklist, not a report of the current credentials' status.

## Pending feature

- **Deepfake detection:** no deepfake-detection API is connected yet. Its model or service still needs to be selected and implemented.
