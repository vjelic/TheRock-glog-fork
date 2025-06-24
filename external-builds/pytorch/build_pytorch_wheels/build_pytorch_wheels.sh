#!/bin/bash
set -xuo pipefail

git config --global user.name "therockbot"
git config --global user.email "therockbot@amd.com"

python_dir="/opt/python/${PYTHON_VERSION}"
export PATH="$python_dir/bin:$PATH"

# Run repo checkouts
cd /workspace
./external-builds/pytorch/pytorch_torch_repo.py checkout
./external-builds/pytorch/pytorch_audio_repo.py checkout
./external-builds/pytorch/pytorch_vision_repo.py checkout

# Clean state for patching
cd /workspace/external-builds/pytorch/pytorch
git am --abort || true
git reset --hard
git clean -xfd

# Create pip cache
mkdir -p /tmp/pipcache

# Build wheels
cd /workspace
./external-builds/pytorch/build_prod_wheels.py \
  --pip-cache-dir /tmp/pipcache \
  --index-url "https://${S3_CLOUDFRONT}/${S3_SUBDIR}/${AMDGPU_FAMILIES}/" \
  build \
  --install-rocm \
  --clean \
  --output-dir "${PACKAGE_DIST_DIR}"

# Install for test
python -m pip install "${PACKAGE_DIST_DIR}"/torch-*.whl
python -m pip install "${PACKAGE_DIST_DIR}"/torchvision-*.whl
python -m pip install "${PACKAGE_DIST_DIR}"/torchaudio-*.whl
