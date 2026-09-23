import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Sequence, Any
from dataclasses import dataclass

from .query import Query

def parse_dump(dump: str, n_queries = None, n_sims = None) -> list[list[float]]:
    """dump is newline-separated list of run measurements, each line corresponds to one run, each column to one feature.
    Returns a list of feature Ecdfs
    """

    lines: list[str] = dump.splitlines()

    if n_sims is None:
        n_sims = len(lines)
    else:
        assert len(lines) == n_sims

    line_vals: list[list[float]] = [[float(x) for x in line.split()] for line in lines]

    # Set up empty list for every feature
    collated: list[list[float]] = [[] for _ in line_vals[0]]
    
    for vals in line_vals:
        if n_queries is None:
            n_queries = len(vals) 
        else:
            assert len(vals) == n_queries

        for i, val in enumerate(vals):
            collated[i].append(val)

    assert len(collated) == n_queries

    for vals in collated:
        assert len(vals) == n_sims

    return [sorted(coll) for coll in collated]