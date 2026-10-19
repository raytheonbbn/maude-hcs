"""Shared TGEN composition experiments using the existing generator and SMC runner."""
from dataclasses import dataclass, asdict, replace, field
from pathlib import Path
from urllib.parse import quote
from typing import Self, Any, Sequence
from enum import Enum

import hashlib
import json
import logging
import math
import re
import shutil
import statistics
import tempfile
import uuid
import typing
import os

import numpy as np
import yaml
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from scipy.stats import ks_2samp

from maude_hcs.generate_cp3 import FEATURES
from maude_hcs.lib import GLOBALS
from maude_hcs.query import parse_quatex
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
    exp: Experiment
    feat: str
    vantage: str
    window_size: int

    status: CaseStatus = CaseStatus.PENDING

    ks_distance: float | None   = None
    ks_location: float | None   = None
    p_value: float | None       = None
    passed: bool | None         = None
    traceback: str | None       = None

    test_samples: list[float] | None       = None
    control_samples: list[float] | None    = None

    def to_query(self) -> str:
        if self.feat.startswith("tcp"): log = "getTsPL"
        elif self.feat.startswith("dns"): log = "getTsML"
        else: raise RuntimeError("unrecognized feat")

        expr = f'compObsFeatureX({self.vantage}, {self.feat}, {log}(getAdversary(C)), 0.0, {self.window_size}.0)'
        tag =  f"// cumulative {self.feat} 0 {self.window_size} {self.vantage}"
        return f"eval E[s.rval(\"{expr}\")]; {tag}"

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["status"] = str(self.status) 
        del result["exp"]
        return result
    
    def to_sorted_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["status"] = str(self.status)
        del result["exp"]
        result["test_samples"].sort()
        result["control_samples"].sort()
        return result

    def case_id(self) -> str:
        return f"{self.exp.name}+{self.feat}+{self.vantage}+{self.window_size}"

@dataclass(frozen=True, kw_only=True)
class Experiment:
    ctx_path: Path
    name: str
    yaml_chunk: str
    feats: list[str]
    vantages: list[str]
    window_sizes: list[int]

    control_seed: int = 0
    test_seed: int = 0

    n_samples: int = 5000
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

    def get_yamls(self) -> tuple[dict, dict]:
        net_chunk = yaml.safe_load((self.ctx_path / "yaml_chunks" / "network.yaml").read_text())
        all_chunk = yaml.safe_load((self.ctx_path / "yaml_chunks" / f"{self.yaml_chunk}.yaml").read_text())
        tgen_chunk = {"tgen": all_chunk["tgen"]}
        header_chunk = self.to_yaml_header()

        control_yaml = {"env": "control"} | header_chunk | net_chunk | tgen_chunk
        test_yaml = {"env": "test"} | header_chunk | net_chunk | all_chunk
        return (control_yaml, test_yaml)

    def analyze_case(self, case: Case, run_cfg: RunConfig) -> None:
        control_ecdf = sorted(case.control_samples)
        test_ecdf = sorted(case.test_samples)

        if any(control_ecdf + test_ecdf):
            ks_result = ks_equivalence(control_ecdf, test_ecdf, delta=self.delta,
                                        alpha=self.alpha, method=self.method)
            case.ks_distance = ks_result["distance"]
            case.p_value = ks_result["pvalue"]
            case.passed = not (ks_result["outcome"] == "fail")
            case.ks_location = ks_result["statistic_location"]
            case.status = CaseStatus.COMPLETE

            plot_cdfs(case, run_cfg)
        
        else:
            case.status = CaseStatus.INVALID
    
    def run(self, run_cfg: RunConfig, smoke: bool = False) -> list[Case]:
        control_cfg, test_cfg = prepare_confidentiality_arms(self, run_cfg)
        if run_cfg.build_only: return []

        cases = self.cases()
        queries_by_arm = {}

        exp_dir = run_cfg.temp_dir / self.dir_name()
        control_dir = exp_dir / "control"
        test_dir = exp_dir / "test"

        for arm_name, arm_cfg, arm_dir in [("control", control_cfg, control_dir), ("test", test_cfg, test_dir)]:
            run(arm_cfg, arm_dir, run_cfg)

            for log in (arm_dir / 'logs').glob('*stderr*'):
                if any(marker in log.read_text().lower() for marker in
                    ('unpatchable errors', 'unable to locate file:', 'no parse for term')):
                    raise ValueError(f'Maude load/query error; see {log}')

            rows = read_rows(arm_dir)
            len_first_row = len(rows[0])
            assert all([len(row) == len_first_row for row in rows]), f"expected all rows to have same length, at least one differs"
            assert len(rows) == self.n_samples, f"expected {self.n_samples} rows in output, found {len(rows)} rows"
            assert len_first_row == len(cases), f"expected {len(cases)} samples in each row of output, found {len_first_row} samples"

            # By transposing, we now have all samples (across all sims) for a single given query on the same row
            trans_rows = np.transpose(rows).tolist()
            queries_by_arm[arm_name] = trans_rows

        # The list of cases corresponds with the list of quatex queries, and therefore corresponds with the output samples
        for control_query_samples, test_query_samples, case in zip(queries_by_arm["control"], queries_by_arm["test"], cases):
            case.control_samples = control_query_samples
            case.test_samples = test_query_samples
            self.analyze_case(case, run_cfg)
        
        write_json(exp_dir / "cases.json", list(map(lambda x: x.to_dict(), cases)))
        write_json(exp_dir / "cases_sorted.json", list(map(lambda x: x.to_sorted_dict(), cases)))

        return cases

def run_suite(exps: list[Experiment], run_cfg: RunConfig, smoke: bool = False) -> list[Case]:
    cases = []

    for exp in exps:
        cases.extend(exp.run(run_cfg, smoke))
    
    return cases

def load_confidentiality_suite(ctx_path: Path) -> list[Experiment]:
    data = json.loads((ctx_path / "experiment.json").read_text())
    return [Experiment(**e, ctx_path=ctx_path) for e in data]

def install_observation(directory: Path, exp: Experiment):
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

def prepare_confidentiality_arms(exp: Experiment, run_cfg: RunConfig) -> tuple[TestConfig, TestConfig]:
    exp_dir_path = run_cfg.temp_dir / exp.dir_name()
    exp_dir_path.mkdir(exist_ok=False)

    control_yaml, test_yaml = exp.get_yamls()
    test_cfgs = []
    
    for arm_name, arm_yaml in [("control", control_yaml), ("test", test_yaml)]:
        build_dir_path = exp_dir_path / arm_name
        build_dir_path.mkdir(exist_ok=False)

        (build_dir_path / f"{arm_name}.yaml").write_text(yaml.safe_dump(arm_yaml, sort_keys=False))

        params = SimParams(
            yaml_filename=f"{arm_name}.yaml",
            run_time=max(exp.window_sizes)
        )
        logger.warning(exp.vantages)
        args = GenArgs(
            params=params,
            feats=exp.feats,
            performance=True,
        )
        cfg = BuildConfig(
            name=f"{exp.name}-{arm_name}", 
            markov_v1_dirs=MARKOV_V1_DIRS,
            markov_v2_dirs=MARKOV_V2_DIRS,
            gen_args=args
        )

        build(cfg, run_cfg, src_dir=exp.ctx_path, build_dir=build_dir_path)
        install_observation(build_dir_path, exp)

        ctx = Context(arm_name, exp.ctx_path)
        arg = {
            "nsims": f"{exp.n_samples}-{exp.n_samples}",
            "seed": exp.test_seed if arm_name == "test" else exp.control_seed,
            "jobs": 0
        }

        test = TestConfig(ctx, exp.name, f"Test branch of {exp.name}", TestRunner.SMC, cfg, arg)
        test_cfgs.append(test)
    
    return tuple(test_cfgs)

def read_rows(directory: Path) -> list[list[float]]:
    """Preserve run-level pairing; never use the runner's sorted marginal samples."""
    rows = [[float(value) for value in row.split()]
            for row in (directory / 'dumps' / 'all_dumps').read_text().splitlines()]
    assert all(math.isfinite(sample) for row in rows for sample in row)
    return rows

def ks_equivalence(x, y, *, delta, alpha, method='p-value') -> dict[str, str | float]:
    """Choose equality-test acceptance or a confidence bound on KS distance.

    A p-value pass means equality was not rejected; it is not evidence of
    equivalence within delta. Bound mode retains that stronger acceptance rule.
    """
    if method not in {'p-value', 'bound'}:
        raise ValueError('method must be p-value or bound')
    if not 0 < alpha < 1 or not 0 < delta < 1:
        raise ValueError('alpha and delta must be between 0 and 1')
    if len(x) == 0 or len(y) == 0 or any(not math.isfinite(v) for v in [*x, *y]):
        raise ValueError('Expected nonempty finite samples')
    ks = ks_2samp(x, y)
    # Store native scalars, not the scipy result object, for a portable JSON report.
    result = dict(method=method, distance=float(ks.statistic),
                  pvalue=float(ks.pvalue), statistic_location=float(ks.statistic_location),
                  statistic_sign=int(ks.statistic_sign), delta=delta, alpha=alpha)
    if method == 'p-value':
        reject = result['pvalue'] < alpha
        result.update(reject_null=reject,
                      decision='reject_equal_distributions' if reject else 'do_not_reject_equal_distributions',
                      outcome='fail' if reject else 'pass')
    else:
        # DKW bounds at alpha/2 for each empirical CDF, combined by a union bound.
        margin = sum(math.sqrt(math.log(4 / alpha) / (2 * n)) for n in (len(x), len(y)))
        lower, upper = max(0., result['distance'] - margin), min(1., result['distance'] + margin)
        result.update(lower=lower, upper=upper,
                      outcome='pass' if upper < delta else 'fail' if lower > delta else 'inconclusive')
    return result

def plot_cdfs(case: Case, run_cfg: RunConfig) -> str:
    """Plot right-continuous ECDFs and the vertical gap at the KS location."""

    assert case.control_samples is not None
    assert case.test_samples is not None
    assert case.ks_location is not None
    assert case.ks_distance is not None

    control_ecdf = sorted(case.control_samples)
    test_ecdf = sorted(case.test_samples)

    support = np.unique(np.concatenate((control_ecdf, test_ecdf)))
    padding = max(float(np.ptp(support)) * .04, .01)
    grid = np.r_[support[0] - padding, support, support[-1] + padding]
    fig = Figure(figsize=(9, 5.5))
    FigureCanvasAgg(fig)  # Render in workers/headless test environments without a GUI.
    ax = fig.subplots()
    for values, label in ((control_ecdf, f'tgen-only arm'), (test_ecdf, 'hcs+tgen arm')):
        ax.step(grid, np.searchsorted(values, grid, side='right') / len(values),
                where='post', label=f'{label} (n={len(values)})', linewidth=1.8)
    location = case.ks_location
    heights = [np.searchsorted(values, location, side='right') / len(values)
               for values in (control_ecdf, test_ecdf)]
    ax.axvline(location, color='0.4', linestyle=':', label=f'KS location = {location:.6g}')
    ax.plot([location, location], heights, color='crimson', marker='o', linewidth=2.5,
            label=f"KS gap = {case.ks_distance:.4g}")
    ax.set(xlabel=f'{case.feat} at {case.vantage}; window 0–{case.window_size}s',
           ylabel='Empirical cumulative probability', ylim=(-.025, 1.025),
           title=(f'{case.case_id()}\n'
                  f"KS statistic={case.ks_distance:.6g}, p-value={case.p_value:.6g}, "
                  f"location={location:.6g}\n"
                  f"Decision mode: {case.exp.method} | hidden: {case.passed}"))
    ax.grid(alpha=.2)
    ax.legend(loc='best', fontsize=9)
    fig.tight_layout()
    filename = f'{case.case_id()}.png'
    fig.savefig(run_cfg.temp_dir / case.exp.dir_name() / filename, dpi=160, bbox_inches='tight')
    return filename

def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')