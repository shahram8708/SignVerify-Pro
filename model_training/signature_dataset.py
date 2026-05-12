"""PyTorch dataset definitions for pair and triplet signature training."""

from __future__ import annotations

import random
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from PIL import Image
from torch.utils.data import Dataset

from .config import INPUT_SIZE
from .data_augmentation import SignatureAugmentationPipeline


def _load_grayscale(path: str, size: tuple[int, int]) -> np.ndarray:
    with Image.open(path) as image:
        image = image.convert("L")
        image = image.resize((size[1], size[0]), Image.Resampling.LANCZOS)
        array = np.array(image, dtype=np.uint8)
    return array


def _to_tensor(image: np.ndarray) -> torch.Tensor:
    normalized = image.astype(np.float32) / 255.0
    return torch.from_numpy(normalized).unsqueeze(0)


class SignaturePairDataset(Dataset):
    """Generates online genuine and forgery pairs for Siamese training."""

    def __init__(
        self,
        manifest_csv_path: str | Path,
        split: str,
        augment: bool = True,
        pairs_per_epoch: int = 500000,
        input_size: tuple[int, int] = INPUT_SIZE,
    ) -> None:
        super().__init__()

        self.manifest_csv_path = Path(manifest_csv_path)
        if not self.manifest_csv_path.exists():
            raise FileNotFoundError(f"Manifest CSV not found: {manifest_csv_path}")

        frame = pd.read_csv(self.manifest_csv_path)
        frame = frame[frame["split"].str.lower() == str(split).lower()].copy()
        if frame.empty:
            raise RuntimeError(f"No rows found in manifest for split '{split}'")

        self.frame = frame
        self.split = str(split).lower()
        self.pairs_per_epoch = int(pairs_per_epoch)
        self.input_size = input_size

        self.augment = augment
        self.augmenter = SignatureAugmentationPipeline(input_size=input_size) if augment else None

        self.signer_sources: dict[int, str] = {}
        self.genuine_by_signer: dict[int, list[str]] = defaultdict(list)
        self.forgery_by_signer: dict[int, list[str]] = defaultdict(list)

        for row in frame.itertuples(index=False):
            signer_id = int(row.signer_id)
            image_path = str(row.image_path)
            self.signer_sources[signer_id] = str(row.dataset_source)
            if str(row.label).lower() == "genuine":
                self.genuine_by_signer[signer_id].append(image_path)
            else:
                self.forgery_by_signer[signer_id].append(image_path)

        self.signers = sorted(self.genuine_by_signer.keys())
        self.signers_with_pairs = [s for s in self.signers if len(self.genuine_by_signer[s]) >= 2]
        if not self.signers_with_pairs:
            raise RuntimeError("No signer has at least two genuine signatures for pair generation")

    def __len__(self) -> int:
        return self.pairs_per_epoch

    def _augment_if_needed(self, image: np.ndarray) -> np.ndarray:
        if self.augmenter is None:
            return image
        return self.augmenter(image)

    def _load_pair_tensors(self, path1: str, path2: str) -> tuple[torch.Tensor, torch.Tensor]:
        image1 = _load_grayscale(path1, size=self.input_size)
        image2 = _load_grayscale(path2, size=self.input_size)

        image1 = self._augment_if_needed(image1)
        image2 = self._augment_if_needed(image2)

        return _to_tensor(image1), _to_tensor(image2)

    def _sample_genuine_pair(self) -> tuple[str, str, int, str, float]:
        signer_id = random.choice(self.signers_with_pairs)
        image_paths = self.genuine_by_signer[signer_id]
        path1, path2 = random.sample(image_paths, 2)
        dataset_source = self.signer_sources.get(signer_id, "Unknown")
        return path1, path2, signer_id, dataset_source, 0.0

    def _sample_forgery_pair(self) -> tuple[str, str, int, str, float]:
        signer_id = random.choice(self.signers_with_pairs)
        genuine_path = random.choice(self.genuine_by_signer[signer_id])

        use_skilled = bool(self.forgery_by_signer.get(signer_id)) and random.random() < 0.5
        if use_skilled:
            forged_path = random.choice(self.forgery_by_signer[signer_id])
            return genuine_path, forged_path, signer_id, self.signer_sources.get(signer_id, "Unknown"), 1.0

        other_signers = [s for s in self.signers_with_pairs if s != signer_id]
        if not other_signers:
            # Fallback to skilled forgery if only one signer exists
            if self.forgery_by_signer.get(signer_id):
                forged_path = random.choice(self.forgery_by_signer[signer_id])
                return genuine_path, forged_path, signer_id, self.signer_sources.get(signer_id, "Unknown"), 1.0
            # Fallback duplicate with forged label to keep pipeline alive in tiny sets
            return genuine_path, genuine_path, signer_id, self.signer_sources.get(signer_id, "Unknown"), 1.0

        other_signer = random.choice(other_signers)
        forged_path = random.choice(self.genuine_by_signer[other_signer])
        return genuine_path, forged_path, signer_id, self.signer_sources.get(signer_id, "Unknown"), 1.0

    def __getitem__(self, idx: int):
        _ = idx
        if random.random() < 0.5:
            path1, path2, signer_id, dataset_source, label = self._sample_genuine_pair()
        else:
            path1, path2, signer_id, dataset_source, label = self._sample_forgery_pair()

        image1, image2 = self._load_pair_tensors(path1, path2)
        label_tensor = torch.tensor(label, dtype=torch.float32)

        return image1, image2, label_tensor, signer_id, dataset_source


class SignatureTripletDataset(Dataset):
    """Triplet dataset for optional triplet margin training mode."""

    def __init__(
        self,
        manifest_csv_path: str | Path,
        split: str,
        augment: bool = True,
        triplets_per_epoch: int = 300000,
        input_size: tuple[int, int] = INPUT_SIZE,
    ) -> None:
        super().__init__()

        self.manifest_csv_path = Path(manifest_csv_path)
        if not self.manifest_csv_path.exists():
            raise FileNotFoundError(f"Manifest CSV not found: {manifest_csv_path}")

        frame = pd.read_csv(self.manifest_csv_path)
        frame = frame[frame["split"].str.lower() == str(split).lower()].copy()
        if frame.empty:
            raise RuntimeError(f"No rows found in manifest for split '{split}'")

        self.input_size = input_size
        self.triplets_per_epoch = int(triplets_per_epoch)
        self.augmenter = SignatureAugmentationPipeline(input_size=input_size) if augment else None

        self.genuine_by_signer: dict[int, list[str]] = defaultdict(list)
        self.forgery_by_signer: dict[int, list[str]] = defaultdict(list)

        for row in frame.itertuples(index=False):
            signer_id = int(row.signer_id)
            image_path = str(row.image_path)
            if str(row.label).lower() == "genuine":
                self.genuine_by_signer[signer_id].append(image_path)
            else:
                self.forgery_by_signer[signer_id].append(image_path)

        self.signers = sorted(self.genuine_by_signer.keys())
        self.signers_with_pairs = [s for s in self.signers if len(self.genuine_by_signer[s]) >= 2]
        if not self.signers_with_pairs:
            raise RuntimeError("No signer has at least two genuine signatures for triplet generation")

    def __len__(self) -> int:
        return self.triplets_per_epoch

    def _load_tensor(self, path: str) -> torch.Tensor:
        image = _load_grayscale(path, size=self.input_size)
        if self.augmenter is not None:
            image = self.augmenter(image)
        return _to_tensor(image)

    def __getitem__(self, idx: int):
        _ = idx

        signer_id = random.choice(self.signers_with_pairs)
        anchor_path, positive_path = random.sample(self.genuine_by_signer[signer_id], 2)

        if self.forgery_by_signer.get(signer_id) and random.random() < 0.5:
            negative_path = random.choice(self.forgery_by_signer[signer_id])
        else:
            other_signers = [s for s in self.signers_with_pairs if s != signer_id]
            other_signer = random.choice(other_signers) if other_signers else signer_id
            if other_signer == signer_id:
                negative_pool = self.forgery_by_signer.get(signer_id, self.genuine_by_signer[signer_id])
            else:
                negative_pool = self.genuine_by_signer[other_signer]
            negative_path = random.choice(negative_pool)

        anchor = self._load_tensor(anchor_path)
        positive = self._load_tensor(positive_path)
        negative = self._load_tensor(negative_path)

        return anchor, positive, negative
