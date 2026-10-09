"""Compact temporal U-Net for flood prediction."""
from __future__ import annotations

import torch
from torch import nn


class TemporalFloodUNet(nn.Module):
    """Predict one future flood map from three prior flood maps plus rainfall/DEM."""

    def __init__(self, input_channels: int = 5, base_channels: int = 32) -> None:
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Conv2d(input_channels, base_channels, 3, padding=1),
            nn.BatchNorm2d(base_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(base_channels, base_channels * 2, 3, stride=2, padding=1),
            nn.BatchNorm2d(base_channels * 2),
            nn.ReLU(inplace=True),
            nn.Conv2d(base_channels * 2, base_channels * 4, 3, stride=2, padding=1),
            nn.BatchNorm2d(base_channels * 4),
            nn.ReLU(inplace=True),
        )
        self.up4 = nn.Sequential(
            nn.ConvTranspose2d(base_channels * 4, base_channels * 2, 3, stride=2, padding=1,
                               output_padding=1),
            nn.BatchNorm2d(base_channels * 2),
            nn.ReLU(inplace=True),
        )
        self.up2 = nn.Sequential(
            nn.ConvTranspose2d(base_channels * 4, base_channels, 3, stride=2, padding=1,
                               output_padding=1),
            nn.BatchNorm2d(base_channels),
            nn.ReLU(inplace=True),
        )
        self.head = nn.Sequential(
            nn.Conv2d(base_channels * 2, base_channels, 3, padding=1),
            nn.BatchNorm2d(base_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(base_channels, 2, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        enc1 = self.encoder[0:3](x)
        enc2 = self.encoder[3:6](enc1)
        enc3 = self.encoder[6:9](enc2)
        decoded = self.up4(enc3)
        decoded = torch.cat((decoded, enc2), dim=1)
        decoded = self.up2(decoded)
        decoded = torch.cat((decoded, enc1), dim=1)
        return self.head(decoded)
