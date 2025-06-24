#!/bin/bash
set -xuo pipefail

cd /workspace/external-builds/pytorch/pytorch

python -m pip install pytest pytest-xdist
export PYTORCH_TEST_WITH_ROCM=1
rocm-smi

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
