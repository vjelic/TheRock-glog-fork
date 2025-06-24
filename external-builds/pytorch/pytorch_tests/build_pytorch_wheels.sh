#!/bin/bash
set -xeuo pipefail

python_dir="/opt/python/${PYTHON_VERSION}"
export PATH="$python_dir/bin:$PATH"

# Step 1: Clone and checkout repos
cd /workspace
./external-builds/pytorch/pytorch_torch_repo.py checkout
./external-builds/pytorch/pytorch_audio_repo.py checkout
./external-builds/pytorch/pytorch_vision_repo.py checkout

# Step 2: Clean the PyTorch repo now that it exists
cd /workspace/external-builds/pytorch/pytorch
git am --abort || true
git reset --hard
git clean -xfd

# Step 3: Build and test
cd /workspace
mkdir -p /tmp/pipcache

./external-builds/pytorch/build_prod_wheels.py \
  --pip-cache-dir /tmp/pipcache \
  --index-url "https://${S3_CLOUDFRONT}/${S3_SUBDIR}/${AMDGPU_FAMILIES}/" \
  build \
  --install-rocm \
  --clean \
  --output-dir "$PACKAGE_DIST_DIR"

python -m pip install "$PACKAGE_DIST_DIR"/torch-*.whl
rocm-smi

cd /workspace/external-builds/pytorch/pytorch
python -m pip install pytest pytest-xdist

export PYTORCH_TEST_WITH_ROCM=1
set +e
EXIT_CODE=0
pytest test/test_nn.py -v --continue-on-collection-errors || EXIT_CODE=$?
pytest test/test_torch.py -v --continue-on-collection-errors || EXIT_CODE=$?
pytest test/test_cuda.py -v --continue-on-collection-errors || EXIT_CODE=$?
pytest test/test_ops.py -v --continue-on-collection-errors || EXIT_CODE=$?
pytest test/test_unary_ufuncs.py -v --continue-on-collection-errors || EXIT_CODE=$?
pytest test/test_binary_ufuncs.py -v --continue-on-collection-errors || EXIT_CODE=$?
pytest test/test_autograd.py -v --continue-on-collection-errors || EXIT_CODE=$?
pytest torch/_inductor/test_torchinductor.py -v --continue-on-collection-errors || EXIT_CODE=$?
exit $EXIT_CODE
