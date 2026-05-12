"""Evaluation utilities for offline signature verification model."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
import torch
from sklearn.metrics import auc as sk_auc
from sklearn.metrics import det_curve, roc_auc_score, roc_curve

from .config import EVALUATION_DIR

sns.set_style("whitegrid")


def compute_far(genuine_scores: np.ndarray, forged_scores: np.ndarray, threshold: float) -> float:
    if len(forged_scores) == 0:
        return 0.0
    false_accepts = np.sum(forged_scores >= threshold)
    return float(false_accepts / len(forged_scores))


def compute_frr(genuine_scores: np.ndarray, forged_scores: np.ndarray, threshold: float) -> float:
    _ = forged_scores
    if len(genuine_scores) == 0:
        return 0.0
    false_rejects = np.sum(genuine_scores < threshold)
    return float(false_rejects / len(genuine_scores))


def compute_eer(genuine_scores: np.ndarray, forged_scores: np.ndarray) -> tuple[float, float]:
    if len(genuine_scores) == 0 or len(forged_scores) == 0:
        return 1.0, 0.5

    thresholds = np.linspace(0.01, 0.99, 500)
    best_eer = 1.0
    best_threshold = 0.5

    for threshold in thresholds:
        far = compute_far(genuine_scores, forged_scores, float(threshold))
        frr = compute_frr(genuine_scores, forged_scores, float(threshold))
        eer = (far + frr) / 2.0

        if eer < best_eer:
            best_eer = eer
            best_threshold = float(threshold)

    return float(best_eer), float(best_threshold)


def compute_auc(labels_same: np.ndarray, scores: np.ndarray) -> float:
    labels_same = np.asarray(labels_same)
    scores = np.asarray(scores)

    if len(np.unique(labels_same)) < 2:
        return 0.0

    try:
        return float(roc_auc_score(labels_same, scores))
    except Exception:
        return 0.0


def plot_roc_curve(labels_same: np.ndarray, scores: np.ndarray, output_path: Path | None = None) -> Path:
    output_dir = Path(output_path).parent if output_path else EVALUATION_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = Path(output_path) if output_path else output_dir / "roc_curve.png"

    fpr, tpr, _ = roc_curve(labels_same, scores)
    roc_auc = sk_auc(fpr, tpr)

    plt.figure(figsize=(8, 6))
    plt.plot(fpr, tpr, color="#1565C0", lw=2, label=f"ROC curve (AUC = {roc_auc:.4f})")
    plt.plot([0, 1], [0, 1], color="#9CA3AF", lw=1, linestyle="--")
    plt.xlabel("False Positive Rate")
    plt.ylabel("True Positive Rate")
    plt.title("Receiver Operating Characteristic")
    plt.legend(loc="lower right")
    plt.tight_layout()
    plt.savefig(final_path, dpi=180)
    plt.close()

    return final_path


def plot_det_curve(labels_same: np.ndarray, scores: np.ndarray, output_path: Path | None = None) -> Path:
    output_dir = Path(output_path).parent if output_path else EVALUATION_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = Path(output_path) if output_path else output_dir / "det_curve.png"

    fpr, fnr, _ = det_curve(labels_same, scores)

    plt.figure(figsize=(8, 6))
    plt.plot(fpr, fnr, color="#C62828", lw=2)
    plt.xlabel("False Acceptance Rate")
    plt.ylabel("False Rejection Rate")
    plt.title("Detection Error Tradeoff")
    plt.tight_layout()
    plt.savefig(final_path, dpi=180)
    plt.close()

    return final_path


class Evaluator:
    """Evaluates model performance across overall and per-dataset splits."""

    @staticmethod
    def evaluate_on_dataset(model, test_loader, threshold: float, device: str | torch.device = "cpu") -> dict[str, Any]:
        model.eval()
        device = torch.device(device)

        scores: list[float] = []
        labels_diff: list[int] = []
        sources: list[str] = []

        with torch.no_grad():
            for batch in test_loader:
                if len(batch) < 5:
                    continue

                image1 = batch[0].to(device, non_blocking=True)
                image2 = batch[1].to(device, non_blocking=True)
                label_batch = batch[2].detach().cpu().numpy().astype(int)

                outputs = model(image1, image2)
                sim_batch = outputs["similarity"].detach().cpu().view(-1).numpy().astype(float)

                source_batch = batch[4]
                if isinstance(source_batch, (list, tuple)):
                    src_values = [str(item) for item in source_batch]
                else:
                    src_values = [str(source_batch)] * len(sim_batch)

                scores.extend(sim_batch.tolist())
                labels_diff.extend(label_batch.tolist())
                sources.extend(src_values)

        score_array = np.array(scores, dtype=np.float32)
        label_diff_array = np.array(labels_diff, dtype=np.int32)
        labels_same = (1 - label_diff_array).astype(np.int32)

        genuine_scores = score_array[label_diff_array == 0]
        forged_scores = score_array[label_diff_array == 1]

        overall_eer, optimal_threshold = compute_eer(genuine_scores, forged_scores)
        auc_value = compute_auc(labels_same, score_array)
        far_value = compute_far(genuine_scores, forged_scores, threshold)
        frr_value = compute_frr(genuine_scores, forged_scores, threshold)

        roc_path = plot_roc_curve(labels_same, score_array)
        det_path = plot_det_curve(labels_same, score_array)

        per_dataset: dict[str, dict[str, float]] = {}
        source_array = np.array(sources)
        for dataset_name in sorted(set(sources)):
            mask = source_array == dataset_name
            ds_scores = score_array[mask]
            ds_labels_diff = label_diff_array[mask]

            ds_genuine = ds_scores[ds_labels_diff == 0]
            ds_forged = ds_scores[ds_labels_diff == 1]
            ds_eer, ds_threshold = compute_eer(ds_genuine, ds_forged)
            ds_auc = compute_auc((1 - ds_labels_diff).astype(np.int32), ds_scores)

            per_dataset[dataset_name] = {
                "eer": float(ds_eer),
                "optimal_threshold": float(ds_threshold),
                "auc": float(ds_auc),
            }

        report = {
            "overall": {
                "eer": float(overall_eer),
                "threshold_used": float(threshold),
                "optimal_threshold": float(optimal_threshold),
                "far": float(far_value),
                "frr": float(frr_value),
                "auc": float(auc_value),
                "roc_curve": str(roc_path),
                "det_curve": str(det_path),
            },
            "per_dataset": per_dataset,
        }

        print("Evaluation summary:")
        print(
            f"Overall: EER={report['overall']['eer'] * 100:.2f}% | "
            f"AUC={report['overall']['auc']:.4f} | "
            f"FAR={report['overall']['far'] * 100:.2f}% | FRR={report['overall']['frr'] * 100:.2f}%"
        )

        for key in ["CEDAR", "GPDS-960", "BHSig260-Hindi", "BHSig260-Bengali"]:
            if key in per_dataset:
                metrics = per_dataset[key]
                print(f"{key}: EER={metrics['eer'] * 100:.2f}% | AUC={metrics['auc']:.4f}")

        return report
