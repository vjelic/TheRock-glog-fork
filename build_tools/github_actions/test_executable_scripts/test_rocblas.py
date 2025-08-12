import logging
import os
import shlex
import subprocess
from pathlib import Path
from test_hipblaslt import is_windows

THEROCK_BIN_DIR = os.getenv("THEROCK_BIN_DIR")
SCRIPT_DIR = Path(__file__).resolve().parent
THEROCK_DIR = SCRIPT_DIR.parent.parent.parent

logging.basicConfig(level=logging.INFO)

cmd = [
    f"{THEROCK_BIN_DIR}/rocblas-test",
    "--yaml",
    f"{THEROCK_BIN_DIR}/rocblas_smoke.yaml",
]
logging.info(f"++ Exec [{THEROCK_DIR}]$ {shlex.join(cmd)}")

subprocess.run(
    cmd,
    cwd=THEROCK_DIR,
    check=True,
    shell=is_windows()
)
