#!/bin/bash

set -uxo pipefail

# Validate required environment variables
if [ -z "$PYTHON_VERSION" ]; then
  echo "Error: PYTHON_VERSION must be set"
  exit 1
fi

# Determine script and project root directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(realpath "$SCRIPT_DIR/../..")"
PYTORCH_DIR="$ROOT_DIR/external-builds/pytorch/pytorch"

# Activate virtual environment
VENV_DIR="$ROOT_DIR/venv"
if [ ! -d "$VENV_DIR" ]; then
  echo "Error: Virtual environment not found at $VENV_DIR"
  exit 1
fi
source "$VENV_DIR/bin/activate" || {
  echo "Error: Failed to activate virtual environment"
  exit 1
}

# Configure git
git config --global user.name 'therockbot'
git config --global user.email 'therockbot@amd.com'

# Checkout repositories
cd "$ROOT_DIR"
./external-builds/pytorch/pytorch_torch_repo.py checkout
./external-builds/pytorch/pytorch_audio_repo.py checkout
./external-builds/pytorch/pytorch_vision_repo.py checkout

# Reset PyTorch repository
cd "$PYTORCH_DIR"
git am --abort || true
git reset --hard
git clean -xfd

# Run tests from a clean directory
TEST_DIR="$(mktemp -d)"
cd "$TEST_DIR"
echo "Running tests in temporary directory: $TEST_DIR"

export PYTORCH_PRINT_REPRO_ON_FAILURE=0
export PYTORCH_TEST_WITH_ROCM=1

set +e
EXIT_CODE=0

# Use xdist for pytests
python -m pytest \
  "$PYTORCH_DIR/test/test_nn.py" \
  "$PYTORCH_DIR/test/test_torch.py" \
  "$PYTORCH_DIR/test/test_cuda.py" \
  "$PYTORCH_DIR/test/test_ops.py" \
  "$PYTORCH_DIR/test/test_unary_ufuncs.py" \
  "$PYTORCH_DIR/test/test_binary_ufuncs.py" \
  "$PYTORCH_DIR/test/test_autograd.py" \
  "$PYTORCH_DIR/test/inductor/test_torchinductor.py" \
  -v \
  --continue-on-collection-errors \
  -n auto || {
  EXIT_CODE=$?
  echo "Pytest failed with exit code $EXIT_CODE"
}

# Log the final exit code
echo "Final test exit code: $EXIT_CODE"

# Deactivate virtual environment
deactivate

exit 0
