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
    "ctest",
    "--test-dir",
    f"{THEROCK_BIN_DIR}/rocthrust",
    "--output-on-failure",
    "--parallel",
    "8",
    "--exclude-regex",
    "^copy.hip$|scan.hip",
    "--timeout",
    "300",
    "--repeat",
    "until-pass:3",
]
logging.info(f"++ Exec [{THEROCK_DIR}]$ {shlex.join(cmd)}")

subprocess.run(
    cmd,
    cwd=THEROCK_DIR,
    check=True,
    shell=is_windows()
)
