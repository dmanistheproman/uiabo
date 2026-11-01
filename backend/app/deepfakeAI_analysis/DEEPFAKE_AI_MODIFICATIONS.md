## Branch:

Created from "main" branch as of 17 September 2026 (Commit: ad8bd66)

## Storage Warning

When following the set up steps in [Teammate Setup](../../../TEAMMATE_SETUP.md), step 5 "Install and start the backend" will start the download of the AI-images detector model. Estimated storage is:
- 1gb in the project folder: uiabo/backend/app/deepfakeAI_analysis/models/convnext-ai-images-detector
- 0.3gb in: C:/users/[YOUR_USER]/.cache/huggingface/hub/models--timm--convnextv2_base.fcmae_ft_in22k_in1k

Once no longer in use, storage can be freed by deleting the entire /huggingface folder if you do not have other huggingface models downloaded. If you do, delete these from /huggingface/hub:
- .locks folder
- models--timm--convnextv2_base.fcmae_ft_in22k_in1k folder
- CACHEDIR.TAG

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
 

## How it works

Services used:

1. Open source machine learning model trained specifically to detect AI images. It lists a 90% accuracy in its description on its Huggingface page. Internal testing using 4000 images from Tiny-GenImage achieved 98% accuracy. [Model] https://huggingface.co/xRayon/convnext-ai-images-detector

2. Uses Gemini 3.5 Flash Lite, a general multimodal reasoning AI model. It is used to add explanation to the classification of the ML model. An API key is required, from the link below.
[API] https://aistudio.google.com/api-keys



The feature uses a 3 step process to determine if an image is AI-generated/manipulated by AI.

1. The image is passed into the convnext-ai-images-detector, which returns a classification and confidence score.

2. Gemini 3.5 Flash Lite receives the image as well as the classification and confidence score. It is instructed to perform an independent secondary analysis of the image, not taking into account the ML model's classification. It is instructed to return a fixed json format output, explicitly stating:
  - Its own classification
  - Whether it agrees with the ML model
  - An explanation of its analysis, in a fixed format: Visual evidence, Reasoning and Limitations.

3. A final output is then constructed using the two outputs.
  - Agreement: The scores and classification are returned, along with the explanation.
  - Disagreement: The scores are not returned and classifications is replaced with "Uncertain", along with a fixed
    placeholder explanation 
  - ML model/Gemini failure: Failed analysis error handling.


## LIST OF NEW FILES/FOLDERS:

uiabo
|------\mobile
|        ------\src\Deepfake_AI_Check_Screen.js
|        ------\src\Deepfake_AI_Result_Screen.js
|------\backend
|        ------\tests\deepfakeAI_analysis
|                ------\test_service.py
|                ------\test.jpg
|        ------\app
|               ------\routers\deepfakeAI_analysis.py
|                ------\deepfakeAI_analysis
|                        ------\models\convnext-ai-image-detector 
|                        ------\models.py
|                        ------\service.py
|                        ------\score_service.py


## PURPOSE OF NEW FILES/FOLDERS

1. [Deepfake_AI_Check_Screen.js] The UI for the user input and image preview. Passes the image to the backend.
2. [Deepfake_AI_Result_Screen.js] The UI for the results of the analysis.
3. [test_service.py] The backend tests.
4. [test.jpg] A test image for the backend tests.
5. [deepfakeAI_analysis.py] Routes the image input to the backend analysis service.
6. [\models\convnext-ai-images-detector] Contains the ML model. Folder will be created automatically when starting backend. 
7. [models.py] Defines the structured schemas for the data models used by this feature.
8. [score_service.py] Contains the AI images ML model service.
9. [service.py] Contains the Gemini API and results consolidation service.


## LIST OF MODIFIED FILES:

uiabo
|------\mobile
|        ------\package-lock.json [Modified by command: npx.cmd install expo-image-picker]
|        ------\package.json [Modified by command: npx.cmd install expo-image-picker]
|        ------\App.js
|        ------\src
|                ------\services\api.js
|                ------\screens\HomeScreen.js
|                ------\screens\ResultsScreen.js
|------\backend
|        ------\requirements.txt
|        -------\app
|                ------\main.py
|                ------\analyses\store.py
|------\ .env.instructions
      

## MODIFICATIONS MADE

1. [package-lock.json] Modified by command: "npx.cmd install expo-image-picker", for the frontend image input.
2. [package.json] Modified by command: "npx.cmd install expo-image-picker", for the frontend image input.
3. [App.js] Added the deepfake/AI screens to the app's existing navigation system.
4. [api.js] Adds the function that uploads an image to the deepfake/AI backend endpoint.
5. [HomeScreen.js] Adds a feature entry for deepfake/AI image checking to the home screen's feature list.
6. [ResultsScreen.js] Updates the existing results-history screen to recognise deepfake/AI image analyses.
7. [requirements.txt] Added installations:
  -  torch: PyTorch, the machine-learning framework that actually runs the neural network/model.
  -  torchvision: Provides computer-vision utilities built around PyTorch, including image processing and transformations. Used for handling images going into the model.
  -  transformers: Hugging Face's library for loading and running pretrained ML models.
  -  accelerate: Helps Transformers efficiently run models on available hardware, particularly handling CPU/GPU/device placement.
  -  huggingface_hub: Lets Python download and access models hosted on Hugging Face.
  -  pillow: Python's image-processing library. Used to open/read the images.
  -  timm: PyTorch Image Models, a library containing a large collection of pretrained computer-vision models and utilities.
  -  google-genai: Used to access the AI reasoning models provided by Gemini.
8. [main.py] Registers the new deepfake/AI router with the existing FastAPI application.
9. [store.py] Extends the existing analysis-storage system to handle deepfake/AI analysis records.
10. [.env.instructions] Added instructions for Gemini API key.