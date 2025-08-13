import logging
import os
import shlex
import subprocess
from pathlib import Path

THEROCK_BIN_DIR = Path(os.getenv("THEROCK_BIN_DIR")).resolve()
SCRIPT_DIR = Path(__file__).resolve().parent
THEROCK_DIR = SCRIPT_DIR.parent.parent.parent

logging.basicConfig(level=logging.INFO)

cmd = [
    "ctest",
    "--test-dir",
    f"{THEROCK_BIN_DIR}/rocRAND",
    "--output-on-failure",
    "--parallel",
    "8",
    "--timeout",
    "900",
]
logging.info(f"++ Exec [{THEROCK_DIR}]$ {shlex.join(cmd)}")

subprocess.run(
    cmd,
    cwd=THEROCK_DIR,
    check=True,
)
