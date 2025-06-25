#!/bin/bash

set -uxo pipefail

# Validate required environment variables
if [ -z "$PYTHON_VERSION" ] || [ -z "$INDEX_URL" ]; then
  echo "Error: PYTHON_VERSION and INDEX_URL must be set"
  exit 1
fi

# Set Python path
python_dir="/opt/python/$PYTHON_VERSION"
export PATH="$python_dir/bin:$PATH"

echo 'Python version:'
which python
python --version

# Configure git
git config --global user.name 'therockbot'
git config --global user.email 'therockbot@amd.com'

# Checkout repositories
cd /workspace
./external-builds/pytorch/pytorch_torch_repo.py checkout
./external-builds/pytorch/pytorch_audio_repo.py checkout
./external-builds/pytorch/pytorch_vision_repo.py checkout

# Reset PyTorch repository
cd /workspace/external-builds/pytorch/pytorch
git am --abort || true
git reset --hard
git clean -xfd

# Install dependencies
python -m pip install --index-url "$INDEX_URL" torch
python -m pip install pytest pytest-xdist numpy psutil expecttest hypothesis

# Verify installed packages
python -m pip show torch
python -m pip show expecttest
python -c 'import torch; print(torch.__file__); print(torch.__version__)'

# Run ROCm SMI for debug
rocm-smi || true

# Run tests from a clean directory
mkdir -p /tmp/test_dir
cd /tmp/test_dir

set +e
EXIT_CODE=0
for test_file in \
  /workspace/external-builds/pytorch/pytorch/test/test_nn.py \
  /workspace/external-builds/pytorch/pytorch/test/test_torch.py \
  /workspace/external-builds/pytorch/pytorch/test/test_cuda.py \
  /workspace/external-builds/pytorch/pytorch/test/test_ops.py \
  /workspace/external-builds/pytorch/pytorch/test/test_unary_ufuncs.py \
  /workspace/external-builds/pytorch/pytorch/test/test_binary_ufuncs.py \
  /workspace/external-builds/pytorch/pytorch/test/test_autograd.py \
  /workspace/external-builds/pytorch/pytorch/test/inductor/test_torchinductor.py; do
    python -m pytest "$test_file" -v --continue-on-collection-errors || EXIT_CODE=$?
done
