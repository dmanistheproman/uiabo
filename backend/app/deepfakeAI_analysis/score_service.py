import os

import torch
import torch.nn.functional as F
import timm

from PIL import Image
from torchvision import transforms
from huggingface_hub import hf_hub_download


BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MODEL_DIR = os.path.join(
    BASE_DIR,
    "models",
    "convnext-ai-images-detector"
)

MODEL_PATH = os.path.join(
    MODEL_DIR,
    "AI Images Detector",
    "checkpoints",
    "checkpoint_phase2.pth"
)


# ---------------------------------------------------------
# Model setup
# ---------------------------------------------------------

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def load_model():
    """Load the detector model once when the module is imported."""

    if not os.path.exists(MODEL_PATH):
        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)

        hf_hub_download(
            repo_id="xRayon/convnext-ai-images-detector",
            filename="AI Images Detector/checkpoints/checkpoint_phase2.pth",
            local_dir=MODEL_DIR
        )

    model = timm.create_model(
        "convnextv2_base",
        pretrained=True,
        num_classes=2
    )

    checkpoint = torch.load(
        MODEL_PATH,
        map_location=device
    )

    model.load_state_dict(checkpoint["model"])
    model.to(device)
    model.eval()

    return model


model = load_model()


# ---------------------------------------------------------
# Image preprocessing
# ---------------------------------------------------------

transform = transforms.Compose([
    transforms.Resize(288),
    transforms.CenterCrop(256),
    transforms.ToTensor(),
    transforms.Normalize(
        mean=(0.485, 0.456, 0.406),
        std=(0.229, 0.224, 0.225)
    )
])


# ---------------------------------------------------------
# Detector scoring
# ---------------------------------------------------------

def score_deepfakeAI(image: Image.Image) -> dict:
    """
    Analyse an image using the ConvNeXt AI-image detector.

    Returns:
        {
            "label": "Real" or "Fake",
            "confidence": float,
            "real_probability": float,
            "fake_probability": float
        }
    """

    image = image.convert("RGB")

    image_tensor = transform(image)
    image_tensor = image_tensor.unsqueeze(0).to(device)

    with torch.inference_mode():
        logits = model(image_tensor)
        probabilities = F.softmax(logits, dim=1)[0]

    real_probability = probabilities[0].item()
    fake_probability = probabilities[1].item()

    if fake_probability > real_probability:
        label = "Fake"
        confidence = fake_probability
    else:
        label = "Real"
        confidence = real_probability

    return {
        "label": label,
        "confidence": confidence,
        "real_probability": real_probability,
        "fake_probability": fake_probability,
    }