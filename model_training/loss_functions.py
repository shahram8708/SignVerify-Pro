"""Loss functions for Siamese signature verification training."""

from __future__ import annotations

from typing import Dict

import torch
import torch.nn as nn
import torch.nn.functional as F

from .config import CONTRASTIVE_MARGIN, TRIPLET_MARGIN


class ContrastiveLoss(nn.Module):
    """Contrastive loss with label convention: 0 same signer, 1 different signer."""

    def __init__(self, margin: float = CONTRASTIVE_MARGIN) -> None:
        super().__init__()
        self.margin = margin

    def forward(self, embedding1: torch.Tensor, embedding2: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
        labels = labels.float().view(-1)
        distances = F.pairwise_distance(embedding1, embedding2, p=2)

        same_term = (1.0 - labels) * 0.5 * distances.pow(2)
        diff_term = labels * 0.5 * torch.clamp(self.margin - distances, min=0.0).pow(2)
        return (same_term + diff_term).mean()


class TripletLoss(nn.Module):
    """Triplet margin loss for optional anchor-positive-negative training mode."""

    def __init__(self, margin: float = TRIPLET_MARGIN) -> None:
        super().__init__()
        self.loss_fn = nn.TripletMarginLoss(margin=margin, p=2)

    def forward(self, anchor: torch.Tensor, positive: torch.Tensor, negative: torch.Tensor) -> torch.Tensor:
        return self.loss_fn(anchor, positive, negative)


class CombinedLoss(nn.Module):
    """Multi-task objective combining contrastive, BCE, and forensic supervision losses."""

    def __init__(
        self,
        contrastive_weight: float = 0.4,
        bce_weight: float = 0.45,
        forensic_weight: float = 0.15,
        margin: float = CONTRASTIVE_MARGIN,
    ) -> None:
        super().__init__()
        self.contrastive_weight = contrastive_weight
        self.bce_weight = bce_weight
        self.forensic_weight = forensic_weight

        self.contrastive = ContrastiveLoss(margin=margin)
        self.bce = nn.BCELoss()
        self.forensic_bce = nn.BCELoss(reduction="none")

    def _forensic_loss(
        self,
        forensic_outputs: Dict[str, torch.Tensor] | None,
        forensic_labels: Dict[str, torch.Tensor] | None,
        forensic_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        if not forensic_outputs or not forensic_labels:
            if forensic_mask is None:
                return torch.tensor(0.0)

        device = None
        for value in (forensic_outputs or {}).values():
            device = value.device
            break

        if device is None and forensic_mask is not None:
            device = forensic_mask.device

        if device is None:
            device = torch.device("cpu")

        losses: list[torch.Tensor] = []

        for key, predicted in (forensic_outputs or {}).items():
            target = forensic_labels.get(key) if forensic_labels is not None else None
            if target is None:
                continue

            target_tensor = target.float().view_as(predicted).to(device)
            loss_map = self.forensic_bce(predicted, target_tensor)

            if forensic_mask is not None:
                mask = forensic_mask.float().view_as(predicted).to(device)
                weighted = loss_map * mask
                denom = torch.clamp(mask.sum(), min=1.0)
                losses.append(weighted.sum() / denom)
            else:
                losses.append(loss_map.mean())

        if not losses:
            return torch.tensor(0.0, device=device)

        return torch.stack(losses).mean()

    def forward(
        self,
        embedding1: torch.Tensor,
        embedding2: torch.Tensor,
        similarity_scores: torch.Tensor,
        labels: torch.Tensor,
        forensic_outputs: Dict[str, torch.Tensor] | None = None,
        forensic_labels: Dict[str, torch.Tensor] | None = None,
        forensic_mask: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, dict[str, float]]:
        labels = labels.float().view(-1)

        contrastive_loss = self.contrastive(embedding1, embedding2, labels)

        bce_target = (1.0 - labels).view_as(similarity_scores)
        bce_loss = self.bce(similarity_scores, bce_target)

        forensic_loss = self._forensic_loss(forensic_outputs, forensic_labels, forensic_mask)
        if not torch.is_tensor(forensic_loss):
            forensic_loss = torch.tensor(float(forensic_loss), device=embedding1.device)
        forensic_loss = forensic_loss.to(embedding1.device)

        total = (
            (self.contrastive_weight * contrastive_loss)
            + (self.bce_weight * bce_loss)
            + (self.forensic_weight * forensic_loss)
        )

        components = {
            "total": float(total.detach().item()),
            "contrastive": float(contrastive_loss.detach().item()),
            "bce": float(bce_loss.detach().item()),
            "forensic": float(forensic_loss.detach().item()),
        }
        return total, components
