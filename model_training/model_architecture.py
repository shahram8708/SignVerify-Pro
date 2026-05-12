"""Siamese signature verification architecture with ResNet50 backbone."""

from __future__ import annotations

from typing import Dict

import torch
import torch.nn as nn
import torch.nn.functional as F
from torchvision.models import ResNet50_Weights, resnet50

from .config import DROPOUT_RATE, EMBEDDING_DIM

PRIMARY_FORENSIC_KEYS = [
    "overall_gestalt_score",
    "pen_lift_score",
    "letter_formation_score",
    "baseline_score",
    "slant_angle_score",
    "pressure_pattern_score",
    "speed_indicator_score",
    "loop_proportion_score",
    "beginning_stroke_score",
    "ending_stroke_score",
    "connecting_stroke_score",
    "abbreviation_style_score",
    "flourish_pattern_score",
]

SUPPLEMENTARY_FORENSIC_KEYS = [
    "ink_distribution",
    "stroke_consistency",
    "spatial_proportions",
    "retouching_indicators",
    "tremor_assessment",
    "natural_variation",
    "complexity_level",
    "character_spacing",
    "terminal_features",
    "size_consistency",
    "rhythm_pattern",
    "overall_similarity",
]

ALL_FORENSIC_KEYS = PRIMARY_FORENSIC_KEYS + SUPPLEMENTARY_FORENSIC_KEYS


class L2Normalize(nn.Module):
    """Applies L2 normalization over feature dimension."""

    def __init__(self, eps: float = 1e-8) -> None:
        super().__init__()
        self.eps = eps

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return F.normalize(x, p=2, dim=1, eps=self.eps)


class SignatureFeatureExtractor(nn.Module):
    """ResNet50 feature extractor with multi-scale aggregation for signatures."""

    def __init__(self, embedding_dim: int = EMBEDDING_DIM, dropout_rate: float = DROPOUT_RATE) -> None:
        super().__init__()

        try:
            backbone = resnet50(weights=ResNet50_Weights.IMAGENET1K_V2)
        except Exception:
            backbone = resnet50(weights=None)

        original_conv1 = backbone.conv1
        new_conv1 = nn.Conv2d(1, 64, kernel_size=7, stride=2, padding=3, bias=False)

        with torch.no_grad():
            if original_conv1.weight.shape[1] == 3:
                new_conv1.weight.copy_(original_conv1.weight.mean(dim=1, keepdim=True))
            else:
                new_conv1.weight.copy_(original_conv1.weight)

        backbone.conv1 = new_conv1

        self.conv1 = backbone.conv1
        self.bn1 = backbone.bn1
        self.relu = backbone.relu
        self.maxpool = backbone.maxpool

        self.layer1 = backbone.layer1
        self.layer2 = backbone.layer2
        self.layer3 = backbone.layer3
        self.layer4 = backbone.layer4

        self.global_pool = nn.AdaptiveAvgPool2d((1, 1))

        self.embedding_head = nn.Sequential(
            nn.Linear(3584, 1024),
            nn.BatchNorm1d(1024),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout_rate),
            nn.Linear(1024, 512),
            nn.BatchNorm1d(512),
            nn.ReLU(inplace=True),
            nn.Dropout(0.3),
            nn.Linear(512, embedding_dim),
            L2Normalize(),
        )

    def _backbone_forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        x = self.conv1(x)
        x = self.bn1(x)
        x = self.relu(x)
        x = self.maxpool(x)

        x = self.layer1(x)
        layer2 = self.layer2(x)
        layer3 = self.layer3(layer2)
        layer4 = self.layer4(layer3)
        return layer2, layer3, layer4

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        layer2, layer3, layer4 = self._backbone_forward(x)

        pooled_l2 = self.global_pool(layer2).flatten(1)
        pooled_l3 = self.global_pool(layer3).flatten(1)
        pooled_l4 = self.global_pool(layer4).flatten(1)

        multi_scale = torch.cat([pooled_l2, pooled_l3, pooled_l4], dim=1)
        embedding = self.embedding_head(multi_scale)
        return embedding

    def set_backbone_trainable(self, trainable: bool) -> None:
        for module in [
            self.conv1,
            self.bn1,
            self.layer1,
            self.layer2,
            self.layer3,
            self.layer4,
        ]:
            for param in module.parameters():
                param.requires_grad = trainable


class SimilarityHead(nn.Module):
    """Produces a scalar similarity from two embeddings."""

    def __init__(self, embedding_dim: int = EMBEDDING_DIM) -> None:
        super().__init__()
        input_dim = (embedding_dim * 2) + 1

        self.classifier = nn.Sequential(
            nn.Linear(input_dim, 256),
            nn.BatchNorm1d(256),
            nn.ReLU(inplace=True),
            nn.Dropout(0.35),
            nn.Linear(256, 128),
            nn.ReLU(inplace=True),
            nn.Dropout(0.3),
            nn.Linear(128, 64),
            nn.ReLU(inplace=True),
            nn.Linear(64, 1),
            nn.Sigmoid(),
        )

    def build_pair_features(self, emb1: torch.Tensor, emb2: torch.Tensor) -> torch.Tensor:
        abs_diff = torch.abs(emb1 - emb2)
        elem_prod = emb1 * emb2
        cosine = F.cosine_similarity(emb1, emb2, dim=1).unsqueeze(1)
        return torch.cat([abs_diff, elem_prod, cosine], dim=1)

    def from_pair_features(self, pair_features: torch.Tensor) -> torch.Tensor:
        return self.classifier(pair_features)

    def forward(self, emb1: torch.Tensor, emb2: torch.Tensor) -> torch.Tensor:
        pair_features = self.build_pair_features(emb1, emb2)
        return self.from_pair_features(pair_features)


class ForensicAnalysisHead(nn.Module):
    """Multi-output forensic head for 25 dimensions."""

    def __init__(self, pair_feature_dim: int = (EMBEDDING_DIM * 2) + 1) -> None:
        super().__init__()
        self.shared = nn.Sequential(
            nn.Linear(pair_feature_dim, 256),
            nn.ReLU(inplace=True),
        )

        self.branches = nn.ModuleDict({
            key: nn.Sequential(nn.Linear(256, 1), nn.Sigmoid()) for key in ALL_FORENSIC_KEYS
        })

    def forward(self, pair_features: torch.Tensor) -> Dict[str, torch.Tensor]:
        shared_features = self.shared(pair_features)
        return {key: branch(shared_features) for key, branch in self.branches.items()}


class SiameseSignatureNet(nn.Module):
    """Full Siamese signature network with similarity and forensic heads."""

    def __init__(self, embedding_dim: int = EMBEDDING_DIM) -> None:
        super().__init__()
        self.embedding_dim = embedding_dim
        self.branch = SignatureFeatureExtractor(embedding_dim=embedding_dim)
        self.similarity_head = SimilarityHead(embedding_dim=embedding_dim)
        self.forensic_head = ForensicAnalysisHead(pair_feature_dim=(embedding_dim * 2) + 1)

    def forward(self, image1: torch.Tensor, image2: torch.Tensor) -> Dict[str, torch.Tensor | Dict[str, torch.Tensor]]:
        emb1 = self.branch(image1)
        emb2 = self.branch(image2)

        pair_features = self.similarity_head.build_pair_features(emb1, emb2)
        similarity = self.similarity_head.from_pair_features(pair_features)
        forensic_scores = self.forensic_head(pair_features)

        return {
            "embedding1": emb1,
            "embedding2": emb2,
            "pair_features": pair_features,
            "similarity": similarity,
            "forensic_scores": forensic_scores,
        }

    def set_backbone_trainable(self, trainable: bool) -> None:
        self.branch.set_backbone_trainable(trainable)

    def parameter_count(self) -> int:
        return sum(param.numel() for param in self.parameters())
