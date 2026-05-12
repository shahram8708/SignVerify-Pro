# SignVerify Pro

### AI-powered offline signature verification — three capture modes, 25 forensic dimensions, zero cloud dependency.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![PyQt6](https://img.shields.io/badge/UI-PyQt6-41CD52?logo=qt&logoColor=white)](https://www.riverbankcomputing.com/software/pyqt/)
[![PyTorch](https://img.shields.io/badge/ML-PyTorch-EE4C2C?logo=pytorch&logoColor=white)](https://pytorch.org/)
[![SQLite](https://img.shields.io/badge/Database-SQLite-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![License](https://img.shields.io/badge/License-Not%20Specified-lightgrey)](LICENSE)
[![Version](https://img.shields.io/badge/Version-1.0.0-informational)](config.py)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-0078D6)](build_exe.ps1)

---

## Table of Contents

1. [About the Project](#about-the-project)
2. [Key Features](#key-features)
3. [Tech Stack](#tech-stack)
4. [Project Structure](#project-structure)
5. [Getting Started](#getting-started)
   - [Prerequisites](#prerequisites)
   - [Installation](#installation)
   - [Environment Variables](#environment-variables)
   - [Running the Project](#running-the-project)
6. [Usage](#usage)
7. [Verification Modes](#verification-modes)
8. [Configuration](#configuration)
9. [Model Training](#model-training)
10. [Testing](#testing)
11. [Deployment](#deployment)
12. [Licence Tiers](#licence-tiers)
13. [Contributing](#contributing)
14. [Roadmap](#roadmap)
15. [Acknowledgements](#acknowledgements)
16. [Contact / Author](#contact--author)

---

## About the Project

Handwritten signature verification has always been a human expert's game — slow, expensive, and inconsistent. SignVerify Pro brings that capability to a desktop application that runs entirely offline, with no subscription, no API keys, and no data leaving the machine.

At its core is a custom Siamese neural network built on a modified ResNet50 backbone, trained to compare signature pairs across 25 forensic dimensions: pen lift patterns, letter formation, baseline consistency, slant angle, pressure distribution, loop proportions, and more. Every verification produces a confidence score, a human-readable reason, and a breakdown of each forensic observation — the same dimensions a trained document examiner would consider.

The application is built for bank fraud analysts, notaries, HR departments, and forensic examiners who need a reliable, auditable, and privacy-respecting tool that can fit into an existing workflow without IT infrastructure changes.

---

## Key Features

- **Three capture modes** cover every real-world scenario: screen detection for documents open on-screen, upload or live camera for physical documents, and ad-hoc free-form comparison for any two images.
- **Siamese ResNet50 architecture** with multi-scale feature aggregation (layers 2, 3, and 4) produces 256-dimensional L2-normalised embeddings for robust signature representation.
- **25 forensic observation dimensions** including pen lift score, slant angle, pressure pattern, tremor assessment, retouching indicators, and rhythm pattern are scored per verification.
- **Temperature-scaled confidence** via logit rescaling gives calibrated probability estimates rather than raw neural network outputs.
- **OpenCV-based automatic signature detection** finds likely signature regions in screenshots using adaptive thresholding and connected-component analysis, with adjustable sensitivity.
- **People database** stores reference signatures with thumbnail previews, notes, and full verification history per person backed by SQLite via SQLAlchemy ORM.
- **Machine-tied encryption** uses PBKDF2-HMAC-SHA256 derived from the Windows MachineGUID (or a generated UUID on other platforms) to protect sensitive stored settings with Fernet symmetric encryption.
- **Professional PDF reports** generated with ReportLab include side-by-side signature images, verdict badges, confidence bars, and a full observations table with page numbering.
- **Offline model training pipeline** supports 12 public signature datasets spanning Latin, Hindi, Bengali, Chinese, Dutch, Spanish, and Persian scripts.
- **PyInstaller packaging** produces a self-contained Windows executable with a one-command PowerShell build script.
- **Licence tier gating** controls daily verification limits and export features across FREE, PROFESSIONAL, and ENTERPRISE tiers without a remote licence server.
- **Rotating file logger** with a sensitive data filter prevents accidental logging of model paths, thumbnail blobs, or decrypted values.

---

## Tech Stack

### Frontend / UI
| Library | Role |
|---|---|
| PyQt6 | Desktop GUI framework, all screens, dialogs, and widgets |
| Segoe UI (system font) | Typography throughout the application |

### Backend / Logic
| Library | Role |
|---|---|
| Python 3.10+ | Application language |
| python-dotenv | Environment variable loading from `.env` |
| cryptography (Fernet, PBKDF2HMAC) | Machine-tied encryption for settings |
| pywin32 | Windows registry access for MachineGUID |
| psutil | System memory and CPU info during training |

### Machine Learning
| Library | Role |
|---|---|
| PyTorch | Siamese network training and inference |
| torchvision (ResNet50_Weights.IMAGENET1K_V2) | Pre-trained backbone |
| scikit-learn | EER calculation and evaluation metrics |
| scipy | Statistical utilities during evaluation |
| albumentations | Training-time data augmentation |
| numpy | Tensor and array operations |
| tqdm | Training progress bars |
| pandas | Dataset manifest (CSV) handling |
| matplotlib / seaborn | Evaluation plots |

### Computer Vision
| Library | Role |
|---|---|
| opencv-python-headless | Signature detection, image processing, camera capture |
| Pillow | Image loading, conversion, and pre-processing |
| mss | Cross-monitor screen capture |

### Database
| Library | Role |
|---|---|
| SQLite | Embedded database (zero configuration) |
| SQLAlchemy | ORM, session management, migration-free schema creation |

### Export
| Library | Role |
|---|---|
| ReportLab | PDF report generation with custom styles and page numbering |

### Dataset Acquisition
| Library | Role |
|---|---|
| gdown | Google Drive dataset downloads |
| kaggle | Kaggle API dataset downloads |

### Build / Distribution
| Tool | Role |
|---|---|
| PyInstaller | Windows `.exe` packaging |
| PowerShell (`build_exe.ps1`) | One-command build automation |

---

## Project Structure

```
SignVerify-Pro-main/
│
├── main.py                          # Application entry point — bootstraps DB, seeds data, launches MainWindow
├── config.py                        # All constants: paths, colours, screen indices, global QSS stylesheet
├── requirements.txt                 # Full dependency list
├── .env.example                     # Template for environment variable configuration
├── .gitignore                       # Standard Python gitignore
├── SignVerifyPro.spec                # PyInstaller spec file for Windows executable build
├── build_exe.ps1                    # PowerShell script that cleans and runs PyInstaller
│
├── controllers/
│   ├── database_controller.py       # All CRUD operations: persons, verifications, settings, history
│   ├── navigation_controller.py     # Screen switching via QStackedWidget index
│   ├── settings_controller.py       # Reads and writes persisted settings (detection sensitivity, model path, etc.)
│   └── verification_controller.py  # Orchestrates end-to-end verification: licence check → model → DB save
│
├── database/
│   └── db_manager.py               # SQLAlchemy engine, session factory, init_db(), get_db() context manager
│
├── models/
│   ├── base.py                      # SQLAlchemy declarative Base
│   ├── person.py                    # Person ORM model (name, signature path, thumbnail blob, notes)
│   ├── verification.py              # Verification ORM model (verdict, confidence, observations JSON, hash)
│   ├── seed_image.py                # Seed signature ORM model for demo data
│   └── settings_model.py           # Key-value settings ORM model (encrypted values)
│
├── services/
│   ├── local_model_service.py       # Loads .pth checkpoint, runs Siamese inference, applies temperature scaling
│   ├── signature_detector.py        # OpenCV adaptive threshold + connected component signature region detector
│   ├── screen_capture.py            # mss-based full-screen and region capture service
│   ├── window_enumerator.py         # Win32 window enumeration for picking an open application window
│   ├── window_capture_worker.py     # QThread worker for continuous window capture in Mode A
│   ├── camera_service.py            # OpenCV camera lifecycle management and frame conversion
│   ├── encryption_service.py        # Machine-tied PBKDF2 + Fernet encryption/decryption helpers
│   ├── export_service.py            # ReportLab PDF report builder with images, tables, and footer pagination
│   ├── image_utils.py               # Image quality assessment (sharpness, contrast, noise, resolution)
│   └── seed_service.py              # Seeds the database with example persons if it is empty on first launch
│
├── model_training/
│   ├── README_TRAINING.md           # Hardware requirements and step-by-step training guide
│   ├── config.py                    # All training hyperparameters (embedding dim, epochs, learning rate, etc.)
│   ├── model_architecture.py        # SiameseSignatureNet: ResNet50 branch + SimilarityHead + ForensicAnalysisHead
│   ├── train.py                     # Main training entrypoint with CLI argument parsing
│   ├── trainer.py                   # Training loop: forward pass, loss, backprop, checkpointing
│   ├── evaluator.py                 # EER, accuracy, ROC curve, and threshold optimisation
│   ├── loss_functions.py            # Combined contrastive + triplet + BCE loss
│   ├── signature_dataset.py         # PyTorch Dataset reading pairs from the manifest CSV
│   ├── dataset_downloader.py        # Downloads GPDS, CEDAR, BHSig260, MCYT, UTSig, SigComp, Kaggle datasets
│   ├── dataset_processor.py         # Normalises raw datasets into a unified manifest CSV
│   ├── data_augmentation.py         # Albumentations pipeline for training-time augmentation
│   ├── forensic_feature_extractor.py # Handcrafted CV features + model score mapping to 25 observations
│   └── export_model.py              # Bundles final checkpoint and metadata into models/signverify_model.pth
│
├── ui/
│   ├── main_window.py               # Top-level QMainWindow: sidebar + QStackedWidget screen container
│   ├── base_screen.py               # Abstract base class all screens inherit from
│   ├── sidebar.py                   # Navigation sidebar with active-state highlighting
│   │
│   ├── screens/
│   │   ├── home_screen.py           # Dashboard: today's stats, recent verifications, quick action cards
│   │   ├── database_screen.py       # People database: add, edit, search, delete persons
│   │   ├── verification_hub.py      # Mode selection hub — entry point for all three verification modes
│   │   ├── mode_a_screen.py         # Mode A: window picker → screenshot → detect → crop → verify
│   │   ├── mode_b_screen.py         # Mode B: person selector → upload or camera capture → verify
│   │   ├── mode_c_screen.py         # Mode C: upload or capture two images → ad-hoc verify
│   │   ├── results_screen.py        # Full forensic results with confidence bar, observations table, export
│   │   ├── history_screen.py        # Paginated verification history with filter and flag controls
│   │   └── settings_screen.py       # Model path, inference device, detection sensitivity, licence upgrade
│   │
│   ├── dialogs/
│   │   ├── add_record_dialog.py     # Dialog for adding a new person to the database
│   │   ├── camera_dialog.py         # Live camera preview dialog for capturing a signature photo
│   │   ├── crop_dialog.py           # Interactive crop tool for trimming captured images
│   │   ├── edit_verification_dialog.py # Dialog to view, flag, or annotate a past verification
│   │   └── window_picker_dialog.py  # Scrollable grid of open windows with thumbnails for Mode A selection
│   │
│   └── widgets/
│       ├── confidence_bar.py         # Animated gradient confidence percentage bar widget
│       ├── observations_table.py     # 25-row forensic observations table with score and rating columns
│       ├── signature_preview_label.py # Zoomable signature image preview label
│       ├── verdict_badge.py          # Coloured MATCH / MISMATCH / INCONCLUSIVE badge widget
│       └── window_card_widget.py     # Clickable card showing a window thumbnail and title
│
└── utils/
    ├── licence_manager.py            # Singleton tier gating: FREE / PROFESSIONAL / ENTERPRISE feature checks
    ├── logger.py                     # Rotating file + console logger with sensitive data filter
    ├── thread_workers.py             # QThread workers for non-blocking model inference and PDF export
    ├── validators.py                 # File MIME type and image path validation helpers
    └── window_thumbnail_worker.py    # Background worker for fetching window thumbnails in the picker dialog
```

---

## Getting Started

### Prerequisites

Before you begin, make sure you have the following installed:

| Tool | Minimum Version | Install Link |
|---|---|---|
| Python | 3.10 | https://www.python.org/downloads/ |
| pip | 23+ | Bundled with Python |
| Git | Any recent version | https://git-scm.com/ |
| CUDA (optional, GPU training/inference) | 11.8 | https://developer.nvidia.com/cuda-downloads |
| PowerShell (Windows exe build only) | 5.1+ | Bundled with Windows |

> On Windows, `pywin32` is used for reading the MachineGUID from the registry. Install it as part of `requirements.txt` — no separate step needed.

---

### Installation

**1. Clone the repository**

```bash
git clone https://github.com/shahram8708/SignVerify-Pro.git
cd SignVerify-Pro
```

**2. Create and activate a virtual environment**

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# Linux / macOS
python -m venv .venv
source .venv/bin/activate
```

**3. Install all dependencies**

```bash
pip install -r requirements.txt
```

> PyTorch with CUDA support is included in `requirements.txt` as `torch`, `torchvision`, and `torchaudio`. If you want a specific CUDA build, install from https://pytorch.org/get-started/locally/ before running the step above.

**4. Copy and configure the environment file**

```bash
cp .env.example .env
```

Edit `.env` with your preferred settings (see [Environment Variables](#environment-variables) below).

**5. Place the pre-trained model**

Download or copy `signverify_model.pth` into the `models/` directory:

```
models/
└── signverify_model.pth
```

If no pre-trained model is available, see [Model Training](#model-training) to train your own.

---

### Environment Variables

All environment variables are loaded from a `.env` file in the project root via `python-dotenv`. Create yours by copying `.env.example`.

| Variable | Description | Example |
|---|---|---|
| `MODEL_PATH` | Path to the `.pth` model checkpoint used for inference | `models/signverify_model.pth` |
| `APP_SECRET_SALT` | Salt string used with the machine identity to derive the Fernet encryption key | `signverifypro_unique_salt_2024` |
| `LICENCE_TIER` | Starting licence tier (`FREE`, `PROFESSIONAL`, or `ENTERPRISE`) | `FREE` |
| `APP_VERSION` | Semantic version shown in the UI and metadata | `1.0.0` |
| `DB_PATH` | SQLite database filename or absolute path | `signverify.db` |
| `SIGNATURES_DIR` | Directory name under app data for persisted signature image files | `signatures` |
| `LOG_LEVEL` | Logging verbosity (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |

> **Important:** `APP_SECRET_SALT` is combined with the machine's unique hardware identifier (Windows MachineGUID or a generated UUID on other platforms) to derive the encryption key. Changing this value after setup will make previously encrypted settings unreadable.

---

### Running the Project

**Development mode**

```bash
python main.py
```

The application will:
1. Load environment variables from `.env`
2. Initialise the SQLite database (creates tables if they do not exist)
3. Seed the database with example persons if it is empty
4. Launch the PyQt6 main window maximised

**With a specific log level**

```bash
LOG_LEVEL=DEBUG python main.py
```

**Logs** are written to:
- `logs/signverify.log` during development
- `%APPDATA%\SignVerifyPro\logs\signverify.log` when running the compiled executable

The log file rotates at 5 MB and keeps 3 backup files.

---

## Usage

### Launching a Verification

Open the application and choose your mode from the **Verification Hub** screen:

**Mode A — Screen Detection**
1. Click **Mode A** in the Verification Hub.
2. Click **Pick Window** to choose any open application window (a scrollable grid of thumbnails appears).
3. Click **Capture** to take a screenshot of the selected window.
4. Click **Detect Signatures** to run OpenCV region detection. Detected regions are highlighted with bounding boxes.
5. Click a detected region to select it as the submitted signature.
6. Choose the reference person from the database and click **Verify**.

**Mode B — Upload or Camera**
1. Click **Mode B** in the Verification Hub.
2. Select a person from the database — their stored reference signature loads automatically.
3. In the **Upload** tab, browse to the submitted signature image. In the **Camera** tab, open the live camera preview and capture a photo.
4. Click **Verify**.

**Mode C — Ad-hoc Comparison**
1. Click **Mode C** in the Verification Hub.
2. Load Signature 1 (reference) via file upload or camera capture.
3. Load Signature 2 (submitted) via file upload or camera capture.
4. Click **Verify**. No database lookup is performed.

### Reading the Results Screen

After any verification completes, the Results screen shows:

- A **verdict badge**: `MATCH` (green), `MISMATCH` (red), or `INCONCLUSIVE` (amber)
- A **confidence bar** showing the temperature-scaled probability as a percentage
- A **reason** paragraph generated from the 25 forensic observations
- An **observations table** with all 25 forensic dimension scores and qualitative ratings
- Side-by-side **signature previews**
- **Export to PDF** button (Professional/Enterprise tier)
- **Copy JSON** button for raw result data

### Managing the People Database

Navigate to **Database** in the sidebar to:
- Add a person with their reference signature (upload or camera capture)
- Edit a person's name, notes, or reference image
- View all verifications performed against a person
- Delete a person (associated verifications retain `person_id = NULL`)

---

## Verification Modes

| Mode | Code | Description |
|---|---|---|
| Screen Detection | `A_SCREEN` | Captures an open application window, auto-detects signature regions using OpenCV |
| Upload | `B_UPLOAD` | Compares a database person's stored reference against an uploaded image file |
| Camera | `B_CAMERA` | Compares a database person's stored reference against a live camera capture |
| Ad-hoc | `C_ADHOC` | Compares any two signature images without a database person lookup |

Each verification result is stored in the `verifications` table with a SHA-256 hash of the raw response JSON for integrity tracking.

---

## Configuration

### Application Settings (stored in database, editable via Settings screen)

| Setting Key | Description | Default |
|---|---|---|
| `model_path` | Path to the `.pth` model file | `models/signverify_model.pth` |
| `inference_device` | Compute device for inference (`auto`, `cpu`, `cuda`) | `auto` |
| `detection_sensitivity` | OpenCV signature detector sensitivity (0.0 to 1.0) | `0.5` |
| `aspect_ratio_min` | Minimum bounding box aspect ratio for detected regions | `1.5` |
| `aspect_ratio_max` | Maximum bounding box aspect ratio for detected regions | `8.0` |
| `licence_tier` | Active licence tier (encrypted at rest) | `FREE` |

Settings are persisted in the `settings` SQLite table. Values marked as sensitive are stored encrypted using the machine-derived Fernet key.

### Colour Palette (defined in `config.py`)

The entire UI colour palette is centralised in `config.py` as Python constants (e.g., `C_NAVY = "#0A1628"`, `C_BLUE = "#1565C0"`, `C_GOLD = "#F9A825"`). The global Qt stylesheet (`GLOBAL_QSS`) references these constants, making theming a single-file change.

### Window Size Defaults

```python
MIN_WINDOW_WIDTH = 1280
MIN_WINDOW_HEIGHT = 800
SIDEBAR_WIDTH = 220
```

---

## Model Training

The `model_training/` folder contains the complete end-to-end pipeline for training the offline Siamese model from scratch.

### Architecture Summary

The model is `SiameseSignatureNet`, which consists of:

1. **`SignatureFeatureExtractor`** — A ResNet50 backbone modified to accept single-channel (grayscale) input via weight averaging of the original RGB conv1 weights. Multi-scale features from layers 2, 3, and 4 are pooled and concatenated, then projected to a 256-dimensional L2-normalised embedding.

2. **`SimilarityHead`** — Takes two embeddings, builds pair features (absolute difference, element-wise product, cosine similarity), and outputs a scalar similarity probability via a sigmoid-activated MLP.

3. **`ForensicAnalysisHead`** — Takes the same pair features and outputs 25 individual forensic scores through dedicated branches sharing a common linear layer.

### Training Hyperparameters (from `model_training/config.py`)

| Parameter | Value |
|---|---|
| Input size | 224 × 224 |
| Embedding dimension | 256 |
| Batch size | 64 |
| Learning rate | 1e-4 (AdamW) |
| Weight decay | 1e-5 |
| Epochs | 100 |
| Warmup epochs | 5 |
| Backbone freeze epochs | 10 |
| Scheduler | Cosine Annealing with Warm Restarts (T0=10, T_mult=2) |
| Early stopping patience | 15 |
| Gradient accumulation steps | 4 |
| Train / Val / Test split | 70% / 15% / 15% |
| Random seed | 42 |

### Supported Training Datasets

| Dataset | Script |
|---|---|
| GPDS 960 | Auto-downloaded |
| GPDS Synthetic | Auto-downloaded |
| CEDAR | Auto-downloaded |
| BHSig260 Hindi | Auto-downloaded |
| BHSig260 Bengali | Auto-downloaded |
| MCYT 75 | Auto-downloaded |
| UTSig (Persian) | Auto-downloaded |
| SigComp 2011 Dutch | Auto-downloaded |
| SigComp 2011 Chinese | Auto-downloaded |
| SigWIComp 2015 Bengali | Auto-downloaded |
| Kaggle Mixed | Requires Kaggle credentials |
| NIST SD19 | Auto-downloaded |

### Training Steps

**Step 1 — Configure Kaggle credentials (for Kaggle datasets)**

```bash
mkdir -p ~/.kaggle
echo '{"username":"YOUR_USERNAME","key":"YOUR_API_KEY"}' > ~/.kaggle/kaggle.json
chmod 600 ~/.kaggle/kaggle.json
```

**Step 2 — Download all datasets**

```bash
python -m model_training.train --download-datasets
```

**Step 3 — Train the model**

```bash
python -m model_training.train
```

**Step 4 — Override training parameters (optional)**

```bash
python -m model_training.train --epochs 50 --batch-size 32 --device cuda
```

**Step 5 — Resume from checkpoint**

```bash
python -m model_training.train --resume model_training/checkpoints/best_model.pth
```

**Step 6 — Evaluate an existing checkpoint without retraining**

```bash
python -m model_training.train --eval-only --resume model_training/checkpoints/best_model.pth
```

The final model is automatically exported to `models/signverify_model.pth` and `models/model_metadata.json`.

### Hardware Requirements

| Configuration | Specs | Estimated Training Time |
|---|---|---|
| CPU only | 8-core i7 / Ryzen 7, 32 GB RAM, 500 GB disk | 5 to 8 days for 100 epochs |
| Recommended GPU | NVIDIA RTX 3070 / 4070 (8 GB VRAM), 32 GB RAM | 10 to 20 hours for 100 epochs |
| High-end GPU | NVIDIA RTX 4090 / A100 (24 GB VRAM), 64 GB RAM, NVMe | 4 to 8 hours for 100 epochs |

> For production deployment, distribute the pre-trained `signverify_model.pth` (approximately 150 to 200 MB) with the installer. End users do not need to run the training pipeline.

---

## Testing

No automated test suite is present in this repository at this time. Manual testing has been performed against the three verification modes, the database CRUD operations, the export pipeline, and the encryption service.

If you would like to contribute tests, the natural candidates are:

- Unit tests for `services/encryption_service.py` (encrypt / decrypt round-trip)
- Unit tests for `services/image_utils.py` (quality assessment on known images)
- Unit tests for `utils/validators.py` (MIME type validation)
- Integration tests for `controllers/verification_controller.py` with a mock model service
- UI smoke tests using `pytest-qt`

---

## Deployment

### Windows Standalone Executable

SignVerify Pro ships as a self-contained Windows executable built with PyInstaller.

**Step 1 — Activate the virtual environment**

```powershell
.venv\Scripts\activate
```

**Step 2 — Run the build script**

```powershell
.\build_exe.ps1
```

This script:
1. Verifies the virtual environment exists at `.venv\Scripts\python.exe`
2. Cleans the `build/`, `dist/`, and `__pycache__/` directories
3. Runs PyInstaller with `--noconfirm --clean` against `SignVerifyPro.spec`
4. Confirms the output executable exists at `dist\SignVerifyPro\SignVerifyPro.exe`

**Step 3 — Distribute the output folder**

```
dist/
└── SignVerifyPro/
    ├── SignVerifyPro.exe    # Main executable
    ├── assets/              # Icons, fonts, seed signatures (bundled by the spec)
    └── ...                  # All required DLLs and Python packages
```

Place `signverify_model.pth` alongside the executable in `dist/SignVerifyPro/models/` before distributing.

### Linux / macOS (Development Run)

The application runs in development mode on Linux and macOS as long as PyQt6 and all dependencies are installed. The `pywin32` dependency is Windows-only and is used only inside conditional `os.name == "nt"` branches, so it can be omitted from the install on non-Windows platforms.

```bash
pip install -r requirements.txt  # omit pywin32 on Linux/macOS
python main.py
```

### Data Locations (at Runtime)

| Platform | App Data Directory |
|---|---|
| Windows | `%APPDATA%\SignVerifyPro\` |
| Linux / macOS | `~/.signverifypro/` |

The database (`signverify.db`), signature image files (`signatures/`), log files (`logs/`), and temp files (`temp/`) are all created inside this directory automatically on first launch.

---

## Licence Tiers

| Feature | FREE | PROFESSIONAL | ENTERPRISE |
|---|---|---|---|
| Daily verifications | 10 per day | Unlimited | Unlimited |
| PDF export | No | Yes | Yes |
| CSV export | No | Yes | Yes |
| All three verification modes | Yes | Yes | Yes |
| People database | Yes | Yes | Yes |
| Verification history | Yes | Yes | Yes |

The tier is read from the `LICENCE_TIER` environment variable at startup and persisted in the settings database. It can be upgraded from the **Settings** screen.

---

## Contributing

Contributions are welcome. Here is how to get started:

**1. Fork the repository and create a feature branch**

```bash
git checkout -b feature/your-feature-name
```

**2. Make your changes**

Follow the existing code style: type-annotated Python, `from __future__ import annotations`, docstrings on all public classes and functions, and controller/service/model separation of concerns.

**3. Commit with a clear message**

```bash
git commit -m "feat: add batch export to CSV from history screen"
```

**4. Push and open a Pull Request**

```bash
git push origin feature/your-feature-name
```

**Reporting Bugs**

Open an issue with the following template:

```
**Describe the bug**
A clear description of what went wrong.

**Steps to reproduce**
1. Go to...
2. Click...
3. See error

**Expected behaviour**
What you expected to happen.

**Logs**
Paste relevant lines from signverify.log (remove any sensitive file paths).

**Environment**
- OS and version
- Python version
- GPU (if relevant)
```

**Requesting Features**

Open an issue titled `[Feature Request]: your feature idea` and describe the use case and the behaviour you would expect.

---

## Roadmap

Based on the current codebase, these are natural next steps:

| Item | Status |
|---|---|
| Core Siamese model with 25 forensic dimensions | Done |
| Three verification modes (screen, upload/camera, ad-hoc) | Done |
| People database with SQLAlchemy | Done |
| PDF export via ReportLab | Done |
| Machine-tied encryption | Done |
| PyInstaller Windows build pipeline | Done |
| Licence tier gating | Done |
| Automated test suite (pytest, pytest-qt) | Planned |
| Batch verification from a folder of images | Planned |
| CSV export of verification history | Planned (gated behind Professional tier) |
| macOS and Linux packaged builds | Planned |
| Pre-trained model distribution | Planned |
| Model fine-tuning on custom datasets within the UI | Planned |
| Dark mode theme | Planned |
| REST API mode for headless integration | Under consideration |

---

## Acknowledgements

SignVerify Pro builds on the shoulders of a solid open-source ecosystem:

- **PyTorch and torchvision** — the backbone of the entire ML pipeline, including the pre-trained ResNet50 weights from ImageNet-1K V2.
- **PyQt6 / Qt** — the cross-platform GUI toolkit powering the entire desktop interface.
- **SQLAlchemy** — the ORM layer that makes the database code clean and database-agnostic.
- **OpenCV** — the computer vision engine behind the automatic signature region detector.
- **ReportLab** — the PDF generation library that produces professional audit-ready reports.
- **cryptography** — the library providing PBKDF2-HMAC-SHA256 key derivation and Fernet symmetric encryption.
- **albumentations** — training-time data augmentation that improves model generalisation across diverse signature styles.
- **mss** — fast cross-monitor screen capture that makes Mode A possible.
- **The public signature datasets** — GPDS, CEDAR, BHSig260, MCYT, UTSig, SigComp, SigWIComp, and NIST SD19, without which the training pipeline would not exist.

---

## Contact / Author

Author information was not found in `package.json`, git config references, or any other file in this repository.

If you are the maintainer and would like to add contact details, update this section with your GitHub profile, email address, or project website. A good place to put it:

```
GitHub: https://github.com/shahram8708
Email:  hello@signverifypro.com
Web:    https://signverifypro.com
```

Thank you for taking the time to read through this. If SignVerify Pro solves a problem you have been wrestling with, we would genuinely love to hear about it. Open an issue, send a pull request, or just say hello.