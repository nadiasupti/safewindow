"""Train and evaluate the temporal flood model on a local GPU."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset
from tqdm import tqdm

from model import TemporalFloodUNet


class FloodDataset(TensorDataset):
    def __init__(self, path: Path, split: str):
        with np.load(path, allow_pickle=False) as data:
            self.x = torch.from_numpy(data["x" if split == "train" else "x_val"])
            self.y = torch.from_numpy(data["y" if split == "train" else "y_val"])
            self.dates = data["dates" if split == "train" else "dates_val"]
            self.ids = data["sample_ids" if split == "train" else "sample_ids_val"]

    def __len__(self) -> int:
        return len(self.x)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        return self.x[index], self.y[index]


def weighted_loss() -> nn.Module:
    """Weight flooded pixels more heavily; ignore unknown/no-data pixels."""
    return nn.CrossEntropyLoss(weight=torch.tensor([1.0, 5.0]), ignore_index=255)


def evaluate(model: nn.Module, loader: DataLoader, device: torch.device) -> tuple[float, float]:
    model.eval()
    loss = 0.0
    correct = 0
    total = 0
    with torch.inference_mode():
        for x, y in loader:
            x, y = x.to(device), y.to(device)
            logits = model(x)
            criterion = weighted_loss().to(device)
            batch_loss = criterion(logits, y)
            loss += float(batch_loss.item()) * y.numel()
            correct += int((logits.argmax(1) == y).sum().item())
            total += int(y.numel())
    return loss / max(len(loader.dataset), 1), correct / max(total, 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=Path("ml/dataset.npz"))
    parser.add_argument("--output", type=Path, default=Path("ml/model.pt"))
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--resume", type=Path, default=None)
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
        torch.backends.cudnn.benchmark = True
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using {device}")

    with np.load(args.dataset, allow_pickle=False) as data:
        input_channels = int(data["input_channels"])
        patch_size = int(data["patch_size"])

    train_set = FloodDataset(args.dataset, "train")
    validation_set = FloodDataset(args.dataset, "val")
    train_loader = DataLoader(train_set, batch_size=args.batch_size, shuffle=True,
                               num_workers=args.workers, pin_memory=torch.cuda.is_available())
    validation_loader = DataLoader(validation_set, batch_size=args.batch_size, shuffle=False,
                                    num_workers=args.workers, pin_memory=torch.cuda.is_available())

    model = TemporalFloodUNet(input_channels=input_channels, base_channels=32).to(device)
    criterion = weighted_loss().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate, weight_decay=1e-4)
    scaler = torch.amp.GradScaler("cuda", enabled=torch.cuda.is_available())
    best_loss = math.inf
    last_epoch = 0

    if args.resume and args.resume.exists():
        checkpoint = torch.load(args.resume, map_location=device)
        model.load_state_dict(checkpoint["model"])
        optimizer.load_state_dict(checkpoint["optimizer"])
        last_epoch = int(checkpoint.get("epoch", 0))
        best_loss = float(checkpoint.get("best_loss", math.inf))

    for epoch in range(last_epoch + 1, args.epochs + 1):
        model.train()
        epoch_loss = 0.0
        for x, y in tqdm(train_loader, desc=f"epoch {epoch}/{args.epochs}"):
            x, y = x.to(device, non_blocking=torch.cuda.is_available()), y.to(device, non_blocking=torch.cuda.is_available())
            optimizer.zero_grad(set_to_none=True)
            with torch.amp.autocast("cuda", enabled=torch.cuda.is_available(), dtype=torch.float16):
                logits = model(x)
                loss = criterion(logits, y)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            epoch_loss += float(loss.item()) * y.numel()

        validation_loss, accuracy = evaluate(model, validation_loader, device)
        print(f"epoch={epoch:03d} train_loss={epoch_loss / max(len(train_set), 1):.4f} "
              f"val_loss={validation_loss:.4f} val_accuracy={accuracy:.4f}")
        if validation_loss < best_loss:
            best_loss = validation_loss
            checkpoint = {
                "model": model.state_dict(),
                "optimizer": optimizer.state_dict(),
                "epoch": epoch,
                "best_loss": best_loss,
                "config": {
                    "input_channels": input_channels,
                    "patch_size": patch_size,
                    "batch_size": args.batch_size,
                    "learning_rate": args.learning_rate,
                },
            }
            torch.save(checkpoint, args.output)
            print(f"Saved best model to {args.output}")

    print(f"Training complete. Best validation loss: {best_loss:.4f}")


if __name__ == "__main__":
    main()
