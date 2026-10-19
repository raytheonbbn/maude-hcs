import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Sequence, Any

# For all of these, we need separate values for separate windows!

# Latency percentiles (we're doing this instead of full latency lists)
# These are only cumulative
perf_latency_keys = [
    "latency0",
    "latency25",
    "latency50",
    "latency75",
    "latency100",
]

# Need cumulative/independent versions for each of these
perf_other_keys = [
    "goodput",
    "integrity",    # Need individual integrity measures for each alice!
    "availability", # Mean Time Between Failures (MTBF)
]

# Also need cumulative/independent versions for these
adv_keys = [
    "dns_query_rate",
    "dns_query_size_mean",
    "dns_response_size_mean",
    "tcp_upload_rate",
    "tcp_download_rate",
    "tcp_upload_download_ratio",
    "tcp_outgoing_packet_rate",
    "tcp_incoming_packet_rate",
    "tcp_packet_upload_download_ratio",
    "tcp_packet_size_std_dev",
    "packet_size_mean",
    "packet_interarrival_mean",
    "direction_change_count",
    "active_flow_count",
    "tcp_new_conn_count",
]

len_perf_latencies = len(perf_latency_keys)
len_perf_other = len(perf_other_keys)
len_all_perfs = len_perf_latencies + len_perf_other
len_adv = len(adv_keys)

def mk_windows(lst: Sequence, sizes: list[int]) -> list[list]:
    assert len(lst) == sum(sizes)
    idx = 0
    result = []
    for size in sizes:
        result.append(lst[idx:idx+size])
        idx += size
    return result

def extract_stats(line: str) -> dict[str, float]:
    toks = line.split()

    return {
        "mean": float(toks[2]),
        "stddev": float(toks[5]),
        "radius": float(toks[8]),
    }

def list_to_perf_dict(lst: Sequence[Any]) -> dict:
    assert len(lst) == len_all_perfs
    result = {"latency": {}}
    perf_latency_stats, perf_other_stats = tuple(
        mk_windows(lst, [len_perf_latencies, len_perf_other])
    )

    for key in perf_latency_keys:
        result["latency"][key] = {}

    for stat, key in zip(perf_latency_stats, perf_latency_keys):
        result["latency"][key]["cumulative"] = stat
        result["latency"][key]["independent"] = stat

    for key in perf_other_keys:
        result[key] = {}

    for stat, key in zip(perf_other_stats, perf_other_keys):
        result[key]["cumulative"] = stat
        result[key]["independent"] = stat

    return result

def list_to_adv_dict(lst: Sequence[Any], scenario: str, generated_at: str) -> dict:
    assert len(lst) == 2 * len_adv
    result = {}
    result["metadata"] = {"scenario": scenario, "generated_at": generated_at}
    adv_cum_stats, adv_ind_stats = tuple(
        mk_windows(lst, [len_adv, len_adv])
    )

    for key in adv_keys:
        result[key] = {}

    for stat, key in zip(adv_cum_stats, adv_keys):
        result[key]["cumulative"] = stat

    for stat, key in zip(adv_ind_stats, adv_keys):
        result[key]["independent"] = stat

    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
                        prog='TnE Formatter',
                        description='Transform results from SMC queries into a proper JSON format')
    parser.add_argument('-i', '--input-file')
    parser.add_argument('-p', '--perf-output-file')
    parser.add_argument('-a', '--adv-output-file')
    parser.add_argument('--perf-stats-output-file')
    parser.add_argument('--adv-stats-output-file')
    parser.add_argument('-d', '--dump-file')
    parser.add_argument('-r', '--run-output-dir')
    parser.add_argument('-s', '--scenario')
    args = parser.parse_args()

    if args.input_file is not None:
        assert args.perf_output_file is not None
        assert args.adv_output_file is not None

        if args.scenario is not None:
            scenario = args.scenario
        else: 
            scenario = args.input_file.removesuffix(".txt")
        generated_at = str(datetime.now().isoformat())

        with open(args.input_file, "r") as f:
            lines = [ln.strip() for ln in f.readlines() if ln.strip().startswith("μ")]

        stats = [extract_stats(line) for line in lines]
        means = [feat["mean"] for feat in stats]

        # len_adv is repeated because there are cumulative and independent versions
        assert len_all_perfs + (2*len_adv) == len(means)

        perf_dict = list_to_perf_dict(means[:len_all_perfs])
        adv_dict = list_to_adv_dict(means[len_all_perfs:], scenario, generated_at)

        with open(args.perf_output_file, "w") as f:
            json.dump(perf_dict, f, indent=4)

        with open(args.adv_output_file, "w") as f:
            json.dump(adv_dict, f, indent=4)

        if args.perf_stats_output_file is not None:
            assert args.adv_stats_output_file is not None
            perf_stats_dict = list_to_perf_dict(stats[:len_all_perfs])
            adv_stats_dict = list_to_adv_dict(stats[len_all_perfs:], scenario, generated_at)

            with open(args.perf_stats_output_file, "w") as f:
                json.dump(perf_stats_dict, f, indent=4)

            with open(args.adv_stats_output_file, "w") as f:
                json.dump(adv_stats_dict, f, indent=4)

    if args.dump_file is not None:
        assert args.run_output_dir is not None

        if args.scenario is not None:
            scenario = args.scenario
        elif args.input_file is not None: 
            scenario = args.input_file.removesuffix(".txt")
        else:
            scenario = "unknown"
        generated_at = str(datetime.now().isoformat())

        with open(args.dump_file, "r") as f:
            runs = [[float(samp) for samp in line.split()] for line in f.readlines()]

        for i, run in enumerate(runs):
            run_perf_dict = list_to_perf_dict(run[:len_perf_latencies + len_perf_other])
            run_adv_dict = list_to_adv_dict(run[len_perf_latencies + len_perf_other:], scenario, generated_at)

            run_perf_output_file = Path(args.run_output_dir) / f"run{i}_perf.json"
            run_adv_output_file = Path(args.run_output_dir) / f"run{i}_adv.json"

            with open(run_perf_output_file, "w") as f:
                json.dump(run_perf_dict, f, indent=4)

            with open(run_adv_output_file, "w") as f:
                json.dump(run_adv_dict, f, indent=4)