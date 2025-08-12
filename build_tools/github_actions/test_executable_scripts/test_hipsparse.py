import logging
import os
import shlex
import subprocess
from pathlib import Path
from test_hipblaslt import is_windows

THEROCK_BIN_DIR = Path(os.getenv("THEROCK_BIN_DIR")).resolve()
OUTPUT_ARTIFACTS_DIR = os.getenv("OUTPUT_ARTIFACTS_DIR")
SCRIPT_DIR = Path(__file__).resolve().parent
THEROCK_DIR = SCRIPT_DIR.parent.parent.parent

logging.basicConfig(level=logging.INFO)

cmd = [f"{THEROCK_BIN_DIR}/hipsparse-test"]
logging.info(f"++ Exec [{THEROCK_DIR}]$ {shlex.join(cmd)}")
subprocess.run(
    cmd,
    cwd=THEROCK_DIR,
    check=True,
    env={"HIPSPARSE_CLIENTS_MATRICES_DIR": f"{OUTPUT_ARTIFACTS_DIR}/clients/matrices/"},
    shell=is_windows()
)
