import os
from pathlib import Path


def data_dir():
    root = Path(os.environ.get("LOGLENS_HOME", Path.home() / ".loglens"))
    root.mkdir(parents=True, exist_ok=True)
    return root
