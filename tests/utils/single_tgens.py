"""Shared TGEN composition experiments using the existing generator and SMC runner."""
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any
from enum import Enum

import json
import logging
import math
import uuid

import numpy as np
import yaml
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from scipy.stats import ks_2samp

from maude_hcs.result import SimParams
from .build import build
from .context import BuildConfig, Context, GenArgs, TestConfig, TestRunner, RunConfig
from ..regression.test_regression import run

logger = logging.getLogger(__name__)

MARKOV_V1_DIRS = (
    ("skyhook_action_models", "skyhook"),
    ("mastodon_action_models", "mastodon"),

    ("tgen_user_models/dns", "dns-tgen"),
    ("tgen_user_models/mastodon", "mastodon-tgen"),
    ("tgen_user_models/mastodon_monitor", "mastodon-monitor-tgen"),
    ("tgen_user_models/minio_monitor", "minio-monitor-tgen")
)

MARKOV_V2_DIRS = (
    ("irc_user_models", "irc"),

    ("tgen_user_models/ftp", "ftp-tgen"),
    ("tgen_user_models/gorilla", "gorilla-tgen"),
    ("tgen_user_models/irc", "irc-tgen"),
    ("tgen_user_models/minio", "minio-tgen"),
    ("tgen_user_models/tls", "tls-tgen")
)

class CaseStatus(Enum):
    PENDING = "pending"
    INVALID = "invalid"
    COMPLETE = "complete"

@dataclass(kw_only=True)
class Case:
    exp: SingleTgenExperiment
    feat: str
    vantage: str
    window_size: int
    
    traceback: str | None = None
    samples: list[float] | None = None

    def to_query(self) -> str:
        if self.feat.startswith("tcp"): log = "getTsPL"
        elif self.feat.startswith("dns"): log = "getTsML"
        else: raise RuntimeError("unrecognized feat")

        expr = f'compObsFeatureX({self.vantage}, {self.feat}, {log}(getAdversary(C)), 0.0, {self.window_size}.0)'
        tag =  f"// cumulative {self.feat} 0 {self.window_size} {self.vantage}"
        return f"eval E[s.rval(\"{expr}\")]; {tag}"

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        del result["exp"]
        return result
    
    def to_sorted_dict(self) -> dict[str, Any]:
        result = asdict(self)
        del result["exp"]
        result["samples"].sort()
        return result

    def case_id(self) -> str:
        return f"{self.exp.name}+{self.feat}+{self.vantage}+{self.window_size}"

@dataclass(frozen=True, kw_only=True)
class SingleTgenExperiment:
    ctx_path: Path
    name: str
    yaml: str
    feats: list[str]
    vantages: list[str]
    window_sizes: list[int]

    seed: int = 0

    n_samples: int = 256
    method: str = 'p-value'
    alpha: float = .05
    delta: float = .05

    _dir_name: str | None = None

    def dir_name(self) -> str:
        if self._dir_name is None:
            object.__setattr__(self, '_dir_name', f"{self.name}+{uuid.uuid4().hex}")
        assert isinstance(self._dir_name, str)
        return self._dir_name

    def cases(self) -> list[Case]:
        return [
            Case(exp=self, feat=feat, vantage=vantage, window_size=window_size)
            for feat in self.feats for vantage in self.vantages for window_size in self.window_sizes]
    
    def to_yaml_header(self) -> dict[str, int]:
        return {
            "conversation_duration": max(self.window_sizes),
            "max_start_delay": 900,
            "one_way_availability": 30,
            "analysis_window_size": max(self.window_sizes) # doesn't actually matter here
        }

    def get_yaml(self) -> dict:
        return yaml.safe_load((self.ctx_path / "yaml_chunks" / self.yaml).read_text())
    
    def run(self, run_cfg: RunConfig, smoke: bool = False) -> list[Case]:
        cfg = prepare_single_tgen_arm(self, run_cfg)
        if run_cfg.build_only: return []

        cases = self.cases()

        exp_dir = run_cfg.temp_dir / self.dir_name()

        run(cfg, exp_dir, run_cfg)

        for log in (exp_dir / 'logs').glob('*stderr*'):
            if any(marker in log.read_text().lower() for marker in
                ('unpatchable errors', 'unable to locate file:', 'no parse for term')):
                raise ValueError(f'Maude load/query error; see {log}')

        rows = read_rows(exp_dir)
        len_first_row = len(rows[0])
        assert all([len(row) == len_first_row for row in rows]), f"expected all rows to have same length, at least one differs"
        assert len(rows) == self.n_samples, f"expected {self.n_samples} rows in output, found {len(rows)} rows"
        assert len_first_row == len(cases), f"expected {len(cases)} samples in each row of output, found {len_first_row} samples"

        # By transposing, we now have all samples (across all sims) for a single given query on the same row
        trans_rows = np.transpose(rows).tolist()

        # The list of cases corresponds with the list of quatex queries, and therefore corresponds with the output samples
        for query_samples, case in zip(trans_rows, cases):
            case.samples = sorted(query_samples)
        
        write_json(exp_dir / "cases.json", list(map(lambda x: x.to_dict(), cases)))
        return cases

def run_suite(exps: list[SingleTgenExperiment], run_cfg: RunConfig, smoke: bool = False) -> list[Case]:
    cases = []

    for exp in exps:
        cases.extend(exp.run(run_cfg, smoke))
    
    return cases

def load_suite(ctx_path: Path) -> list[SingleTgenExperiment]:
    data = json.loads((ctx_path / "single_tgen_experiment.json").read_text())
    return [SingleTgenExperiment(**e, ctx_path=ctx_path) for e in data]

def install_observation(directory: Path, exp: SingleTgenExperiment):
    """Retain passive DNS/TCP logs without baseline collection or pruning."""
    path = directory / 'test.maude'
    lines = path.read_text().splitlines(keepends=True)
    timers = [line for line in lines if '(to baseLineAddr from baseLineAddr : initKs)' in line]
    if len(timers) != 1 or any(line.strip() == 'baseLineAct' for line in lines):
        raise ValueError('Expected performance-mode model with one unused KS timer')
    generated = ''.join(line for line in lines if line not in timers)
    path.write_text(generated)

    quatex = '\n'.join(case.to_query() for case in exp.cases())
    (directory / 'test.quatex').write_text(quatex)

def prepare_single_tgen_arm(exp: SingleTgenExperiment, run_cfg: RunConfig) -> TestConfig:
    exp_dir_path = run_cfg.temp_dir / exp.dir_name()
    exp_dir_path.mkdir(exist_ok=False)

    the_yaml = exp.get_yaml()

    (exp_dir_path / "config.yaml").write_text(yaml.safe_dump(the_yaml, sort_keys=False))

    params = SimParams(
        yaml_filename="config.yaml",
        run_time=max(exp.window_sizes)
    )
    args = GenArgs(
        params=params,
        feats=exp.feats,
        performance=True,
    )
    cfg = BuildConfig(
        name=f"{exp.name}", 
        markov_v1_dirs=MARKOV_V1_DIRS,
        markov_v2_dirs=MARKOV_V2_DIRS,
        gen_args=args
    )

    build(cfg, run_cfg, src_dir=exp.ctx_path, build_dir=exp_dir_path)
    install_observation(exp_dir_path, exp)

    ctx = Context("ctx", exp.ctx_path)
    arg = {
        "nsims": f"{exp.n_samples}-{exp.n_samples}",
        "seed": exp.seed,
        "jobs": 0
    }

    test = TestConfig(ctx, exp.name, f"Test branch of {exp.name}", TestRunner.SMC, cfg, arg)
    return test

def read_rows(directory: Path) -> list[list[float]]:
    """Preserve run-level pairing; never use the runner's sorted marginal samples."""
    rows = [[float(value) for value in row.split()]
            for row in (directory / 'dumps' / 'all_dumps').read_text().splitlines()]
    assert all(math.isfinite(sample) for row in rows for sample in row)
    return rows

def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')