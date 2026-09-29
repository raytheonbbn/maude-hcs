import sys
import json
import argparse
import math
from pathlib import Path
from datetime import datetime
from typing import Sequence, Any
from dataclasses import dataclass

from .query import Query

def parse_dump_rows(dump: str, n_queries=None, n_sims=None) -> list[list[float]]:
    """Keep measurements from the same simulation together; never sort columns."""
    lines = [line for line in dump.splitlines() if line.strip()]
    if not lines:
        raise ValueError("SMC dump contains no samples")
    if n_sims is not None and len(lines) != n_sims:
        raise ValueError(f"Expected {n_sims} sample rows, got {len(lines)}")
    rows = []
    for number, line in enumerate(lines, 1):
        try:
            row = [float(value) for value in line.split()]
        except ValueError as exc:
            raise ValueError(f"Invalid number in sample row {number}") from exc
        if n_queries is None:
            n_queries = len(row)
        if len(row) != n_queries or not all(math.isfinite(x) for x in row):
            raise ValueError(f"Invalid sample row {number}: expected {n_queries} finite values")
        rows.append(row)
    return rows


def parse_dump(dump: str, n_queries = None, n_sims = None) -> list[list[float]]:
    """dump is newline-separated list of run measurements, each line corresponds to one run, each column to one feature.
    Returns a list of feature Ecdfs
    """

    # Preserve the legacy marginal-ECDF API; joint analyses use parse_dump_rows.
    rows = parse_dump_rows(dump, n_queries=n_queries, n_sims=n_sims)
    return [sorted(column) for column in zip(*rows)]
