"""Centralized configuration for offline signature model training."""

from __future__ import annotations

from pathlib import Path

import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_TRAINING_DIR = Path(__file__).resolve().parent
RAW_DATASETS_DIR = MODEL_TRAINING_DIR / "raw_datasets"
PROCESSED_DIR = MODEL_TRAINING_DIR / "processed"
CHECKPOINT_DIR = MODEL_TRAINING_DIR / "checkpoints"
EVALUATION_DIR = MODEL_TRAINING_DIR / "evaluation_results"
MANIFEST_PATH = MODEL_TRAINING_DIR / "dataset_manifest.csv"
TRAINING_LOG_PATH = MODEL_TRAINING_DIR / "training_log.csv"
FINAL_MODEL_PATH = PROJECT_ROOT / "models" / "signverify_model.pth"
MODEL_METADATA_PATH = PROJECT_ROOT / "models" / "model_metadata.json"

INPUT_SIZE = (224, 224)
EMBEDDING_DIM = 256
BATCH_SIZE = 64
LEARNING_RATE = 1e-4
WEIGHT_DECAY = 1e-5
NUM_EPOCHS = 100
WARMUP_EPOCHS = 5
CONTRASTIVE_MARGIN = 1.0
TRIPLET_MARGIN = 0.5
DROPOUT_RATE = 0.4
POSITIVE_PAIRS_PER_SIGNER = 276
NEGATIVE_PAIRS_PER_SIGNER = 720
TRAIN_VAL_TEST_SPLIT = (0.70, 0.15, 0.15)
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
NUM_WORKERS = 4
PIN_MEMORY = True
EARLY_STOPPING_PATIENCE = 15
LR_SCHEDULER = "cosine_annealing_warm_restarts"
SCHEDULER_T0 = 10
SCHEDULER_T_MULT = 2
FREEZE_BACKBONE_EPOCHS = 10
GRADIENT_ACCUMULATION_STEPS = 4
PAIR_SAMPLES_PER_EPOCH = 500000
TRIPLET_SAMPLES_PER_EPOCH = 300000
SEED = 42

FORGERY_OBSERVATION_KEYS = [
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

DATASET_LANGUAGE_MAP = {
    "GPDS-960": "Latin",
    "GPDS-Synthetic": "Latin",
    "CEDAR": "English",
    "BHSig260-Hindi": "Hindi",
    "BHSig260-Bengali": "Bengali",
    "MCYT-75": "Spanish",
    "UTSig": "Persian",
    "SigComp2011-Dutch": "Dutch",
    "SigComp2011-Chinese": "Chinese",
    "SigWIComp2015-Bengali": "Bengali",
    "Kaggle-Mixed": "Mixed",
    "NIST-SD19": "English",
}
