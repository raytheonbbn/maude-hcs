import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Sequence, Any
from dataclasses import dataclass

from .query import Query

def parse_dump(dump: str) -> list[list[float]]:
    """dump is newline-separated list of run measurements, each line corresponds to one run, each column to one feature.
    Returns a list of feature Ecdfs
    """

    lines: list[str] = dump.splitlines()
    line_vals: list[list[str]] = [line.split() for line in lines]

    # Set up empty list for every feature
    collated: list[list[float]] = [[]] * len(line_vals[0])

    for vals in line_vals:

        for i, val in enumerate(vals):
            collated[i].append(float(val))

    return [sorted(coll) for coll in collated]