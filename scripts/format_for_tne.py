import sys
import json
from pathlib import Path
from datetime import datetime

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
len_adv = len(adv_keys)

def mk_windows(lst: list, sizes: list[int]) -> list[list]:
    assert len(lst) == sum(sizes)
    idx = 0
    result = []
    for size in sizes:
        result.append(lst[idx:idx+size])
        idx += size
    return result

def mean_stddev_rad(line: str) -> tuple[float, float, float]:
    toks = line.split()
    return (float(toks[2]), float(toks[5]), float(toks[8]))

def list_to_perf_dict(lst: list[float]) -> dict:
    assert len(lst) == len_perf_latencies + len_perf_other
    result = {"latency": {}}
    perf_latency_stats, perf_other_stats = tuple(
        mk_windows(lst, [len_perf_latencies, len_perf_other])
    )

    for stat, key in zip(perf_latency_stats, perf_latency_keys):
        result["latency"][key] = stat

    for stat, key in zip(perf_other_stats, perf_other_keys):
        result[key] = stat

    return result

def list_to_adv_dict(lst: list[float], scenario: str, generated_at: str) -> dict:
    assert len(lst) == 2 * len_adv
    result = {}
    result["metadata"] = {"scenario": scenario, "generated_at": generated_at}
    adv_cum_stats, adv_ind_stats = tuple(
        mk_windows(lst, [len_adv, len_adv])
    )

    for stat, key in zip(adv_cum_stats, adv_keys):
        result[key] = {"cumulative": stat}

    for stat, key in zip(adv_ind_stats, adv_keys):
        result[key] = {"independent": stat}

    return result

if __name__ == "__main__":
    input_file = sys.argv[1]
    perf_output_file = sys.argv[2]
    adv_output_file = sys.argv[3]
    dump_file = sys.argv[4]
    run_output_dir = sys.argv[5]

    scenario = input_file.removesuffix(".txt")
    generated_at = str(datetime.now().isoformat())

    with open(input_file, "r") as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip().startswith("μ")]

    means = [mean_stddev_rad(line)[0] for line in lines]

    # len_adv is repeated because there are cumulative and independent versions
    assert len_perf_latencies + len_perf_other + (2*len_adv) == len(means)


    perf_dict = list_to_perf_dict(means[:len_perf_latencies + len_perf_other])
    adv_dict = list_to_adv_dict(means[len_perf_latencies + len_perf_other:], scenario, generated_at)

    with open(perf_output_file, "w") as f:
        json.dump(perf_dict, f, indent=4)

    with open(adv_output_file, "w") as f:
        json.dump(adv_dict, f, indent=4)

    with open(dump_file, "r") as f:
        runs = [[float(samp) for samp in line.split()] for line in f.readlines()]

    for i, run in enumerate(runs):
        run_perf_dict = list_to_perf_dict(run[:len_perf_latencies + len_perf_other])
        run_adv_dict = list_to_adv_dict(run[len_perf_latencies + len_perf_other:], scenario, generated_at)

        run_perf_output_file = Path(run_output_dir) / f"run{i}_perf.json"
        run_adv_output_file = Path(run_output_dir) / f"run{i}_adv.json"

        with open(run_perf_output_file, "w") as f:
            json.dump(run_perf_dict, f, indent=4)

        with open(run_adv_output_file, "w") as f:
            json.dump(run_adv_dict, f, indent=4)