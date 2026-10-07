"""Functions for comparing test results to known answers or previous snapshots"""

import logging
import math
import json

from pathlib import Path
from typing import Any, Callable

import scipy

from .context import TestConfig, TestRunner, RunConfig

SMC_THRESHOLD = 10.0
KS_THRESHOLD = 0.6

logger = logging.getLogger(__name__)

def validate_params(obtained_params: dict, expected_params: dict) -> None:
    """Warn if parameters differ between obtained and expected results"""
    obtained_extra_top_keys, expected_extra_top_keys = get_key_diffs(obtained_params, expected_params)

    if obtained_extra_top_keys:
        logger.warning("Obtained run parameters include keys not present in expected run parameters! Extra keys: %s", obtained_extra_top_keys)

    if expected_extra_top_keys:
        logger.warning("Expected run parameters include keys not present in obtained run parameters! Extra keys: %s", expected_extra_top_keys)

    shared_top_keys = set(obtained_params.keys()).intersection(expected_params.keys()).difference(set(["results"]))

    for key in shared_top_keys:
        obt_val = obtained_params[key]
        exp_val = expected_params[key]

        if obt_val != exp_val:
            logger.warning("Obtained run parameters don't match expected parameters! Comparing the two runs might not be meaningful.")
            logger.warning("Obtained %s: %s", key, obt_val)
            logger.warning("Expected %s: %s", key, exp_val)

def remove_independents(d: dict[str, Any]) -> None:
    ind_keys = [k for k in d.keys() if k.startswith("independent")]
    for k in ind_keys:
        del d[k]

def validate_feats(obtained_feats: set[str], expected_feats: set[str], run_cfg: RunConfig) -> None:
    if any(map(lambda x: x.startswith("independent"), obtained_feats)):
        logger.warning("Found 'independent' queries in obtained results! They will be ignored/deleted")

    if any(map(lambda x: x.startswith("independent"), expected_feats)):
        logger.warning("Found 'independent' queries in expected results! They will be ignored/deleted")

    without_inds = lambda feats: set(filter(lambda x: not x.startswith("independent"), feats))
    obtained_feats = without_inds(obtained_feats)
    expected_feats = without_inds(expected_feats)

    obtained_extra_feats = obtained_feats.difference(expected_feats)
    expected_extra_feats = expected_feats.difference(obtained_feats)

    if run_cfg.partial_smc_comp:
        if obtained_extra_feats:
            logger.warning("Obtained run results contain features not present in expected run results! Extra features: %s", obtained_extra_feats)
        if expected_extra_feats:
            logger.warning("Expected run results contain features not present in obtained run results! Extra features: %s", expected_extra_feats)
    else:
        assert obtained_feats == expected_feats, \
            "expected and obtained results must measure the same features! To relax this restriction, pass --partial-smc-comp"

def make_check_fn(f: Callable[[str, str], None]) -> Callable[[Path, Path], None]:
    """Given a comparison function `f` between two strings, returns a comparison function between filenames
    that just invokes `f` on the contents of those files."""
    return lambda n0, n1: f(n0.read_text(), n1.read_text())

def euclid_feat_distance(feat0: dict, feat1: dict) -> float:
    """Provides a metric for the distance between two feature distributions
    feat0 and feat1 should have keys "mean", "std", and "radius"
    """
    return math.sqrt(
        (feat0["mean"] - feat1["mean"]) ** 2.0 +
        (feat0["std"] - feat1["std"]) ** 2.0 +
        (feat0["radius"] - feat1["radius"]) ** 2.0
    )

def get_comp(cfg: TestConfig, run_cfg: RunConfig) -> Callable[[str, str], None]:
    """Get appropriate comparison function for this config"""

    match cfg.runner:
        case TestRunner.MAUDE: return str_comp
        case TestRunner.SMC: return mk_smc_comp(run_cfg)
        case _: raise Exception("invalid TestRunner")

def naive_smc_comp(obtained: str, expected: str) -> None:
    """Compare the results of an SMC run to a known "good" reference run.
    Both strings should contain json of the form {queries: [{"mean": X, "std": Y, "radius": Z}, ...], ...}
    where X Y and Z are floats.
    
    The comparison is made by averaging the "distance" between each pair of queries, interpreting X Y and Z as 3d coordinates.
    This is a kinda silly method, but I'm not yet sure of a better metric on distributions without ECDFs."""

    obtained_json = json.loads(obtained)
    obtained_queries = obtained_json["queries"]

    expected_json = json.loads(expected)
    expected_queries = expected_json["queries"]

    if not isinstance(obtained_queries, list):
        raise Exception("obtained queries should be a list of objects")
    
    if not isinstance(expected_queries, list):
        raise Exception("obtained queries should be a list of objects")

    n_queries = len(obtained_queries)
    assert n_queries == len(expected_queries)

    total_distance = sum([euclid_feat_distance(feat0, feat1) for feat0, feat1 in zip(obtained_queries, expected_queries)])
    avg_distance = total_distance / n_queries

    assert avg_distance <= SMC_THRESHOLD

def get_key_diffs(d0: dict, d1: dict) -> tuple[set, set]:
    """Return a tuple containing the keys in d0 that aren't in d1,
    and the keys in d1 that aren't in d0. In other words, (d0_extra, d1_extra)"""
    return (
        set(d0.keys()).difference(d1.keys()),
        set(d1.keys()).difference(d0.keys())
    )

def mk_smc_comp(run_cfg: RunConfig) -> Callable[[str, str], None]:
    return lambda obt, exp: smc_comp(obt, exp, run_cfg)

def smc_comp(obtained: str, expected: str, run_cfg: RunConfig) -> None:
    obtained_json: dict = json.loads(obtained)
    expected_json: dict = json.loads(expected)

    assert "results" in obtained_json
    assert "results" in expected_json

    obtained_results: dict = obtained_json["results"]
    expected_results: dict = expected_json["results"]
    remove_independents(obtained_results)
    remove_independents(expected_results)

    if run_cfg.partial_smc_comp:
        keys_to_compare = set(obtained_results.keys()).intersection(expected_results.keys())
    else:
        # This should already have been checked earlier during validation stage, so this is basically a sanity check
        assert (obtained_results.keys() == expected_results.keys())
        keys_to_compare = set(obtained_results.keys())

    for key in keys_to_compare:
        obtained_samples = obtained_results[key]["samples"]
        expected_samples = expected_results[key]["samples"]

        assert scipy.stats.ks_2samp(
            obtained_samples,
            expected_samples
        ).statistic <= KS_THRESHOLD, \
            f"ks distance beyond threshold for feature {key}, with ECDFs:\n{obtained_samples}\nand\n{expected_samples}"

def str_comp(obtained: str, expected: str) -> None:
    assert obtained == expected, f"obtained = '{obtained}', expected = '{expected}'"