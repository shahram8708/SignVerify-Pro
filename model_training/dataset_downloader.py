"""Automated downloader for all required signature datasets."""

from __future__ import annotations

import json
import os
import re
import tarfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests
from tqdm import tqdm

from .config import RAW_DATASETS_DIR

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}


@dataclass(frozen=True)
class DatasetSpec:
    name: str
    target_dir: str
    expected_images: int | None


DATASET_SPECS = [
    DatasetSpec("GPDS-960", "gpds_960", 51840),
    DatasetSpec("GPDS-Synthetic", "gpds_synthetic", 216000),
    DatasetSpec("CEDAR", "cedar", 2640),
    DatasetSpec("BHSig260-Hindi", "bhsig260_hindi", 5400),
    DatasetSpec("BHSig260-Bengali", "bhsig260_bengali", 8640),
    DatasetSpec("MCYT-75", "mcyt_75", 2250),
    DatasetSpec("UTSig", "utsig", 8280),
    DatasetSpec("SigComp2011-Dutch", "sigcomp2011_dutch", 1600),
    DatasetSpec("SigComp2011-Chinese", "sigcomp2011_chinese", 2400),
    DatasetSpec("SigWIComp2015-Bengali", "sigwicomp2015_bengali", 3500),
    DatasetSpec("Kaggle-Mixed", "kaggle_mixed", 14500),
    DatasetSpec("NIST-SD19", "nist_sd19", None),
]


class DatasetDownloader:
    """Downloads, extracts, and validates all mandatory datasets."""

    def __init__(self, raw_root: Path | None = None, retries: int = 3, timeout: int = 120) -> None:
        self.raw_root = Path(raw_root or RAW_DATASETS_DIR)
        self.retries = retries
        self.timeout = timeout
        self.session = requests.Session()

    def _dataset_dir(self, spec: DatasetSpec) -> Path:
        return self.raw_root / spec.target_dir

    def _count_images(self, root: Path) -> int:
        if not root.exists():
            return 0
        return sum(1 for path in root.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS)

    def _download_file(self, url: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)

        for attempt in range(1, self.retries + 1):
            try:
                with self.session.get(url, stream=True, timeout=self.timeout) as response:
                    response.raise_for_status()
                    total = int(response.headers.get("content-length", 0))

                    with output_path.open("wb") as target, tqdm(
                        total=total,
                        unit="B",
                        unit_scale=True,
                        desc=f"Downloading {output_path.name}",
                    ) as progress:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if not chunk:
                                continue
                            target.write(chunk)
                            progress.update(len(chunk))

                return output_path
            except Exception as exc:
                if attempt == self.retries:
                    raise RuntimeError(f"Failed downloading {url}: {exc}") from exc

        return output_path

    def _extract_archive(self, archive_path: Path, extract_to: Path) -> None:
        extract_to.mkdir(parents=True, exist_ok=True)
        suffix = archive_path.suffix.lower()

        if suffix == ".zip":
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(extract_to)
            return

        if suffix in {".tar", ".gz", ".tgz", ".bz2", ".xz"} or archive_path.name.endswith((".tar.gz", ".tar.bz2", ".tar.xz")):
            with tarfile.open(archive_path, "r:*") as tf:
                tf.extractall(extract_to)
            return

        raise ValueError(f"Unsupported archive format: {archive_path}")

    def _download_and_extract_archive_urls(self, urls: Iterable[str], target_dir: Path, archive_prefix: str) -> None:
        archives_dir = target_dir / "archives"
        archives_dir.mkdir(parents=True, exist_ok=True)

        for idx, url in enumerate(urls, start=1):
            sanitized = re.sub(r"[^A-Za-z0-9_.-]", "_", url.split("?")[0].split("/")[-1])
            filename = sanitized or f"{archive_prefix}_{idx}.archive"
            archive_path = archives_dir / filename

            if not archive_path.exists() or archive_path.stat().st_size == 0:
                self._download_file(url, archive_path)

            try:
                self._extract_archive(archive_path, target_dir)
            except ValueError:
                pass

    def _discover_archive_links(self, page_url: str) -> list[str]:
        response = self.session.get(page_url, timeout=self.timeout)
        response.raise_for_status()
        html = response.text

        candidates = re.findall(r'href=["\']([^"\']+\.(?:zip|tar|tar\.gz|tgz|7z))["\']', html, flags=re.IGNORECASE)
        links: list[str] = []
        for candidate in candidates:
            if candidate.startswith("http://") or candidate.startswith("https://"):
                links.append(candidate)
            else:
                base = page_url.rstrip("/")
                links.append(f"{base}/{candidate.lstrip('/')}")

        # Deduplicate while preserving order
        seen: set[str] = set()
        ordered: list[str] = []
        for link in links:
            if link in seen:
                continue
            seen.add(link)
            ordered.append(link)
        return ordered

    def _download_gpds_960(self, target_dir: Path) -> None:
        article_api = "https://api.figshare.com/v2/articles/1287360"
        response = self.session.get(article_api, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()

        files = payload.get("files", [])
        if not files:
            raise RuntimeError("Figshare GPDS-960 article returned no downloadable files")

        urls = [file_info.get("download_url") for file_info in files if file_info.get("download_url")]
        if not urls:
            raise RuntimeError("Figshare GPDS-960 article did not expose download URLs")

        self._download_and_extract_archive_urls(urls, target_dir, "gpds960")

    def _download_gpds_synthetic(self, target_dir: Path) -> None:
        page_url = "http://www.gpds.ulpgc.es/"
        links = self._discover_archive_links(page_url)
        if not links:
            raise RuntimeError(
                "Unable to discover GPDS Synthetic archive automatically. Download manually from http://www.gpds.ulpgc.es/ and extract into raw_datasets/gpds_synthetic"
            )
        self._download_and_extract_archive_urls(links, target_dir, "gpds_synthetic")

    def _download_cedar(self, target_dir: Path) -> None:
        page_url = "http://www.cedar.buffalo.edu/NIJ/data/"
        links = self._discover_archive_links(page_url)
        if not links:
            raise RuntimeError(
                "Unable to discover CEDAR archive automatically. Download manually from http://www.cedar.buffalo.edu/NIJ/data/ and extract into raw_datasets/cedar"
            )
        self._download_and_extract_archive_urls(links, target_dir, "cedar")

    def _download_bhsig260(self, target_dir: Path) -> None:
        try:
            import gdown
        except ImportError as exc:
            raise RuntimeError("gdown is required for BHSig260 download") from exc

        link = "https://drive.google.com/open?id=0B29vNACcjvzVc1RfVkg5dUh2b1E"
        archive_path = target_dir / "bhsig260_drive_download"
        target_dir.mkdir(parents=True, exist_ok=True)

        downloaded = gdown.download(link, output=str(archive_path), quiet=False, fuzzy=True)
        if downloaded is None:
            # Fallback if the link resolves to a folder
            folder_downloads = gdown.download_folder(link, output=str(target_dir), quiet=False, use_cookies=False)
            if not folder_downloads:
                raise RuntimeError("Unable to download BHSig260 from Google Drive link")

        for path in target_dir.rglob("*"):
            if path.suffix.lower() in {".zip", ".tar", ".gz", ".tgz"}:
                try:
                    self._extract_archive(path, target_dir)
                except Exception:
                    continue

    def _download_mcyt(self, target_dir: Path) -> None:
        page_url = "http://atvs.ii.uam.es/databases.html"
        links = self._discover_archive_links(page_url)
        if not links:
            raise RuntimeError(
                "Unable to discover MCYT archive automatically. Download manually from http://atvs.ii.uam.es/databases.html and extract into raw_datasets/mcyt_75"
            )
        self._download_and_extract_archive_urls(links, target_dir, "mcyt")

    def _download_utsig(self, target_dir: Path) -> None:
        url = "https://github.com/kazimfouladi/UTSig/archive/refs/heads/master.zip"
        self._download_and_extract_archive_urls([url], target_dir, "utsig")

    def _download_sigcomp2011(self, target_dir: Path) -> None:
        page_url = "http://www.iapr-tc11.org/mediawiki/index.php/ICDAR_2011_Signature_Verification_Competition_(SigComp2011)"
        links = self._discover_archive_links(page_url)
        if not links:
            raise RuntimeError(
                "Unable to discover SigComp2011 archives automatically. Download manually from ICDAR competition archive and extract into raw_datasets"
            )
        self._download_and_extract_archive_urls(links, target_dir, "sigcomp2011")

    def _download_sigwicomp2015(self, target_dir: Path) -> None:
        page_url = "https://rrc.cvc.uab.es/?ch=10"
        links = self._discover_archive_links(page_url)
        if not links:
            raise RuntimeError(
                "Unable to discover SigWIComp2015 archive automatically. Download manually from ICDAR 2015 competition archive and extract into raw_datasets/sigwicomp2015_bengali"
            )
        self._download_and_extract_archive_urls(links, target_dir, "sigwicomp2015")

    def _download_kaggle(self, target_dir: Path) -> None:
        try:
            from kaggle.api.kaggle_api_extended import KaggleApi
        except ImportError as exc:
            raise RuntimeError("kaggle package is required for Kaggle dataset downloads") from exc

        api = KaggleApi()
        api.authenticate()

        target_dir.mkdir(parents=True, exist_ok=True)
        base_slugs = [
            "robinreni/signature-verification-dataset",
            "ishanikathuria/handwritten-signatures",
            "divyanshrai/handwritten-signature",
            "leadbest/handwritten-signature-dataset",
        ]

        discovered: list[str] = []
        for dataset in api.dataset_list(search="signature"):
            ref = getattr(dataset, "ref", "")
            if ref and "signature" in ref.lower():
                discovered.append(ref)
            if len(discovered) >= 12:
                break

        slugs = list(dict.fromkeys(base_slugs + discovered))
        for slug in slugs:
            out_dir = target_dir / slug.replace("/", "__")
            out_dir.mkdir(parents=True, exist_ok=True)
            api.dataset_download_files(slug, path=str(out_dir), unzip=True, quiet=False)

    def _download_nist_sd19(self, target_dir: Path) -> None:
        page_url = "https://www.nist.gov/srd/nist-special-database-19"
        links = self._discover_archive_links(page_url)
        if not links:
            raise RuntimeError(
                "Unable to discover NIST SD19 archive automatically. Download manually from https://www.nist.gov/srd/nist-special-database-19 and extract signature-like subsets into raw_datasets/nist_sd19"
            )
        self._download_and_extract_archive_urls(links, target_dir, "nist_sd19")

    def _validate_count(self, spec: DatasetSpec, image_count: int) -> None:
        if spec.expected_images is None:
            return

        minimum_acceptable = int(spec.expected_images * 0.7)
        if image_count < minimum_acceptable:
            raise RuntimeError(
                f"Dataset {spec.name} appears incomplete: expected around {spec.expected_images} images, found {image_count}"
            )

    def download_all(self) -> dict[str, int]:
        self.raw_root.mkdir(parents=True, exist_ok=True)

        summary: dict[str, int] = {}
        errors: dict[str, str] = {}

        for spec in DATASET_SPECS:
            dataset_dir = self._dataset_dir(spec)
            dataset_dir.mkdir(parents=True, exist_ok=True)
            existing_count = self._count_images(dataset_dir)

            if existing_count > 0:
                summary[spec.name] = existing_count
                continue

            try:
                if spec.name == "GPDS-960":
                    self._download_gpds_960(dataset_dir)
                elif spec.name == "GPDS-Synthetic":
                    self._download_gpds_synthetic(dataset_dir)
                elif spec.name == "CEDAR":
                    self._download_cedar(dataset_dir)
                elif spec.name in {"BHSig260-Hindi", "BHSig260-Bengali"}:
                    self._download_bhsig260(dataset_dir)
                elif spec.name == "MCYT-75":
                    self._download_mcyt(dataset_dir)
                elif spec.name == "UTSig":
                    self._download_utsig(dataset_dir)
                elif spec.name in {"SigComp2011-Dutch", "SigComp2011-Chinese"}:
                    self._download_sigcomp2011(dataset_dir)
                elif spec.name == "SigWIComp2015-Bengali":
                    self._download_sigwicomp2015(dataset_dir)
                elif spec.name == "Kaggle-Mixed":
                    self._download_kaggle(dataset_dir)
                elif spec.name == "NIST-SD19":
                    self._download_nist_sd19(dataset_dir)

                count = self._count_images(dataset_dir)
                self._validate_count(spec, count)
                summary[spec.name] = count
            except Exception as exc:
                errors[spec.name] = str(exc)
                summary[spec.name] = self._count_images(dataset_dir)

        total_count = sum(summary.values())

        print("Download summary:")
        for name, count in summary.items():
            print(f"{name}: {count} images")

        if errors:
            print("\nDatasets requiring manual intervention:")
            for name, error_text in errors.items():
                print(f"{name}: {error_text}")

        print(f"\nTotal raw images downloaded: {total_count}")

        summary_path = self.raw_root / "download_summary.json"
        summary_path.write_text(
            json.dumps({"counts": summary, "errors": errors, "total_images": total_count}, indent=2),
            encoding="utf-8",
        )

        return summary


if __name__ == "__main__":
    DatasetDownloader().download_all()
