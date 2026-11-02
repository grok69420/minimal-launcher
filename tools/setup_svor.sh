#!/bin/bash
# Film quality engine: SVOR code + removal LoRAs + Wan2.1-VACE-1.3B base (the 11 GB text encoder
# is only fetched until the fixed prompt has been encoded once).
set -e
R=/content/repos
test -d $R/SVOR/videox_fun || git clone -q --depth 1 https://github.com/xiaomi-research/SVOR.git $R/SVOR
python3 - <<'PY'
import os
from huggingface_hub import snapshot_download as d
R = "/content/repos"
d("HigherHu/SVOR", local_dir=f"{R}/SVOR/models", allow_patterns=["*.safetensors"])
pat = ["config.json", "diffusion_pytorch_model*", "Wan2.1_VAE.pth"]
if not os.path.exists(f"{R}/svor_prompt.pt"):
    pat += ["models_t5_umt5-xxl-enc-bf16.pth", "google/*"]
d("Wan-AI/Wan2.1-VACE-1.3B", local_dir=f"{R}/Wan2.1-VACE-1.3B", allow_patterns=pat)
PY
ls -la $R/SVOR/models $R/Wan2.1-VACE-1.3B
