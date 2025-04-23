from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import numpy as np
from io import BytesIO
from PIL import Image
import tensorflow as tf
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

origins = [
    "http://localhost",
    "http://localhost:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load models for each crop
try:
    MODELS = {
        "potato": tf.keras.models.load_model("../Saved_models/potatoes_oversampled.h5"),
"tomato": tf.keras.models.load_model("../Saved_models_tomato/tomato_oversampled.h5"),
        "papaya": tf.keras.models.load_model("../Saved_models/papaya_1.h5"),  # Verify this path
    }
    logger.info("All models loaded successfully")
except Exception as e:
    logger.error(f"Error loading models: {e}")
    raise

# Class names for each crop
CLASS_NAMES = {
    "potato": ["Early Blight", "Late Blight", "Healthy"],
    "tomato": [
        "Bacterial spot",
        "Early blight",
        "Late blight",
        "Leaf Mold",
        "Septoria leaf spot",
        "Spider Mites Two Spotted Spider Mite",
        "Target spot",
        "Yellow leaf curl virus",
        "mosaic virus",
        "Healthy"
    ],
    "papaya": ["Anthracnose", "Bacterial Spot", "Curl", "Healthy", "Ring Spot"],  # Update if needed
}

# Constants
IMAGE_SIZE = 256  # Default size, overridden by crop-specific sizes


@app.get("/ping")
async def ping():
    return "Hello, I am alive"


def preprocess_image(data, crop: str) -> np.ndarray:
    """
    Preprocess the uploaded image to match the model's expected input shape.
    """
    logger.info(f"Preprocessing image for crop: {crop}")
    image = Image.open(BytesIO(data))
    if image.mode != "RGB":
        image = image.convert("RGB")

    # Crop-specific image sizes
    size = {"potato": 256, "tomato": 128, "papaya": 256}.get(crop, 256)
    image = image.resize((size, size))

    image_array = np.array(image) / 255.0
    return image_array


async def predict_crop(file: UploadFile, crop: str):
    """
    Shared prediction logic for all crop endpoints.
    """
    logger.info(f"Received predict request for crop: {crop}")

    # Validate crop
    if crop not in MODELS:
        logger.error(f"Invalid crop: {crop}. Supported crops: {list(MODELS.keys())}")
        return {
            "error": f"Invalid crop: {crop}. Supported crops are: {list(MODELS.keys())}"
        }

    # Read and preprocess the uploaded image
    image = preprocess_image(await file.read(), crop)

    # Add batch dimension
    img_batch = np.expand_dims(image, 0)

    # Select the model
    model = MODELS[crop]
    logger.info(f"Using model for crop: {crop}")

    # Make prediction
    predictions = model.predict(img_batch)
    logger.info(f"Predictions: {predictions[0]}")

    # Get predicted class and confidence
    predicted_class = CLASS_NAMES[crop][np.argmax(predictions[0])]
    confidence = np.max(predictions[0])

    logger.info(f"Predicted class: {predicted_class}, Confidence: {confidence}")

    return {
        "class": predicted_class,
        "confidence": float(confidence),
        "crop": crop,
    }


@app.post("/predict/potato")
async def predict_potato(file: UploadFile = File(...)):
    return await predict_crop(file, "potato")


@app.post("/predict/tomato")
async def predict_tomato(file: UploadFile = File(...)):
    return await predict_crop(file, "tomato")


@app.post("/predict/papaya")
async def predict_papaya(file: UploadFile = File(...)):
    return await predict_crop(file, "papaya")


if __name__ == "__main__":
    uvicorn.run(app, host="localhost", port=8000)