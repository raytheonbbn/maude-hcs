import sys
import json
from pathlib import Path

# parsable from bins:
#   "feature": "active_flow_count",
#   "vantage_point": "router_client_net_racetunnel_ens6",
#   "n_values": 331,
#   "k": 0.4079476334340383,
#   "ecdf_values": ...

# parsable after bins:
#   "bin_size": 10,
#   "window_size": 6,   ??
#   "start_time": null, ??

# constant:
#   "flow_timeout": 20, ??

# unknown (ask team):
#   "scenario": "pcaps",
#   "start_offset": 353,
#   "n_collections": 1,
#   "k_n_trials": 500,

SCENARIO = "scenario_1"
FLOW_TIMEOUT = 20

def write_baseline_file(baseline_str: str, params: dict, dir: str):
    raw_args = baseline_str[3:-1].split(", ")
    vantage, feat, k = raw_args[0], raw_args[1], raw_args[2]

    if "nil" in raw_args[3]:
        ecdf = []
    else:
        ecdf = list(map(lambda x: float(x), raw_args[3].split()))

    result = {
        "feature": feat,
        "vantage_point": vantage,
        "scenario": SCENARIO,
        "bin_size": params["binSize"],
        "flow_timeout": FLOW_TIMEOUT,
        # "start_offset": ???,
        "start_time": params["tStart"],
        "window_size": params["winSize"],
        # "n_collections": ???,
        "n_values": len(ecdf),
        "k": k,
        # "k_n_trials": ???,
        "ecdf_values": ecdf
    }

    stem = f"{feat}.json"
    result_path = Path(dir) / stem
    with open(result_path, "w") as f:
        json.dump(result, f, indent=4)

if __name__ == "__main__":
    baseline_file = sys.argv[1]
    output_dir = sys.argv[2]

    with open(baseline_file, "r") as f:
        # All whitespace runs are replaced by a single space
        raw_baseline = " ".join(f.read().split())

    baseline_start = raw_baseline.find("baseLine: (bl(")
    assert baseline_start >= 0
    raw_baseline = raw_baseline[baseline_start:]

    bl_start = raw_baseline.find("bl(")
    assert bl_start >= 0
    raw_baseline = raw_baseline[bl_start:]

    bl_end = raw_baseline.find(")), winSize: ")
    assert bl_end >= 0
    raw_baseline_terminator = raw_baseline[bl_end+4:-1]
    raw_baseline = raw_baseline[:bl_end+1]

    # raw_baseline should now have the form  "bl(...) :; bl(...) :; bl(...) :; ..."
    baseline_strs = raw_baseline.split(" :; ")

    param_strs = raw_baseline_terminator.split(", ")
    params = {item.split(": ")[0]: float(item.split(": ")[1]) for item in param_strs}

    for s in baseline_strs:
        write_baseline_file(s, params, output_dir)