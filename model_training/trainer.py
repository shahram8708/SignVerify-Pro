"""Training loop implementation for Siamese signature model."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.cuda.amp import GradScaler, autocast

from .evaluator import compute_auc, compute_eer, compute_far, compute_frr


class Trainer:
    """Handles training, validation, checkpointing, and learning schedule."""

    def __init__(
        self,
        model,
        optimizer,
        scheduler,
        loss_fn,
        train_loader,
        val_loader,
        config,
    ) -> None:
        self.model = model
        self.optimizer = optimizer
        self.scheduler = scheduler
        self.loss_fn = loss_fn
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.config = config

        self.device = torch.device(self._cfg("DEVICE", "cpu"))
        self.grad_accum_steps = int(self._cfg("GRADIENT_ACCUMULATION_STEPS", 4))
        self.epochs = int(self._cfg("NUM_EPOCHS", 100))
        self.early_stopping_patience = int(self._cfg("EARLY_STOPPING_PATIENCE", 15))
        self.freeze_backbone_epochs = int(self._cfg("FREEZE_BACKBONE_EPOCHS", 10))
        self.checkpoint_dir = Path(self._cfg("CHECKPOINT_DIR", "model_training/checkpoints"))
        self.training_log_path = Path(self._cfg("TRAINING_LOG_PATH", "model_training/training_log.csv"))

        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.training_log_path.parent.mkdir(parents=True, exist_ok=True)

        self.use_amp = self.device.type == "cuda"
        self.scaler = GradScaler(enabled=self.use_amp)

        self.best_val_eer = float("inf")
        self.best_threshold = 0.5
        self.best_checkpoint_path: Path | None = None
        self.history: list[dict[str, Any]] = []

    def _cfg(self, name: str, default=None):
        if isinstance(self.config, dict):
            return self.config.get(name, default)
        return getattr(self.config, name, default)

    def _save_checkpoint(self, epoch: int, metrics: dict[str, float], is_best: bool = False) -> Path:
        path = self.checkpoint_dir / f"epoch_{epoch:03d}.pth"
        checkpoint = {
            "epoch": epoch,
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "scheduler_state_dict": self.scheduler.state_dict() if self.scheduler is not None else None,
            "scaler_state_dict": self.scaler.state_dict(),
            "best_val_eer": self.best_val_eer,
            "best_threshold": self.best_threshold,
            "metrics": metrics,
        }
        torch.save(checkpoint, path)

        if is_best:
            best_path = self.checkpoint_dir / "best_model.pth"
            torch.save(checkpoint, best_path)
            self.best_checkpoint_path = best_path

        return path

    def _unfreeze_backbone(self) -> None:
        if not hasattr(self.model, "set_backbone_trainable"):
            return

        self.model.set_backbone_trainable(True)

        backbone_params = []
        head_params = []
        for name, param in self.model.named_parameters():
            if not param.requires_grad:
                continue
            if name.startswith("branch."):
                backbone_params.append(param)
            else:
                head_params.append(param)

        optimizer_class = self.optimizer.__class__
        weight_decay = float(self._cfg("WEIGHT_DECAY", 1e-5))

        self.optimizer = optimizer_class(
            [
                {"params": backbone_params, "lr": 1e-5, "weight_decay": weight_decay},
                {"params": head_params, "lr": 1e-4, "weight_decay": weight_decay},
            ]
        )

        scheduler_class = self.scheduler.__class__ if self.scheduler is not None else None
        if scheduler_class is not None:
            self.scheduler = scheduler_class(
                self.optimizer,
                T_0=int(self._cfg("SCHEDULER_T0", 10)),
                T_mult=int(self._cfg("SCHEDULER_T_MULT", 2)),
            )

    @staticmethod
    def find_optimal_threshold(predictions: np.ndarray, labels_diff: np.ndarray) -> tuple[float, float]:
        thresholds = np.linspace(0.01, 0.99, 99)

        best_threshold = 0.5
        best_eer = 1.0

        genuine = predictions[labels_diff == 0]
        forged = predictions[labels_diff == 1]

        if len(genuine) == 0 or len(forged) == 0:
            return best_threshold, best_eer

        for threshold in thresholds:
            far = compute_far(genuine, forged, threshold)
            frr = compute_frr(genuine, forged, threshold)
            eer = (far + frr) / 2.0

            if eer < best_eer:
                best_eer = eer
                best_threshold = float(threshold)

        return best_threshold, best_eer

    @staticmethod
    def _far_at_target_frr(genuine: np.ndarray, forged: np.ndarray, target_frr: float = 0.001) -> float:
        thresholds = np.linspace(0.01, 0.99, 99)
        best_far = 1.0
        best_delta = float("inf")

        for threshold in thresholds:
            far = compute_far(genuine, forged, threshold)
            frr = compute_frr(genuine, forged, threshold)
            delta = abs(frr - target_frr)
            if delta < best_delta:
                best_delta = delta
                best_far = far

        return float(best_far)

    def train_epoch(self, epoch_index: int) -> dict[str, float]:
        self.model.train()

        running_total = 0.0
        running_contrastive = 0.0
        running_bce = 0.0
        running_forensic = 0.0
        num_steps = 0

        self.optimizer.zero_grad(set_to_none=True)

        for step, batch in enumerate(self.train_loader, start=1):
            if len(batch) < 3:
                continue

            image1 = batch[0].to(self.device, non_blocking=True)
            image2 = batch[1].to(self.device, non_blocking=True)
            labels = batch[2].to(self.device, non_blocking=True)

            with autocast(enabled=self.use_amp):
                outputs = self.model(image1, image2)
                loss, components = self.loss_fn(
                    outputs["embedding1"],
                    outputs["embedding2"],
                    outputs["similarity"],
                    labels,
                    outputs.get("forensic_scores"),
                )
                scaled_loss = loss / float(self.grad_accum_steps)

            self.scaler.scale(scaled_loss).backward()

            if (step % self.grad_accum_steps == 0) or (step == len(self.train_loader)):
                self.scaler.step(self.optimizer)
                self.scaler.update()
                self.optimizer.zero_grad(set_to_none=True)

            running_total += components["total"]
            running_contrastive += components["contrastive"]
            running_bce += components["bce"]
            running_forensic += components["forensic"]
            num_steps += 1

        epoch_metrics = {
            "train_loss": running_total / max(1, num_steps),
            "train_contrastive": running_contrastive / max(1, num_steps),
            "train_bce": running_bce / max(1, num_steps),
            "train_forensic": running_forensic / max(1, num_steps),
            "epoch": float(epoch_index),
        }

        return epoch_metrics

    def validate_epoch(self) -> dict[str, float]:
        self.model.eval()

        losses: list[float] = []
        predictions: list[float] = []
        labels_diff: list[int] = []

        with torch.no_grad():
            for batch in self.val_loader:
                if len(batch) < 3:
                    continue

                image1 = batch[0].to(self.device, non_blocking=True)
                image2 = batch[1].to(self.device, non_blocking=True)
                labels = batch[2].to(self.device, non_blocking=True)

                outputs = self.model(image1, image2)
                loss, _ = self.loss_fn(
                    outputs["embedding1"],
                    outputs["embedding2"],
                    outputs["similarity"],
                    labels,
                    outputs.get("forensic_scores"),
                )
                losses.append(float(loss.item()))

                batch_scores = outputs["similarity"].detach().view(-1).cpu().numpy().astype(float)
                batch_labels = labels.detach().view(-1).cpu().numpy().astype(int)

                predictions.extend(batch_scores.tolist())
                labels_diff.extend(batch_labels.tolist())

        if not predictions:
            return {
                "val_loss": float("inf"),
                "val_eer": 1.0,
                "val_auc": 0.0,
                "threshold": 0.5,
                "far_at_0_1_frr": 1.0,
            }

        pred_array = np.array(predictions, dtype=np.float32)
        label_array = np.array(labels_diff, dtype=np.int32)

        threshold, eer = self.find_optimal_threshold(pred_array, label_array)

        genuine = pred_array[label_array == 0]
        forged = pred_array[label_array == 1]
        auc = compute_auc((1 - label_array).astype(np.int32), pred_array)
        far_at_0_1_frr = self._far_at_target_frr(genuine, forged, target_frr=0.001)

        return {
            "val_loss": float(np.mean(losses)) if losses else float("inf"),
            "val_eer": float(eer),
            "val_auc": float(auc),
            "threshold": float(threshold),
            "far_at_0_1_frr": float(far_at_0_1_frr),
        }

    def _write_history_csv(self) -> None:
        if not self.history:
            return

        keys = sorted({key for row in self.history for key in row.keys()})
        with self.training_log_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=keys)
            writer.writeheader()
            for row in self.history:
                writer.writerow(row)

    def train(self) -> dict[str, Any]:
        patience_counter = 0

        for epoch in range(1, self.epochs + 1):
            if epoch == self.freeze_backbone_epochs + 1:
                self._unfreeze_backbone()

            train_metrics = self.train_epoch(epoch)
            val_metrics = self.validate_epoch()

            if self.scheduler is not None:
                self.scheduler.step(epoch - 1)

            current_lr = self.optimizer.param_groups[0]["lr"]
            merged_metrics = {
                "epoch": epoch,
                **train_metrics,
                **val_metrics,
                "learning_rate": current_lr,
            }
            self.history.append(merged_metrics)

            print(
                f"Epoch {epoch:03d}/{self.epochs} | "
                f"train_loss={train_metrics['train_loss']:.5f} | "
                f"val_loss={val_metrics['val_loss']:.5f} | "
                f"EER={val_metrics['val_eer'] * 100:.2f}% | "
                f"FAR@0.1%FRR={val_metrics['far_at_0_1_frr'] * 100:.3f}% | "
                f"AUC={val_metrics['val_auc']:.4f}"
            )

            improved = val_metrics["val_eer"] < self.best_val_eer
            if improved:
                self.best_val_eer = val_metrics["val_eer"]
                self.best_threshold = val_metrics["threshold"]
                self._save_checkpoint(epoch, merged_metrics, is_best=True)
                patience_counter = 0
            else:
                patience_counter += 1

            self._save_checkpoint(epoch, merged_metrics, is_best=False)
            self._write_history_csv()

            if patience_counter >= self.early_stopping_patience:
                print(
                    f"Early stopping triggered after {epoch} epochs. "
                    f"Best validation EER: {self.best_val_eer * 100:.2f}%"
                )
                break

        return {
            "best_val_eer": self.best_val_eer,
            "best_threshold": self.best_threshold,
            "best_checkpoint_path": str(self.best_checkpoint_path) if self.best_checkpoint_path else "",
            "history": self.history,
        }
