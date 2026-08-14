import sys
import os
import json
from pathlib import Path
from dataclasses import dataclass, field
import argparse

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

SCENARIO = "unknown"

def rm_whitespace(s: str) -> str:
    return "".join(s.split())

class Lines:
  def __init__(self, *args, indent=0):
    lines = []
    for arg in args:
      if isinstance(arg, Lines):
        lines += arg.lines
      else:
        lines += [str(arg)]
    self.lines = [(" " * (indent*4)) + line for line in lines]

  def join(self, other):
    return Lines(*(self.lines + other.lines))

  def indent(self, indent=1):
    return Lines(*self.lines, indent=indent)

  def __str__(self):
      return "\n".join(self.lines)

@dataclass(frozen=True)
class Bl:
    feat: str
    vantage: str
    k: float
    ecdf: list[float]

    def __str__(self):
        return f"bl({self.vantage}, {self.feat}, {self.k}, {' '.join(map(str, self.ecdf))})"

# bl_str should look like "bl(...)"
def parse_bl(bl_str: str) -> Bl:
    first_paren_idx, last_paren_idx = bl_str.find('('), bl_str.rfind(')')
    assert first_paren_idx >= 0, last_paren_idx >= 0

    raw_args = bl_str[first_paren_idx+1:last_paren_idx].strip().split(",") # strip initial "bl(" and terminal ")"
    vantage, feat, k = rm_whitespace(raw_args[0]), rm_whitespace(raw_args[1]), float(raw_args[2])

    if "nil" in raw_args[3]:
        ecdf = []
    else:
        ecdf = list(map(lambda x: float(x), raw_args[3].split()))

    return Bl(feat=feat, vantage=vantage, k=k, ecdf=ecdf)

@dataclass
class Baseline:
    bls: list[Bl]
    params: dict[str, float]
    vantages: list[str] = field(init=False)
    feats: list[str] = field(init=False)

    def __post_init__(self):
        assert(self.no_dupe_bls())
        self.vantages = list(set(map(lambda bl: bl.vantage, self.bls)))
        self.feats = list(set(map(lambda x: x.feat, self.bls)))

    def no_dupe_bls(self) -> bool:
        pairs = list(map(lambda x: (x.feat, x.vantage), self.bls))
        return len(pairs) == len(set(pairs))

    def to_maude_str(self):
        return str(Lines(
            f"result Actor:",
            Lines(
                f"< baseLineAddr : BaseLineMonitor |",
                Lines(
                    f"viewPts: ({' :; '.join(self.vantages)}),",
                    f"features: ({' :; '.join(self.feats)}),",
                    f"baseLine: ({' :; '.join(map(str, self.bls))}),",
                    ', '.join([f"{p[0]}: {p[1]}" for p in self.params.items()]),).indent(),
                '>',).indent()
        ))

    def to_tne_dict(self, scenario):
        result = {}

        for bl in self.bls:
            result.setdefault(bl.vantage, {})[bl.feat] = {
                "scenario": scenario,
                "feature": bl.feat,
                "vantage_point": bl.vantage,
                "scenario": SCENARIO,
                "bin_size": self.params["binSize"],
                "start_time": self.params["tStart"],
                "window_size": self.params["winSize"],
                "n_values": len(bl.ecdf),
                "k": bl.k,
                "ecdf_values": bl.ecdf
            }

        return result

    @staticmethod
    def join(baselines: list["Baseline"]) -> "Baseline":
        assert len(baselines) >= 1

        # all baselines to be joined must have the same params
        assert len(set(map(lambda x: tuple(x.params.items()), baselines))) == 1

        bls = []
        for baseline in baselines:
            bls.extend(baseline.bls)

        return Baseline(bls, baselines[0].params)

def parse_baseline(s: str) -> Baseline:
    # All whitespace runs are replaced by a single space
    s = " ".join(s.split())

    actor_start = s.find("result Actor: ")
    assert actor_start >= 0
    s = s[actor_start:]

    baseline_start = s.find("baseLine")
    assert baseline_start >= 0
    s = s[baseline_start:]

    bl_start = s.find("bl")
    assert bl_start >= 0
    s = s[bl_start:]

    winsize_idx = s.rfind("winSize")
    assert winsize_idx >= 0
    terminator = s[winsize_idx:]
    s = s[:winsize_idx]

    last_paren_idx = s.rfind(")")
    assert last_paren_idx >= 0
    # usually there's another ) before this, but if this is the only bl there will only be one paren
    if s[:last_paren_idx].strip()[-1] == ')':
        s = s[:last_paren_idx]
    else:
        s = s[:last_paren_idx+1]

    # raw_baseline should now have the form  "bl(...) :; bl(...) :; bl(...) :; ..."
    bl_strs = s.split(" :; ")

    # Omit final gt sign
    attr_end = terminator.find('>')
    assert attr_end >= 0
    terminator = terminator[:attr_end]

    param_strs = rm_whitespace(terminator).split(",")
    params = {item.split(":")[0]: float(item.split(":")[1]) for item in param_strs}

    return Baseline(list(map(parse_bl, bl_strs)), params)

def write_jsons(baseline: Baseline, output_dir: Path, scenario: str):
    baseline_dct = baseline.to_tne_dict(scenario)

    if not output_dir.is_dir():
        os.mkdir(output_dir)

    for vantage, feats in baseline_dct.items():
        vantage_dir_path = output_dir / vantage
        if not vantage_dir_path.is_dir():
            os.mkdir(vantage_dir_path)

        for feat, bl_dict in feats.items():
            filename = f"{feat}.json"
            result_path = vantage_dir_path / filename
            with open(result_path, "w") as f:
                json.dump(bl_dict, f, indent=4)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="parse_baseline")
    parser.add_argument("baseline_path",
        help="path to the baseline file to parse (should contain output from a maude execution). "
        "If this path points to a dir, all files within are parsed as baseline files and combined.")
    parser.add_argument("output_dir", 
        help="path to a directory where the json files representing the baseline will be created. "
        "A directory is created at this location if it does not already exist.")
    parser.add_argument("-m", "--maude-output-file",
        help="Path where a maude representation of the combined baseline actor will be written.")
    parser.add_argument("-s", "--scenario", help="scenario name to be written to json outputs")
    args = parser.parse_args()

    baseline_path = Path(args.baseline_path).resolve()
    output_dir = Path(args.output_dir).resolve()
    
    if args.scenario is not None:
        scenario = args.scenario
    else:
        scenario = baseline_path.stem

    if baseline_path.is_dir():
        baselines = []
        for filename in os.listdir(baseline_path):
            if filename.startswith("."): continue   # Skip hidden files like .DS_Store

            path = baseline_path / filename
            assert Path(path).is_file(), f"{path} is not a file"
            with open(path, "r") as f:
                baselines.append(parse_baseline(f.read()))
        baseline = Baseline.join(baselines)

    elif baseline_path.is_file():
        with open(baseline_path, "r") as f:
            baseline = parse_baseline(f.read())
    else:
        raise Exception("first argument must be a path to either directory or ordinary file")

    write_jsons(baseline, output_dir, scenario)

    if args.maude_output_file is not None:
        with open(args.maude_output_file, "w") as f:
            f.write(baseline.to_maude_str())
