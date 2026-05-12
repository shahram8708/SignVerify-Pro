"""Export utilities for production model bundle."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Iterable

import torch

from .config import FINAL_MODEL_PATH, MODEL_METADATA_PATH

DEFAULT_DATASETS = [
    "GPDS-960",
    "GPDS-Synthetic",
    "CEDAR",
    "BHSig260-Hindi",
    "BHSig260-Bengali",
    "MCYT-75",
    "UTSig",
    "SigComp2011-Dutch",
    "SigComp2011-Chinese",
    "SigWIComp2015",
    "Kaggle-Mixed",
]


def export_model_bundle(
    model,
    optimal_threshold: float,
    best_val_eer: float,
    total_pairs_used: int,
    datasets_used: Iterable[str] | None = None,
    model_version: str = "1.0.0",
    model_path: str | Path | None = None,
    metadata_path: str | Path | None = None,
) -> dict:
    final_model_path = Path(model_path or FINAL_MODEL_PATH)
    final_metadata_path = Path(metadata_path or MODEL_METADATA_PATH)

    final_model_path.parent.mkdir(parents=True, exist_ok=True)
    final_metadata_path.parent.mkdir(parents=True, exist_ok=True)

    used_datasets = list(datasets_used) if datasets_used else list(DEFAULT_DATASETS)

    metadata = {
        "model_architecture": "SiameseSignatureNet_ResNet50",
        "embedding_dim": 256,
        "input_size": (224, 224),
        "optimal_threshold": float(optimal_threshold),
        "training_eer": float(best_val_eer),
        "datasets_used": used_datasets,
        "total_training_pairs": int(total_pairs_used),
        "training_date": datetime.now().isoformat(),
        "model_version": str(model_version),
    }

    payload = {
        "model_state_dict": model.state_dict(),
        **metadata,
    }

    torch.save(payload, final_model_path)
    final_metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    return {
        "model_path": str(final_model_path),
        "metadata_path": str(final_metadata_path),
        **metadata,
    }


if __name__ == "__main__":
    print(
        "This module exports a trained model. Use export_model_bundle(...) from train.py after training completes."
    )
