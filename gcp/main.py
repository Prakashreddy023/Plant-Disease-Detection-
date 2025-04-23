import functions_framework
from google.cloud import storage
import numpy as np
from PIL import Image
import tensorflow as tf
import logging
from io import BytesIO

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global variables
MODELS = {}
BUCKET_NAME = "prakash-tf-models"

# Model paths and class names
MODEL_CONFIG = {
    "potato": {
        "path": "models/potatoes_oversampled.h5",
        "classes": ["Early Blight", "Late Blight", "Healthy"],
        "image_size": 256
    },
    "tomato": {
        "path": "models/tomato_oversampled.h5",
        "classes": [
            "Bacterial spot", "Early blight", "Late blight", "Leaf Mold",
            "Septoria leaf spot", "Spider Mites Two Spotted Spider Mite",
            "Target spot", "Yellow leaf curl virus", "mosaic virus", "Healthy"
        ],
        "image_size": 128
    },
    "papaya": {
        "path": "models/papaya_1.h5",
        "classes": ["Anthracnose", "Bacterial Spot", "Curl", "Healthy", "Ring Spot"],
        "image_size": 256
    }
}


def download_blob(bucket_name, source_blob_name, destination_file_name):
    """Downloads a blob from the bucket."""
    try:
        storage_client = storage.Client()
        bucket = storage_client.get_bucket(bucket_name)
        blob = bucket.blob(source_blob_name)
        blob.download_to_filename(destination_file_name)
        logger.info(f"Blob {source_blob_name} downloaded to {destination_file_name}")
    except Exception as e:
        logger.error(f"Failed to download blob {source_blob_name}: {e}")
        raise


def load_models():
    """Load all models from GCS if not already loaded."""
    global MODELS
    if not MODELS:
        for crop, config in MODEL_CONFIG.items():
            local_path = f"/tmp/{crop}_model.h5"
            try:
                download_blob(BUCKET_NAME, config["path"], local_path)
                MODELS[crop] = tf.keras.models.load_model(local_path)
                logger.info(f"Model for {crop} loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load model for {crop}: {e}")
                raise


def preprocess_image(image_data, crop: str) -> np.ndarray:
    """Preprocess the uploaded image to match the model's expected input shape."""
    logger.info(f"Preprocessing image for crop: {crop}")
    try:
        image = Image.open(image_data)
        if image.mode != "RGB":
            image = image.convert("RGB")

        size = MODEL_CONFIG[crop]["image_size"]
        image = image.resize((size, size))

        image_array = np.array(image) / 255.0
        return image_array
    except Exception as e:
        logger.error(f"Image preprocessing failed: {e}")
        raise


@functions_framework.http
def predict(request):
    """HTTP Cloud Function to predict crop disease."""
    try:
        # Load models if not already loaded
        load_models()

        # Get crop type from form data (default to potato if not specified)
        crop = request.form.get("crop", "potato").lower()

        # Validate crop
        if crop not in MODEL_CONFIG:
            logger.error(f"Invalid crop: {crop}. Supported crops: {list(MODEL_CONFIG.keys())}")
            return {
                "error": f"Invalid crop: {crop}. Supported crops are: {list(MODEL_CONFIG.keys())}"
            }, 400

        # Get image file
        if "file" not in request.files:
            logger.error("No file provided in request")
            return {"error": "No file provided"}, 400

        image = request.files["file"]

        # Preprocess image
        image_array = preprocess_image(image, crop)

        # Add batch dimension
        img_batch = np.expand_dims(image_array, 0)

        # Make prediction
        model = MODELS[crop]
        predictions = model.predict(img_batch)
        logger.info(f"Predictions for {crop}: {predictions[0]}")

        # Get predicted class and confidence
        predicted_class = MODEL_CONFIG[crop]["classes"][np.argmax(predictions[0])]
        confidence = round(float(np.max(predictions[0]) * 100), 2)

        return {
            "crop": crop,
            "class": predicted_class,
            "confidence": confidence
        }
    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        return {"error": f"Prediction failed: {str(e)}"}, 500