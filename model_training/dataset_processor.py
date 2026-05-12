"""Dataset unification and manifest builder for signature training."""

from __future__ import annotations

import json
import random
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from PIL import Image

from .config import DATASET_LANGUAGE_MAP, MANIFEST_PATH, RAW_DATASETS_DIR, SEED, TRAIN_VAL_TEST_SPLIT
from .dataset_downloader import DATASET_SPECS, IMAGE_EXTENSIONS


@dataclass
class ImageRecord:
    image_path: str
    dataset_source: str
    local_signer_id: str
    label: str
    language: str
    width: int
    height: int


class DatasetProcessor:
    """Builds a clean writer-independent manifest from all raw datasets."""

    def __init__(self, raw_root: Path | None = None, manifest_path: Path | None = None, seed: int = SEED) -> None:
        self.raw_root = Path(raw_root or RAW_DATASETS_DIR)
        self.manifest_path = Path(manifest_path or MANIFEST_PATH)
        self.seed = seed

    @staticmethod
    def _normalize_source_name(folder_name: str) -> str:
        mapping = {
            "gpds_960": "GPDS-960",
            "gpds_synthetic": "GPDS-Synthetic",
            "cedar": "CEDAR",
            "bhsig260_hindi": "BHSig260-Hindi",
            "bhsig260_bengali": "BHSig260-Bengali",
            "mcyt_75": "MCYT-75",
            "utsig": "UTSig",
            "sigcomp2011_dutch": "SigComp2011-Dutch",
            "sigcomp2011_chinese": "SigComp2011-Chinese",
            "sigwicomp2015_bengali": "SigWIComp2015-Bengali",
            "kaggle_mixed": "Kaggle-Mixed",
            "nist_sd19": "NIST-SD19",
        }
        return mapping.get(folder_name.lower(), folder_name)

    @staticmethod
    def _infer_label(path: Path) -> str:
        text = str(path).lower()
        forgery_tokens = ["cf-", "forg", "forgery", "fake", "skilled", "counterfeit", "negative"]
        return "forgery" if any(token in text for token in forgery_tokens) else "genuine"

    @staticmethod
    def _infer_signer_id(path: Path) -> str:
        filename = path.stem.lower()
        parent_tokens = [part.lower() for part in path.parts]

        # GPDS-style name: c-xxx-yy or cf-xxx-yy
        gpds_match = re.search(r"c[f]?[-_](\d+)[-_](\d+)", filename)
        if gpds_match:
            return gpds_match.group(1)

        # Common patterns across signature datasets
        for token in [filename] + list(reversed(parent_tokens)):
            exact_num = re.fullmatch(r"\d{1,6}", token)
            if exact_num:
                return exact_num.group(0)

            embedded = re.findall(r"\d{1,6}", token)
            if embedded:
                return embedded[0]

        digest = re.sub(r"[^a-z0-9]", "", filename)
        return digest[:12] or "unknown"

    def _iter_image_paths(self) -> list[tuple[str, Path]]:
        dataset_dirs = []
        for spec in DATASET_SPECS:
            dataset_dir = self.raw_root / spec.target_dir
            if dataset_dir.exists():
                dataset_dirs.append((self._normalize_source_name(spec.target_dir), dataset_dir))

        image_paths: list[tuple[str, Path]] = []
        for source_name, dataset_dir in dataset_dirs:
            for path in dataset_dir.rglob("*"):
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
                    image_paths.append((source_name, path))

        return image_paths

    def _validate_and_collect_records(self) -> tuple[list[ImageRecord], list[str]]:
        records: list[ImageRecord] = []
        corrupted: list[str] = []

        for dataset_source, image_path in self._iter_image_paths():
            try:
                with Image.open(image_path) as image:
                    image.verify()
                with Image.open(image_path) as image:
                    width, height = image.size
            except Exception:
                corrupted.append(str(image_path))
                continue

            local_signer_id = self._infer_signer_id(image_path)
            label = self._infer_label(image_path)
            language = DATASET_LANGUAGE_MAP.get(dataset_source, "Mixed")

            records.append(
                ImageRecord(
                    image_path=str(image_path.resolve()),
                    dataset_source=dataset_source,
                    local_signer_id=local_signer_id,
                    label=label,
                    language=language,
                    width=width,
                    height=height,
                )
            )

        return records, corrupted

    def _assign_global_signers(self, records: list[ImageRecord]) -> dict[tuple[str, str], int]:
        signer_keys = sorted({(r.dataset_source, r.local_signer_id) for r in records})
        return {key: idx + 1 for idx, key in enumerate(signer_keys)}

    def _writer_independent_split(self, signer_ids: list[int]) -> dict[int, str]:
        train_ratio, val_ratio, test_ratio = TRAIN_VAL_TEST_SPLIT
        if round(train_ratio + val_ratio + test_ratio, 6) != 1.0:
            raise ValueError("TRAIN_VAL_TEST_SPLIT must sum to 1.0")

        random.seed(self.seed)
        unique_signers = sorted(set(signer_ids))
        random.shuffle(unique_signers)

        total = len(unique_signers)
        train_end = int(total * train_ratio)
        val_end = train_end + int(total * val_ratio)

        train_signers = set(unique_signers[:train_end])
        val_signers = set(unique_signers[train_end:val_end])
        test_signers = set(unique_signers[val_end:])

        split_map: dict[int, str] = {}
        for signer_id in unique_signers:
            if signer_id in train_signers:
                split_map[signer_id] = "train"
            elif signer_id in val_signers:
                split_map[signer_id] = "val"
            else:
                split_map[signer_id] = "test"

        return split_map

    def _compute_stats(self, frame: pd.DataFrame) -> dict[str, dict[str, float | int]]:
        stats: dict[str, dict[str, float | int]] = {}
        grouped = frame.groupby("dataset_source")

        for source, group in grouped:
            genuine = int((group["label"] == "genuine").sum())
            forgery = int((group["label"] == "forgery").sum())
            avg_width = float(group["width"].mean()) if not group.empty else 0.0
            avg_height = float(group["height"].mean()) if not group.empty else 0.0

            stats[source] = {
                "total_images": int(len(group)),
                "genuine_images": genuine,
                "forgery_images": forgery,
                "avg_width": round(avg_width, 2),
                "avg_height": round(avg_height, 2),
            }

        return stats

    def build_manifest(self) -> pd.DataFrame:
        self.raw_root.mkdir(parents=True, exist_ok=True)
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)

        records, corrupted = self._validate_and_collect_records()
        if not records:
            raise RuntimeError(
                "No images found under model_training/raw_datasets. Run dataset_downloader.py first or place datasets manually."
            )

        signer_map = self._assign_global_signers(records)

        rows = []
        for record in records:
            global_signer = signer_map[(record.dataset_source, record.local_signer_id)]
            rows.append(
                {
                    "image_path": record.image_path,
                    "signer_id": global_signer,
                    "dataset_source": record.dataset_source,
                    "label": record.label,
                    "language": record.language,
                    "width": record.width,
                    "height": record.height,
                }
            )

        frame = pd.DataFrame(rows)
        split_map = self._writer_independent_split(frame["signer_id"].tolist())
        frame["split"] = frame["signer_id"].map(split_map)

        frame = frame[["image_path", "signer_id", "dataset_source", "label", "language", "split", "width", "height"]]
        frame.sort_values(["dataset_source", "signer_id", "image_path"], inplace=True)
        frame.to_csv(self.manifest_path, index=False)

        stats = self._compute_stats(frame)
        stats_output = {
            "total_images": int(len(frame)),
            "total_signers": int(frame["signer_id"].nunique()),
            "split_counts": frame["split"].value_counts().to_dict(),
            "dataset_stats": stats,
            "corrupted_images": corrupted,
        }

        stats_path = self.manifest_path.with_name("dataset_stats.json")
        stats_path.write_text(json.dumps(stats_output, indent=2), encoding="utf-8")

        print("Dataset statistics summary:")
        for source, source_stats in stats.items():
            print(
                f"{source}: total={source_stats['total_images']}, genuine={source_stats['genuine_images']}, forgery={source_stats['forgery_images']}, avg_size={source_stats['avg_width']}x{source_stats['avg_height']}"
            )

        if corrupted:
            print(f"Skipped corrupted images: {len(corrupted)}")

        return frame


if __name__ == "__main__":
    processor = DatasetProcessor()
    processor.build_manifest()
