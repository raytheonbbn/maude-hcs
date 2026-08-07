import sys
import json
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

if __name__ == "__main__":
    input_file = sys.argv[1]
    perf_output_file = sys.argv[2]
    adv_output_file = sys.argv[3]
    scenario = input_file.removesuffix(".txt")
    generated_at = str(datetime.now().isoformat())
    perf_result = {}
    adv_result = {"metadata": {"scenario": scenario, "generated_at": generated_at}}

    with open(input_file, "r") as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip().startswith("μ")]
        for line in lines:
            print(line)

        len_perf_latencies = len(perf_latency_keys)
        len_perf_other = len(perf_other_keys)
        len_adv = len(adv_keys)

        # len_adv is repeated because there are cumulative and independent versions
        assert len_perf_latencies + len_perf_other + (2*len_adv) == len(lines)

        perf_latency_stats, perf_other_stats, adv_cum_stats, adv_ind_stats = tuple(
            mk_windows(lines, [len_perf_latencies, len_perf_other, len_adv, len_adv])
        )
        perf_result["latency"] = {}
        for line, key in zip(perf_latency_stats, perf_latency_keys):
            stats = mean_stddev_rad(line)
            perf_result["latency"][key] = stats[0]

        for line, key in zip(perf_other_stats, perf_other_keys):
            stats = mean_stddev_rad(line)
            perf_result[key] = stats[0]

        for line, key in zip(adv_cum_stats, adv_keys):
            stats = mean_stddev_rad(line)
            adv_result[key] = {"cumulative": stats[0]}

        for line, key in zip(adv_ind_stats, adv_keys):
            stats = mean_stddev_rad(line)
            adv_result[key] = {"independent": stats[0]}

        with open(perf_output_file, "w") as g:
            json.dump(perf_result, g, indent=4)

        with open(adv_output_file, "w") as h:
            json.dump(adv_result, h, indent=4)