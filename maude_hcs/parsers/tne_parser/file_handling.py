# © 2026 The Johns Hopkins University Applied Physics Laboratory LLC

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import List

import yaml
from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    TemplateError,
)

TEMPLATE_DIR = "/src/python/templates"

env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=False,
    trim_blocks=True,
    lstrip_blocks=True,
)

# logging.basicConfig(
#     level=logging.WARNING,
#     format="%(asctime)s %(levelname)s %(message)s",
#     stream=sys.stdout,
# )


def set_file_644(dst):
    os.chmod(dst, 0o644)


def get_key_from_dict(look: str, info: dict, flip=False) -> str | None:
    """
    Returns the key in the dictionary
    if flip is false looks for the "look" var in the dict key,
    if flip is true looks for the dict key in the "look" var
    """
    for name, ip in info.items():
        if flip:
            if name in look:
                return name
        else:
            if look in name:
                return name


def make_directories(paths):
    if isinstance(paths, str):  # type: ignore
        normalized: List[str] = [paths]
    elif isinstance(paths, Path):
        normalized: List[Path] = [str(paths)]
    else:
        try:
            normalized = [str(p) for p in paths]  # force conversion to str
        except TypeError as exc:
            raise TypeError(
                (
                    "If 'paths' is not a string, "
                    "it must be an iterable of strings."
                )
            ) from exc

    # created: List[str] = []
    for p in normalized:
        if not isinstance(p, str):
            raise TypeError(f"All elements must be strings, got {type(p)!r}")

        # ``exist_ok=True`` means “do nothing if the folder already exists”
        os.makedirs(p, exist_ok=True)


def require_file(path):
    """
    Ensure that the given file exists.
    Raises FileNotFoundError if the file does not exist.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"Required file does not exist: {file_path}")
    return file_path


def read_yaml(file_path):
    file_path = require_file(file_path)
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in file {file_path}: {e}") from e
    return data


def read_json(file_path):
    file_path = require_file(file_path)  # Check file exists
    with open(file_path, "r") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in file {file_path}: {e}") from e
    return data


def write_json(data, path):
    """
    Write `data` to a JSON file at `path`.
    Handles errors and ensures UTF-8 encoding.
    """
    file_path = Path(path)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except TypeError as e:
        raise ValueError(f"Data is not JSON-serializable: {e}") from e
    except OSError as e:
        raise OSError(f"Failed to write to file {file_path}: {e}") from e
    return file_path


def write_file(path: Path, content: str) -> None:
    """Create parent directories as needed and write *content* to *path*."""
    if path.exists():
        with open(path, "w") as f:
            f.write(content)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def append_file(path: Path, content: str) -> None:
    """Create parent directories as needed and write *content* to *path*.
    Will append if *path* exists"""
    if path.exists():
        with open(path, "a") as f:
            f.write(content)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def get_deployment_info(args):
    """
    For ingesting arg parse, returns network map, test config and env name
    """
    test_config_file = args.test_config
    test_config = read_yaml(test_config_file)
    env_name = test_config.get("env", "")

    network_map_file = f"/src/artifacts/{env_name}/network_map.json"
    network_map = read_json(network_map_file)
    return network_map, test_config, env_name


def render_template(template_path: Path, ctx: dict) -> str:
    """
    Render a Jinja2 template located at *template_path* using the context dict *ctx*.
    The template is loaded with ``StrictUndefined`` so undefined variables raise
    a clear error instead of silently rendering an empty string.
    """  # noqa: E501
    env = Environment(
        loader=FileSystemLoader(searchpath=template_path.parent),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        lstrip_blocks=True,
        trim_blocks=True,
    )
    try:
        template = env.get_template(template_path.name)
        return template.render(**ctx)
    except TemplateError as exc:
        sys.exit(f"Template rendering failed: {exc}")


def parse_config_from_name(node):
    if "alice" in node:
        name = "alice"
    else:
        name = "bob"
    node_config = node.split(f"{name}_")[1]
    return re.sub(r"_\d+$", "", node_config)


def get_node_config(client):
    config = parse_config_from_name(client)
    return config
