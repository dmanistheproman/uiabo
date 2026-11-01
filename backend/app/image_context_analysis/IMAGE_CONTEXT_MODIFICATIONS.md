## Branch:

Continued from "deepfake-AI-analysis" branch.

## IMPORTANT

An API key is required from https://aistudio.google.com/api-keys.
1. Sign in with your Google account.
2. Click "Create API key"
3. Choose "Default Gemini Project" or Create a project if you want
4. Add the key to your .env in the Root folder, like this: [GEMINI_API_KEY="YOUR_API_KEY"]
5. The chosen Gemini version supports free usage up to:
  - 500 requests per day 
  - 5 requests per minute 
  - 250k tokens per minute
  - For more information, click "Rate Limit" under "Usage & Billing" and select "Gemini 3.5 Flash Lite"
6. As per Google's terms of service:
  - "Do not submit sensitive, confidential, or personal information to the Unpaid Services."
  - View terms of service at: https://ai.google.dev/gemini-api/terms. 
 
An API key from Tavily is required as well: https://app.tavily.com/. Should already have been created for text analysis pipeline usage.

## How it works

Services used:

1. Tavily, used to search the web for links that are relevant to the extracted claim.

2. Uses Gemini 3.5 Flash Lite, a general multimodal reasoning AI model. It is used twice:
  - To perform OCR to determine the caption, then extract the main claim.
  - Perform analysis of the image and the caption, using the web links returned by Tavily as additional evidence. 



The feature uses a 4 step process to perform image context analysis.

1. Gemini 3.5 Flash Lite receives the image. It is instructed to extract the caption from the image and then extract the main claim from the caption, returning both.

2. Tavily then uses the extracted main claim as a search term to search the web for up to 5 links relating to the main claim.

3. Gemini 3.5 Flash Lite then receives the image again, along with the extracted caption, main claim and the Tavily sourced web links. It is instructed to perform analysis of the image, taking into account the web links provided. It is instructed to return a fixed json format output, explicitly stating:
  - A concern level from a fixed set of options
  - An explanation of its analysis
  - Up to two of the most relevant web links provided by Tavily, in a fixed format: URL, relationship (e.g. supports/contradicts) and summary.

4. A final output is then constructed, including additional values such as the image filename. Tavily/Gemini failure falls back onto the failed analysis error handling.


## LIST OF NEW FILES/FOLDERS:

uiabo
|------\mobile
|        ------\src\screens\Image_Context_Analysis_Screen.js
|        ------\src\screens\Image_Context_Result_Screen.js
|------\backend
|        ------\tests\image_context_analysis
|                ------\test_service.py
|                ------\test.jpg
|        ------\app
|               ------\routers\image_context_analysis.py
|                ------\image_context_analysis
|                        ------\models.py
|                        ------\extraction_service.py
|                        ------\analysis_service.py


## PURPOSE OF NEW FILES/FOLDERS

1. [Image_Context_Analysis_Screen.js] The UI for the user input and image preview. Passes the image to the backend.
2. [Image_Context_Result_Screen.js] The UI for the results of the analysis.
3. [test_service.py] The backend tests.
4. [test.jpg] A test image for the backend tests.
5. [image_context_analysis.py] Routes the image input to the backend analysis service.
6. [models.py] Defines the structured schemas for the data models used by this feature.
7. [extraction_service.py] Contains the first Gemini API call for caption extraction.
8. [analysis_service.py] Contains the Tavily API call and the second Gemini API call, and the results consolidation service.


## LIST OF MODIFIED FILES:

uiabo
|------\mobile
|        ------\App.js
|        ------\src
|                ------\services\api.js
|                ------\screens\HomeScreen.js
|                ------\screens\ResultsScreen.js
|------\backend
|        -------\app
|                ------\main.py
|                ------\analyses\store.py
      

## MODIFICATIONS MADE

1. [App.js] Added the new screens to the app's existing navigation system.
2. [api.js] Adds the function that uploads an image to the new backend endpoint.
3. [HomeScreen.js] Adds a feature entry for image context analysis to the home screen's feature list.
4. [ResultsScreen.js] Updates the existing results-history screen to recognise image context analysis results.
5. [main.py] Registers the new router with the existing FastAPI application.
6. [store.py] Extends the existing analysis-storage system to handle the new analysis records.