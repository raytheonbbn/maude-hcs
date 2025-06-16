
from pathlib import Path
from typing import Any, Dict

import yaml


def load_yaml_to_dict(file_path: Path) -> Dict[Any, Any]:
    print(f'attempting to open {file_path}')
    if not file_path.is_file():
        raise FileNotFoundError(f"Error: The file '{file_path}' was not found.")

    with open(file_path, 'r') as stream:
        try:
            # safe_load is recommended over load for security
            return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            print(f"Error parsing YAML file: {exc}")
            raise