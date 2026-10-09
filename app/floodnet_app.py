"""Streamlit prototype for the trained FloodNet aerial-image classifier."""
from __future__ import annotations

import io
from pathlib import Path

import streamlit as st
from PIL import Image

from ml.floodnet_classifier import FloodClassifier, load_checkpoint, predict_image

MODEL_PATH = Path(__file__).resolve().parents[1] / "ml" / "floodnet_model.pt"


def main() -> None:
    st.set_page_config(page_title="FloodNet Prototype", page_icon="🌊", layout="wide")

    st.title("🌊 FloodNet Aerial Image Prototype")
    st.caption("Classifies a post-flood aerial image as flooded or non-flooded.")

    if not MODEL_PATH.exists():
        st.error(f"Trained model not found at {MODEL_PATH}.")
        st.stop()

    with st.sidebar:
        st.header("Model")
        st.write(f"Checkpoint: {MODEL_PATH.name}")
        st.write("Architecture: compact CNN")
        st.write("Dataset: FloodNet")
        st.write("Output: binary flood classification")

    uploaded_image = st.file_uploader("Upload an aerial image", type=["jpg", "jpeg", "png", "webp"])

    if uploaded_image is None:
        st.info("Upload an aerial image to run the classifier.")
        st.subheader("Example: flood scene")
        st.image("data/raw/floodnet/train_image/img/10165.jpg", use_container_width=True)
        return

    try:
        with Image.open(io.BytesIO(uploaded_image.getvalue())) as source:
            preview = source.convert("RGB")
        model = FloodClassifier()
        load_checkpoint(MODEL_PATH, model, map_location="cpu")
        prediction, confidence = predict_image(model, preview)
    except Exception as exc:
        st.error(f"Could not process this image: {exc}")
        st.stop()

    col_image, col_result = st.columns([1.5, 1])
    with col_image:
        st.subheader("Uploaded image")
        st.image(preview, caption=f"{uploaded_image.name} · {preview.size[0]} × {preview.size[1]}", use_container_width=True)

    with col_result:
        st.subheader("Prediction")
        flooded = prediction == 1
        st.markdown(
            f"<div style='font-size:3rem;font-weight:700;color:{'#d7263d' if flooded else '#2e9d4f'};'>"
            f"{'FLOODED' if flooded else 'NON-FLOODED'}</div>",
            unsafe_allow_html=True,
        )
        st.metric("Confidence", f"{confidence:.1%}")
        st.caption("A binary classification of the overall scene, not a pixel-level flood mask.")
        st.download_button(
            "Download prediction",
            data=f"{uploaded_image.name}\nPrediction: {'flooded' if flooded else 'non-flooded'}\nConfidence: {confidence:.1%}\n",
            file_name="floodnet_prediction.txt",
        )

    st.warning("This is a prototype. It should be validated against official flood observations before operational use.")


if __name__ == "__main__":
    main()
