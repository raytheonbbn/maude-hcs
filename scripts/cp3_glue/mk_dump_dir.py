import sys
import os
from pathlib import Path
from datetime import datetime

if __name__ == "__main__":
    path = Path(sys.argv[1]).resolve()
    name_prefix = path.name
    name = name_prefix + datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    result_dir_path = path.parent / name
    assert not result_dir_path.is_dir()

    os.mkdir(result_dir_path)
    print(result_dir_path)
    exit(0)