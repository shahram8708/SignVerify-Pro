"""Main training entrypoint for offline SignVerify Pro model."""

from __future__ import annotations

import argparse
import platform
import random
import time
from pathlib import Path

import numpy as np
import psutil
import torch
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingWarmRestarts
from torch.utils.data import DataLoader

try:
    from . import config
    from .dataset_downloader import DatasetDownloader
    from .dataset_processor import DatasetProcessor
    from .evaluator import Evaluator
    from .export_model import export_model_bundle
    from .loss_functions import CombinedLoss
    from .model_architecture import SiameseSignatureNet
    from .signature_dataset import SignaturePairDataset
    from .trainer import Trainer
except ImportError:
    import model_training.config as config
    from model_training.dataset_downloader import DatasetDownloader
    from model_training.dataset_processor import DatasetProcessor
    from model_training.evaluator import Evaluator
    from model_training.export_model import export_model_bundle
    from model_training.loss_functions import CombinedLoss
    from model_training.model_architecture import SiameseSignatureNet
    from model_training.signature_dataset import SignaturePairDataset
    from model_training.trainer import Trainer


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def print_system_info(device: str) -> None:
    ram_gb = psutil.virtual_memory().total / (1024 ** 3)
    cpu_name = platform.processor() or platform.machine()

    print("System information:")
    print(f"CPU: {cpu_name}")
    print(f"RAM: {ram_gb:.1f} GB")

    if device == "cuda" and torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        vram_gb = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
        print(f"GPU: {gpu_name}")
        print(f"VRAM: {vram_gb:.1f} GB")
        print("Estimated training time (100 epochs): 8 to 24 hours depending on GPU")
    else:
        print("GPU: Not in use")
        print("Estimated training time (100 epochs): 3 to 7 days on CPU")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train offline Siamese signature verification model")
    parser.add_argument("--download-datasets", action="store_true", help="Download all datasets before training")
    parser.add_argument("--epochs", type=int, default=None, help="Override NUM_EPOCHS")
    parser.add_argument("--batch-size", type=int, default=None, help="Override BATCH_SIZE")
    parser.add_argument("--resume", type=str, default=None, help="Checkpoint path to resume training")
    parser.add_argument("--eval-only", action="store_true", help="Skip training and run evaluation only")
    parser.add_argument("--device", choices=["cpu", "cuda"], default=None, help="Override compute device")
    return parser.parse_args()


def build_loaders(manifest_path: Path, batch_size: int):
    train_dataset = SignaturePairDataset(
        manifest_csv_path=manifest_path,
        split="train",
        augment=True,
        pairs_per_epoch=config.PAIR_SAMPLES_PER_EPOCH,
    )
    val_dataset = SignaturePairDataset(
        manifest_csv_path=manifest_path,
        split="val",
        augment=False,
        pairs_per_epoch=max(100000, config.PAIR_SAMPLES_PER_EPOCH // 5),
    )
    test_dataset = SignaturePairDataset(
        manifest_csv_path=manifest_path,
        split="test",
        augment=False,
        pairs_per_epoch=max(100000, config.PAIR_SAMPLES_PER_EPOCH // 5),
    )

    train_loader = DataLoader(
        train_dataset,
        batch_size=batch_size,
        shuffle=True,
        num_workers=config.NUM_WORKERS,
        pin_memory=config.PIN_MEMORY,
        drop_last=True,
    )

    val_loader = DataLoader(
        val_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=config.NUM_WORKERS,
        pin_memory=config.PIN_MEMORY,
    )

    test_loader = DataLoader(
        test_dataset,
        batch_size=batch_size,
        shuffle=False,
        num_workers=config.NUM_WORKERS,
        pin_memory=config.PIN_MEMORY,
    )

    return train_loader, val_loader, test_loader


def print_dataset_summary(manifest_frame) -> None:
    print("Dataset summary:")
    by_source = manifest_frame.groupby("dataset_source").size().to_dict()
    by_split = manifest_frame.groupby("split").size().to_dict()

    print(f"Total images: {len(manifest_frame):,}")
    print(f"Total signers: {manifest_frame['signer_id'].nunique():,}")

    for source, count in sorted(by_source.items()):
        print(f"{source}: {count:,} images")

    print("Split sizes:")
    for split_name in ["train", "val", "test"]:
        print(f"{split_name}: {int(by_split.get(split_name, 0)):,} images")


def main() -> int:
    args = parse_args()

    if args.epochs is not None:
        config.NUM_EPOCHS = int(args.epochs)
    if args.batch_size is not None:
        config.BATCH_SIZE = int(args.batch_size)
    if args.device is not None:
        config.DEVICE = args.device

    set_seed(config.SEED)

    print_system_info(config.DEVICE)

    if args.download_datasets:
        downloader = DatasetDownloader()
        downloader.download_all()

    processor = DatasetProcessor()
    manifest_frame = processor.build_manifest()
    print_dataset_summary(manifest_frame)

    train_loader, val_loader, test_loader = build_loaders(config.MANIFEST_PATH, config.BATCH_SIZE)

    model = SiameseSignatureNet(embedding_dim=config.EMBEDDING_DIM)
    model = model.to(config.DEVICE)
    model.set_backbone_trainable(False)

    print(f"Model parameters: {model.parameter_count():,}")

    optimizer = AdamW(model.parameters(), lr=config.LEARNING_RATE, weight_decay=config.WEIGHT_DECAY)
    scheduler = CosineAnnealingWarmRestarts(
        optimizer,
        T_0=config.SCHEDULER_T0,
        T_mult=config.SCHEDULER_T_MULT,
    )
    loss_fn = CombinedLoss(margin=config.CONTRASTIVE_MARGIN)

    trainer = Trainer(
        model=model,
        optimizer=optimizer,
        scheduler=scheduler,
        loss_fn=loss_fn,
        train_loader=train_loader,
        val_loader=val_loader,
        config=config,
    )

    if args.resume:
        checkpoint_path = Path(args.resume)
        if not checkpoint_path.exists():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")
        checkpoint = torch.load(checkpoint_path, map_location=config.DEVICE)
        model.load_state_dict(checkpoint["model_state_dict"])
        optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        if checkpoint.get("scheduler_state_dict"):
            scheduler.load_state_dict(checkpoint["scheduler_state_dict"])
        trainer.best_val_eer = float(checkpoint.get("best_val_eer", trainer.best_val_eer))
        trainer.best_threshold = float(checkpoint.get("best_threshold", trainer.best_threshold))
        print(f"Resumed from checkpoint: {checkpoint_path}")

    if args.eval_only:
        if args.resume is None:
            raise ValueError("--eval-only requires --resume <checkpoint>")

        eval_report = Evaluator.evaluate_on_dataset(
            model=model,
            test_loader=test_loader,
            threshold=trainer.best_threshold,
            device=config.DEVICE,
        )

        print("Final evaluation only results:")
        print(eval_report)
        return 0

    start_time = time.time()
    training_result = trainer.train()
    elapsed_hours = (time.time() - start_time) / 3600.0

    print(f"Training completed in {elapsed_hours:.2f} hours")

    eval_report = Evaluator.evaluate_on_dataset(
        model=model,
        test_loader=test_loader,
        threshold=training_result["best_threshold"],
        device=config.DEVICE,
    )

    print("Final results:")
    print(f"Best validation EER: {training_result['best_val_eer'] * 100:.2f}%")
    print(f"Optimal threshold: {training_result['best_threshold']:.4f}")

    for dataset_name, metrics in sorted(eval_report["per_dataset"].items()):
        print(f"{dataset_name}: EER={metrics['eer'] * 100:.2f}% | AUC={metrics['auc']:.4f}")

    total_pairs_used = len(train_loader.dataset) * max(1, len(training_result["history"]))
    export_info = export_model_bundle(
        model=model,
        optimal_threshold=training_result["best_threshold"],
        best_val_eer=training_result["best_val_eer"],
        total_pairs_used=total_pairs_used,
    )

    print("Export complete:")
    print(f"Model path: {export_info['model_path']}")
    print(f"Metadata path: {export_info['metadata_path']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
