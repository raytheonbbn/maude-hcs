import sys
import os
import json
from pathlib import Path
from dataclasses import dataclass, field

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

# parse large number of baseline runs, combine them into one dict,
# and also combine them into one actor.

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
        return f"bl({self.feat}, {self.vantage}, {self.k}, {' '.join(map(str, self.ecdf))}"
    
def parse_bl(bl_str: str) -> Bl:
    raw_args = bl_str.strip()[3:-1].split(", ") # strip initial "bl(" and terminal ")"
    vantage, feat, k = raw_args[0], raw_args[1], float(raw_args[2])

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
        self.vantages = list(map(lambda bl: bl.vantage, self.bls))
        self.feats = list(map(lambda x: x.feat, self.bls))

    def no_dupe_bls(self) -> bool:
        pairs = list(map(lambda x: (x.feat, x.vantage), self.bls))
        return len(pairs) == len(set(pairs))

    def to_actor_str(self):
        return str(Lines(
            f"result Actor:",
            Lines(
                f"< baseLineAddr : BaseLineMonitor |",
                Lines(
                    f"viewPts: ({' :; '.join(self.vantages)}),",
                    f"features: ({' :; '.join(self.feats)}),",
                    f"baseLine: ({' :; '.join(map(str, self.bls))}),",
                    ', '.join([f"{p[0]}: {p[1]}" for p in self.params.items()]),).indent(),
                '>',).indent
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
        assert len(set(map(lambda x: x.params, baselines))) == 1

        bls = []
        for baseline in baselines:
            bls.extend(baseline.bls)

        return Baseline(bls, baselines[0].params)


def parse_baseline(s: str) -> Baseline:
    # All whitespace runs are replaced by a single space
    s = " ".join(s.split())

    baseline_start = s.find("baseLine: (bl(")
    assert baseline_start >= 0
    s = s[baseline_start:]

    bl_start = s.find("bl(")
    assert bl_start >= 0
    s = s[bl_start:]

    bl_end = s.find(")), winSize: ")
    assert bl_end >= 0
    terminator = s[bl_end+4:-1]
    s = s[:bl_end+1]

    # raw_baseline should now have the form  "bl(...) :; bl(...) :; bl(...) :; ..."
    bl_strs = s.split(" :; ")

    attr_end = terminator.find('>')
    assert attr_end >= 0
    terminator = terminator[:attr_end]

    param_strs = terminator.split(", ")
    params = {item.split(": ")[0]: float(item.split(": ")[1]) for item in param_strs}

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
    baseline_path = Path(sys.argv[1]).resolve()
    output_dir = Path(sys.argv[2]).resolve()

    if len(sys.argv) >= 4:
        scenario = sys.argv[3]
    else:
        scenario = baseline_path.stem

    if baseline_path.is_dir():
        baselines = []
        for path in os.listdir(baseline_path):
            assert Path(path).is_file()
            with open(path, "r") as f:
                baselines.append(parse_baseline(f.read()))
        baseline = Baseline.join(baselines)

    elif baseline_path.is_file():
        with open(baseline_path, "r") as f:
            baseline = parse_baseline(f.read())
    else:
        raise Exception("first argument must be a path to either directory or ordinary file")

    write_jsons(baseline, output_dir, scenario)
