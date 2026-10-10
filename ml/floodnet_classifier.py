"""Train a real post-flood scene classifier using FloodNet labels."""
from __future__ import annotations

import argparse
import ast
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from sklearn.model_selection import train_test_split
from torch import nn
from torch.utils.data import DataLoader, Dataset
from tqdm import tqdm


LABELS = {"flooded": 1, "non flooded": 0}


@dataclass(frozen=True)
class Sample:
    image_path: Path
    label: int


class FloodNetDataset(Dataset[Sample]):
    def __init__(self, image_dir: Path, annotation_dir: Path, split: str | None = None,
                 seed: int = 42, validation_fraction: float = 0.2):
        self.samples = self._load_samples(image_dir, annotation_dir)
        if split is not None:
            image_ids = np.asarray([sample.image_path.stem for sample in self.samples])
            labels = np.asarray([sample.label for sample in self.samples])
            train_ids, validation_ids = train_test_split(
                image_ids,
                test_size=validation_fraction,
                random_state=seed,
                stratify=labels,
            )
            selected = set(train_ids if split == "train" else validation_ids)
            self.samples = [sample for sample in self.samples if sample.image_path.stem in selected]

    @staticmethod
    def _load_samples(image_dir: Path, annotation_dir: Path) -> list[Sample]:
        labels: dict[str, int] = {}
        for annotation_path in annotation_dir.glob("*.json"):
            document = json.loads(annotation_path.read_text(encoding="utf-8"))
            for tag in document.get("tags", []):
                if tag.get("name") != "question":
                    continue
                question = ast.literal_eval(tag.get("value", "{}"))
                if question.get("Question") != "What is the overall condition of the given image?":
                    continue
                label_name = question.get("Ground_Truth", "").strip().lower()
                if label_name not in LABELS:
                    raise ValueError(f"Unsupported FloodNet label: {label_name!r}")
                image_id = annotation_path.stem.removesuffix(".JPG")
                labels[image_id] = LABELS[label_name]
                break

        samples: list[Sample] = []
        for image_path in sorted(image_dir.glob("*.jpg")):
            if image_path.stem in labels:
                samples.append(Sample(image_path, labels[image_path.stem]))
        if not samples:
            raise FileNotFoundError(f"No paired images found in {image_dir}")
        missing = sorted(set(labels) - {sample.image_path.stem for sample in samples})
        if len(set(sample.label for sample in samples)) < 2:
            raise ValueError("At least one flooded and one non-flooded image are required")
        if missing:
            print(f"Warning: {len(missing)} annotated images are unavailable; using {len(samples)} paired samples")
        return samples

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        sample = self.samples[index]
        with Image.open(sample.image_path) as image:
            image = image.convert("RGB").resize((224, 224), Image.Resampling.LANCZOS)
            array = np.asarray(image, dtype=np.float32) / 255.0
            tensor = torch.from_numpy(array.transpose(2, 0, 1))
        return tensor, torch.tensor(sample.label, dtype=torch.long)


class FloodClassifier(nn.Module):
    def __init__(self, num_classes: int = 2) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 32, 3, padding=1),
            nn.BatchNorm2d(32),
            nn.ReLU(inplace=True),
            nn.Conv2d(32, 64, 3, stride=2, padding=1),
            nn.BatchNorm2d(64),
            nn.ReLU(inplace=True),
            nn.Conv2d(64, 128, 3, stride=2, padding=1),
            nn.BatchNorm2d(128),
            nn.ReLU(inplace=True),
        )
        self.head = nn.Sequential(
            nn.AdaptiveAvgPool2d((1, 1)),
            nn.Flatten(),
            nn.Linear(128, 64),
            nn.ReLU(inplace=True),
            nn.Linear(64, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.features(x))


def load_checkpoint(path: Path, model: nn.Module, map_location: str | torch.device = "cpu") -> dict[str, object]:
    """Load a locally generated checkpoint using PyTorch's legacy serialization mode."""
    checkpoint = torch.load(path, map_location=map_location, weights_only=False)
    model.load_state_dict(checkpoint["model"])
    return checkpoint


def predict_image(model: nn.Module, image: Image.Image, device: torch.device = torch.device("cpu")) -> tuple[int, float]:
    """Classify a PIL image and return its class and confidence."""
    model.eval()
    with torch.inference_mode():
        tensor = torch.from_numpy(np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0).permute(2, 0, 1).unsqueeze(0)
        logits = model(tensor.to(device))
        probabilities = torch.softmax(logits, dim=1)[0]
        prediction = int(logits.argmax(dim=1).item())
        confidence = float(probabilities[prediction].item())
    return prediction, confidence


def evaluate(model: nn.Module, loader: DataLoader, device: torch.device) -> dict[str, float]:
    model.eval()
    criterion = nn.CrossEntropyLoss()
    total = 0
    correct = 0
    true_positive = 0
    false_positive = 0
    false_negative = 0
    true_negative = 0
    with torch.inference_mode():
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)
            logits = model(images)
            predictions = logits.argmax(dim=1)
            batch_size = labels.numel()
            total += batch_size
            correct += int((predictions == labels).sum().item())
            true_positive += int(((predictions == 1) & (labels == 1)).sum().item())
            false_positive += int(((predictions == 1) & (labels == 0)).sum().item())
            false_negative += int(((predictions == 0) & (labels == 1)).sum().item())
            true_negative += int(((predictions == 0) & (labels == 0)).sum().item())

    accuracy = correct / total
    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    f1 = 2 * precision * recall / max(precision + recall, 1e-8)
    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "confusion_matrix": [
            [true_negative, false_positive],
            [false_negative, true_positive],
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image-dir", type=Path, default=Path("data/raw/floodnet/train_image/img"))
    parser.add_argument("--annotation-dir", type=Path, default=Path("data/raw/floodnet/train_image/ann"))
    parser.add_argument("--output", type=Path, default=Path("ml/floodnet_model.pt"))
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--validation-fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    train_set = FloodNetDataset(args.image_dir, args.annotation_dir, "train", args.seed,
                                args.validation_fraction)
    validation_set = FloodNetDataset(args.image_dir, args.annotation_dir, "validation", args.seed,
                                     args.validation_fraction)
    train_loader = DataLoader(train_set, batch_size=args.batch_size, shuffle=True,
                               num_workers=0, pin_memory=torch.cuda.is_available())
    validation_loader = DataLoader(validation_set, batch_size=args.batch_size, shuffle=False,
                                    num_workers=0, pin_memory=torch.cuda.is_available())

    model = FloodClassifier().to(device)
    criterion = nn.CrossEntropyLoss(weight=torch.tensor([1.0, 5.0], device=device))
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=1e-4)
    best_score = -math.inf

    for epoch in range(1, args.epochs + 1):
        model.train()
        epoch_loss = 0.0
        for images, labels in tqdm(train_loader, desc=f"epoch {epoch}/{args.epochs}"):
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad(set_to_none=True)
            logits = model(images)
            loss = criterion(logits, labels)
            loss.backward()
            optimizer.step()
            epoch_loss += float(loss.item()) * labels.numel()

        metrics = evaluate(model, validation_loader, device)
        print(
            f"epoch={epoch:02d} train_loss={epoch_loss / max(len(train_set), 1):.4f} "
            f"accuracy={metrics['accuracy']:.4f} precision={metrics['precision']:.4f} "
            f"recall={metrics['recall']:.4f} f1={metrics['f1']:.4f}"
        )
        score = metrics["f1"]
        if score > best_score:
            best_score = score
            args.output.parent.mkdir(parents=True, exist_ok=True)
            torch.save({"model": model.state_dict(), "config": vars(args)}, args.output)
            print(f"Saved best model to {args.output}")

    print(f"Best validation F1: {best_score:.4f}")


if __name__ == "__main__":
    main()
