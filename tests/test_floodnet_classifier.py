import json
from pathlib import Path

import torch
from PIL import Image

from ml.floodnet_classifier import FloodNetDataset, FloodClassifier, load_checkpoint, predict_image


def test_dataset_pairs_images_with_real_labels(tmp_path: Path) -> None:
    image_dir = tmp_path / "img"
    annotation_dir = tmp_path / "ann"
    image_dir.mkdir()
    annotation_dir.mkdir()

    for image_id, label in (("10165", "flooded"), ("10166", "non flooded")):
        Image.new("RGB", (32, 24), color=(10, 20, 30)).save(image_dir / f"{image_id}.jpg")
        question = (
            "{'Question': 'What is the overall condition of the given image?', "
            f"'Ground_Truth': '{label}'}}"
        )
        document = {"tags": [{"name": "question", "value": question}]}
        annotation_path = annotation_dir / f"{image_id}.JPG.json"
        annotation_path.write_text(json.dumps(document), encoding="utf-8")

    dataset = FloodNetDataset(image_dir, annotation_dir, split=None)

    assert len(dataset) == 2
    image, label = dataset[0]
    assert image.shape == (3, 224, 224)
    assert label.item() == 1
    assert dataset[1][1].item() == 0


def test_checkpoint_and_prediction(tmp_path: Path) -> None:
    model = FloodClassifier()
    checkpoint_path = tmp_path / "model.pt"
    torch.save({"model": model.state_dict()}, checkpoint_path)

    loaded = FloodClassifier()
    load_checkpoint(checkpoint_path, loaded)
    image = Image.new("RGB", (32, 24), color=(255, 0, 0))
    prediction, confidence = predict_image(loaded, image)

    assert prediction in (0, 1)
    assert 0.0 <= confidence <= 1.0
