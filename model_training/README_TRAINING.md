# SignVerify Pro Offline Model Training

This folder contains the end to end pipeline for training the fully offline signature verification model used by SignVerify Pro.

## Training Steps

1. Install dependencies from requirements.txt
2. Configure Kaggle credentials at ~/.kaggle/kaggle.json for Kaggle dataset download support
3. Run dataset download

```bash
python -m model_training.train --download-datasets
```

4. Start training

```bash
python -m model_training.train
```

5. Evaluate only from an existing checkpoint

```bash
python -m model_training.train --eval-only --resume model_training/checkpoints/best_model.pth
```

6. Final model bundle is exported automatically to models/signverify_model.pth and models/model_metadata.json

## Dataset Pipeline

The pipeline attempts to download and process the following sources into one unified manifest with writer independent split

1. GPDS 960
2. GPDS Synthetic
3. CEDAR
4. BHSig260 Hindi
5. BHSig260 Bengali
6. MCYT 75
7. UTSig
8. SigComp 2011 Dutch
9. SigComp 2011 Chinese
10. SigWIComp 2015 Bengali
11. Kaggle mixed signature datasets
12. NIST SD19 handwriting subsets for additional negative style variation

If any provider changes links or requires manual approvals, place extracted files under model_training/raw_datasets/<dataset_folder> and rerun train.

## Hardware Requirements

Minimum CPU only

1. 8 core CPU Intel i7 or AMD Ryzen 7
2. 32 GB RAM
3. 500 GB free disk space for datasets and intermediate artifacts
4. Estimated training time 5 to 8 days for 100 epochs

Recommended GPU

1. NVIDIA GPU with 8 GB or more VRAM such as RTX 3070 or RTX 4070
2. 32 GB RAM
3. 500 GB free disk space
4. CUDA 11.8 or newer and cuDNN 8.6 or newer
5. Estimated training time 10 to 20 hours for 100 epochs

Optimal high end GPU

1. NVIDIA RTX 4090 or A100 with 24 GB VRAM
2. 64 GB RAM
3. 1 TB NVMe SSD
4. Estimated training time 4 to 8 hours for 100 epochs

## Production Deployment Note

For production deployment, distribute the pre trained models/signverify_model.pth file of roughly 150 MB to 200 MB with the application installer. End users do not need to run training. They only need the pre trained .pth file in the models directory.
