import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Sequence, Any
from dataclasses import dataclass

@dataclass
class Query:
    typ: str # Independent or Cumulative
    name: str
    start: int
    end: int
    extra: str | None = None

    def to_win_str(self):
        return f"t{self.start}_t{self.end}"

    def is_adv_stat(self):
        return self.extra is not None and self.name != "integrity"

def default_feature_dict():
    return {"cumulative": {}, "independent": {}}

def inty(x):
    return int(float(x))

# Maybe this should individually parse clients and stuff, but do that later.
def parse_quatex(quatex: str) -> list[Query]:
    result = []

    for line in quatex.splitlines():
        comment_start = line.find("//")
        if comment_start <= 0: 
            raise Exception("We expect quatex file to have no commented lines and each line to have a correctly formatted comment the end")

        tag = line[comment_start+2:]
        parts = tag.split()

        if len(parts) == 4:
            result.append(Query(
                parts[0], parts[1], inty(parts[2]), inty(parts[3]), None
            ))
        elif len(parts) == 5:
            result.append(Query(
                parts[0], parts[1], inty(parts[2]), inty(parts[3]), parts[4]
            ))
        else:
            raise Exception("tags should have 4 or 5 whitespace-separated parts")

    return result

def write_integrity_stat(val, q: Query, dct: dict):
    if "integrity" not in dct:
        dct["integrity"] = {}

    if q.extra is None:
        if "global_integrity" not in dct["integrity"]:
            dct["integrity"]["global_integrity"] = default_feature_dict()
        dct["integrity"]["global_integrity"][q.typ][q.to_win_str()] = val

    else:
        feature_name = f"{q.extra}_integrity"
        if feature_name not in dct["integrity"]:
            dct["integrity"][feature_name] = default_feature_dict()
        dct["integrity"][feature_name][q.typ][q.to_win_str()] = val
    
def write_adv_stat(val, q: Query, dct: dict):
    if "vantage_points" not in dct:
        dct["vantage_points"] = {}

    if q.extra not in dct["vantage_points"]:
        dct["vantage_points"][q.extra] = {}

    if q.name not in dct["vantage_points"][q.extra]:
        dct["vantage_points"][q.extra][q.name] = default_feature_dict()

    dct["vantage_points"][q.extra][q.name][q.typ][q.to_win_str()] = val

def write_perf_stat(val, q: Query, dct: dict):
    if q.name == "integrity":
        write_integrity_stat(val, q, dct)
        return

    # It's either latency, goodput, or availability
    if q.name not in dct:
        dct[q.name] = default_feature_dict()

    dct[q.name][q.typ][q.to_win_str()] = val

def extract_stats(line: str) -> dict[str, float]:
    toks = line.split()

    return {
        "mean": float(toks[2]),
        "stddev": float(toks[5]),
        "radius": float(toks[8]),
    }

def write_stats_to_json_file(
        stats: list,
        perf_output_file: str,
        adv_output_file: str,
        queries: list[Query],
        scenario: str,
        generated_at: str,
):
    perf_dict = {}
    adv_dict = {"metadata": {"scenario": scenario, "generated_at": generated_at}}

    for val, q in zip(stats, queries):
        if q.is_adv_stat():
            write_adv_stat(val, q, adv_dict)
        else:
            write_perf_stat(val, q, perf_dict)

    with open(perf_output_file, "w") as f:
        json.dump(perf_dict, f, indent=4)

    with open(adv_output_file, "w") as f:
        json.dump(adv_dict, f, indent=4)

# def load_stats_from_txt(s: str) -> list[dict[str, float]]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
                        prog='TnE Formatter',
                        description='Transform results from SMC queries into a proper JSON format')
    parser.add_argument('--smc-results-file')
    parser.add_argument('--json-smc-results-file')

    parser.add_argument('--quatex-file')

    parser.add_argument('--perf-output-file')
    parser.add_argument('--adv-output-file')
    parser.add_argument('--perf-stats-output-file')
    parser.add_argument('--adv-stats-output-file')

    parser.add_argument('--dump-file')
    parser.add_argument('--sample-output-dir')
    parser.add_argument('--scenario')
    args = parser.parse_args()

    assert args.quatex_file is not None

    with open(args.quatex_file, "r") as f:
        queries = parse_quatex(f.read())

    if args.scenario is not None:
        scenario = args.scenario
    else: 
        scenario = "unknown"

    generated_at = str(datetime.now().isoformat())

    if args.smc_results_file is not None:
        assert args.perf_output_file is not None
        assert args.adv_output_file is not None

        with open(args.smc_results_file, "r") as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip().startswith("μ")]

        stats = [extract_stats(line) for line in lines]
        means = [feat["mean"] for feat in stats]

        write_stats_to_json_file(means, args.perf_output_file, args.adv_output_file, queries, scenario, generated_at)

        if args.perf_stats_output_file is not None:
            assert args.adv_stats_output_file is not None
            write_stats_to_json_file(stats, args.perf_stats_output_file, args.adv_stats_output_file, queries, scenario, generated_at)

    if args.json_smc_results_file:
        assert args.perf_output_file is not None
        assert args.adv_output_file is not None

        stats = []

        with open(args.json_smc_results_file, "r") as f:
            s = f.read()
            # pre_json_idx = s.rfind("has converged")            
            # s = s[pre_json_idx:]
            # json_start_idx = s.find("{")
            # assert json_start_idx >= 0
            # json_str = s[json_start_idx:]
            # js = json.loads(json_str)["queries"]
            js = json.loads(s)["queries"]

            for query in js:
                stats.append({"mean": query["mean"], "stddev": query["std"], "radius": query["radius"]})

        means = [feat["mean"] for feat in stats]

        write_stats_to_json_file(means, args.perf_output_file, args.adv_output_file, queries, scenario, generated_at)

        if args.perf_stats_output_file is not None:
            assert args.adv_stats_output_file is not None
            write_stats_to_json_file(stats, args.perf_stats_output_file, args.adv_stats_output_file, queries, scenario, generated_at)

    def are_all_zeroes_exact(float_list):
        """Checks if all elements in the list are exactly 0.0"""
        return all(x == 0.0 for x in float_list)

    if args.dump_file is not None:
        with open(args.dump_file, "r") as f:
            raw_dumps = f.read().splitlines()
        dumps = [[float(val) for val in line.split()] for line in raw_dumps]
        ignored_samples = 0
        good_samples = 0
        for i, dump in enumerate(dumps):
            if are_all_zeroes_exact(dump):
                print(f"Sample {i} is all zeros, ignoring")
                ignored_samples += 1
                continue
            perf_sample_dict = {}
            adv_sample_dict = {"metadata": {"team": "Maude-HCS", "scenario": scenario, "generated_at": generated_at}}
            perf_sample_output_file = str(Path(args.sample_output_dir) / f"run{i}_perf.json")
            adv_sample_output_file = str(Path(args.sample_output_dir) / f"run{i}_adv.json")
            write_stats_to_json_file(dump, perf_sample_output_file, adv_sample_output_file, queries, scenario, generated_at)
            good_samples += 1
        print(f"wrote {good_samples} samples to files ({ignored_samples} ignored)")