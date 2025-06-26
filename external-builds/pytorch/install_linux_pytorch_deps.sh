#!/bin/bash

set -uxo pipefail

# Validate required environment variables
if [ -z "$PYTHON_VERSION" ] || [ -z "$INDEX_URL" ]; then
  echo "Error: PYTHON_VERSION and INDEX_URL must be set"
  exit 1
fi

# Determine script and project root directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(realpath "$SCRIPT_DIR/../..")"

# Find Python executable
PYTHON_EXEC=$(command -v "python${PYTHON_VERSION#cp}" || command -v python3 || command -v python)
if [ -z "$PYTHON_EXEC" ]; then
  echo "Error: No Python executable found"
  exit 1
fi

# Check Python version
echo 'Python version:'
$PYTHON_EXEC --version

# Create and activate virtual environment
VENV_DIR="$ROOT_DIR/venv"
$PYTHON_EXEC -m venv "$VENV_DIR" || {
  echo "Error: Failed to create virtual environment"
  exit 1
}
source "$VENV_DIR/bin/activate" || {
  echo "Error: Failed to activate virtual environment"
  exit 1
}

# Set trap to deactivate virtual environment on exit
trap "deactivate 2> /dev/null" EXIT

# Install dependencies
python -m pip install --upgrade pip
python -m pip install --index-url "$INDEX_URL" torch
python -m pip install pytest pytest-xdist numpy psutil expecttest hypothesis

# Verify installed packages
python -m pip show torch
python -m pip show expecttest
python -c 'import torch; print(torch.__file__); print(torch.__version__)'
