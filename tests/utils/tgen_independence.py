"""One narrow experiment: do two DNS sources compose by adding their rates?"""
from dataclasses import dataclass, asdict
import json
import logging
import math
from pathlib import Path
import shutil
import statistics
import tempfile
import hashlib
import uuid

import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg

from scipy.stats import ks_2samp

import yaml

from .build import build
from .context import BuildConfig, Context, GenArgs, TestConfig, TestRunner
from ..test_maudehcs import run

CONTEXT = Path(__file__).parents[1] / 'contexts' / 'tgen_independence'


@dataclass(frozen=True)
class Experiment:
    feature: str
    vantage: str
    network: str
    profile: str
    window_start: int
    window_size: int
    population: int
    samples: int
    single_seed: int
    joint_seed: int
    delta: float
    alpha: float
    method: str = 'p-value'

    def __post_init__(self):
        if self.method not in {'p-value', 'bound'}:
            raise ValueError('method must be p-value or bound')
        # Deliberately reject unsupported observables rather than silently using
        # addition for a mean, per-flow ECDF, or non-additive feature.
        if (self.feature, self.vantage, self.network, self.profile, self.population) != (
                'dnsQueryRate', 'cl[1]', 'client_net_mastodon', 'normal_1', 2):
            raise ValueError('This first experiment supports two DNS normal_1 sources at cl[1] only')
        if self.window_start != 0 or self.window_size != 60:
            raise ValueError('This experiment observes the fixed window [0, 60] using existing visibility semantics')
        if type(self.samples) is not int or self.samples < 2:
            raise ValueError('samples must be an integer >= 2')
        if self.single_seed == self.joint_seed or any(type(s) is not int or s < 0 for s in (self.single_seed, self.joint_seed)):
            raise ValueError('Use distinct nonnegative seeds for the two simulation streams')
        if not 0 < self.alpha < 1 or not 0 < self.delta < 1:
            raise ValueError('alpha and delta must be between 0 and 1')


def compose_rates(single, population=2):
    """Consume each independent single-source run exactly once, in raw row order."""
    if population != 2 or len(single) == 0 or len(single) % population:
        raise ValueError('Expected disjoint pairs of single-source samples')
    if any(not math.isfinite(x) or x < 0 for x in single):
        raise ValueError('Packet rates must be finite and nonnegative')
    counts = [packet_count(rate) for rate in single]
    return [sum(counts[i:i + population]) / 60 for i in range(0, len(counts), population)]


def packet_count(rate):
    """Recover the integer count behind this fixed 60-second rate observable."""
    count = round(rate * 60)
    if not math.isclose(rate * 60, count, rel_tol=0, abs_tol=1e-9):
        raise ValueError('DNS rate must represent an integer count over 60 seconds')
    return count


def install_observation(build_dir):
    # Note: we are editing the config directly because if we instead set perf = false in the experiment
    #   the -run will have baseline in it which we are avoiding in this case
    #   we instead remove baseline timer and actor and keep adversary measuring
    """Use the generated DNS observer, with no calibration or log pruning."""
    path = build_dir / 'test.maude'
    lines = path.read_text().splitlines(keepends=True)
    # Performance mode removes baseline collection but also disables DNS logging.
    # Restore passive observation and remove the orphan calibration timer;
    # guard these local adaptations against changes in generated structure.
    timers = [line for line in lines if '(to baseLineAddr from baseLineAddr : initKs)' in line]
    if len(timers) != 1 or any(line.strip() == 'baseLineAct' for line in lines):
        raise ValueError('Expected observation-only generated model with one unused KS timer')
    generated = ''.join(line for line in lines if line not in timers)
    observer = 'mkAdversaryCp3(advAddr, false)'
    if generated.count(observer) != 1:
        raise ValueError('Expected one disabled observer in performance mode')
    path.write_text(generated.replace(observer, 'mkAdversaryCp3(advAddr, true)'))
    # PMaude restarts by rewriting initConfig to completion before rval runs.
    # This is the all-flow scalar, not the per-flow/bin ECDF used by detectors.
    (build_dir / 'test.quatex').write_text(
        'eval E[s.rval("compObsFeatureX(cl[1], dnsQueryRate, '
        'getTsML(getAdversary(C)), 0.0, 60.0)")]; // cumulative dnsQueryRate 0 60\n'
    )


def prepare_arm(root, population, samples, seed, experiment, run_cfg):
    source = root / f'source-{population}'
    shutil.copytree(root / 'fixture', source)
    path = source / 'scenario.yaml'
    scenario = yaml.safe_load(path.read_text())
    if scenario['nodes'] or set(scenario['tgen']) != {'tgen_type_dns'}:
        raise ValueError('The experiment requires a DNS-only scenario with no HCS clients')
    networks = scenario['tgen']['tgen_type_dns']['tgen_per_network']
    if set(networks) != {experiment.network} or networks[experiment.network]['profiles'] != {experiment.profile: 1.0}:
        raise ValueError('Expected one network and one identical user profile')
    networks[experiment.network]['quantity'] = population
    path.write_text(yaml.safe_dump(scenario, sort_keys=False))
    cfg = BuildConfig(f'dns-{population}', (('tgen_user_models/dns', 'dns-tgen'),), (),
                      GenArgs('scenario.yaml', run_time=60, hcs_delay=0, tgen_delay=0, performance=True))
    directory = build(cfg, run_cfg, source)
    generated = (directory / 'test.maude').read_text()
    if generated.count('--- DNS TGEN:') != population or 'eq allClientsAddr = nil .' not in generated:
        raise ValueError('Generated configuration does not match the requested populations')
    install_observation(directory)
    test = TestConfig(Context('tgen_independence', source), f'dns-{population}',
                      'DNS-only additive observable experiment', TestRunner.SMC, cfg,
                      {'nsims': f'{samples}-{samples}', 'seed': seed, 'jobs': 0})
    return test, directory, scenario


def read_rates(directory, expected):
    """Use the existing runner's raw dump, never its sorted marginal samples."""
    rows = (directory / 'dumps' / 'all_dumps').read_text().splitlines()
    if len(rows) != expected or any(len(row.split()) != 1 for row in rows):
        raise ValueError('Expected one DNS rate per simulation, with the exact sample budget')
    rates = [float(row) for row in rows]
    if any(not math.isfinite(x) or x < 0 for x in rates) or not any(rates):
        raise ValueError('Invalid or entirely inactive DNS traffic')
    # Canonicalize through counts so equal discrete values have identical floats.
    return [packet_count(rate) / 60 for rate in rates]


def ks_equivalence(x, y, *, delta, alpha, method='p-value'):
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


def plot_cdfs(joint, composed, comparison, root):
    """Plot right-continuous ECDFs and the vertical gap at the KS location."""
    joint, composed = np.sort(joint), np.sort(composed)
    support = np.unique(np.concatenate((joint, composed)))
    padding = max(float(np.ptp(support)) * .04, .01)
    grid = np.r_[support[0] - padding, support, support[-1] + padding]
    fig = Figure(figsize=(9, 5.5))
    FigureCanvasAgg(fig)  # Render in workers/headless test environments without a GUI.
    ax = fig.subplots()
    for values, label in ((joint, 'Two TGENs together'), (composed, 'Sum of independent single-TGEN runs')):
        ax.step(grid, np.searchsorted(values, grid, side='right') / len(values),
                where='post', label=f'{label} (n={len(values)})', linewidth=1.8)
    location = comparison['statistic_location']
    heights = [np.searchsorted(values, location, side='right') / len(values)
               for values in (joint, composed)]
    ax.axvline(location, color='0.4', linestyle=':', label=f'KS location = {location:.6g}')
    ax.plot([location, location], heights, color='crimson', marker='o', linewidth=2.5,
            label=f"KS gap = {comparison['distance']:.4g}")
    ax.set(xlabel='DNS query rate at cl[1] (queries/second; window 0–60 s)',
           ylabel='Empirical cumulative probability', ylim=(-.025, 1.025),
           title=('DNS composition: two TGENs vs. independent sum\n'
                  f"KS statistic={comparison['distance']:.6g}, p-value={comparison['pvalue']:.6g}, "
                  f"location={location:.6g}\n"
                  f"Decision mode: {comparison['method']} | outcome: {comparison['outcome']}"))
    ax.grid(alpha=.2)
    ax.legend(loc='best', fontsize=9)
    fig.tight_layout()
    filename = f'dns-cdfs-{uuid.uuid4().hex}.png'
    fig.savefig(root / filename, dpi=160, bbox_inches='tight')
    return filename


def run_experiment(experiment, run_cfg, *, smoke=False):
    if run_cfg.override_run_time not in (None, 60):
        raise ValueError('DNS composition requires the full fixed 60-second window')
    root = Path(tempfile.mkdtemp(prefix='dns-independence-', dir=run_cfg.temp_dir))
    report = dict(experiment=asdict(experiment), mode='smoke' if smoke else 'statistical',
                  outcome='error', arms={}, report_path=str(root / 'report.json'))
    # Freeze the source fixture once; both arms must use identical model inputs.
    shutil.copytree(CONTEXT, root / 'fixture')
    rates = {}
    try:
        for name, population, samples, seed in (
                ('single', 1, 2 * experiment.samples, experiment.single_seed),
                ('joint', 2, experiment.samples, experiment.joint_seed)):
            test, directory, scenario = prepare_arm(root, population, samples, seed, experiment, run_cfg)
            report['arms'][name] = dict(
                build=str(directory), scenario=scenario, smc=test.arg,
                generation=asdict(test.build_cfg.gen_args),
                model_sha256=hashlib.sha256((directory / 'test.maude').read_bytes()).hexdigest())
            if run_cfg.build_only:
                continue
            result = run(test, directory, run_cfg)
            report['arms'][name]['result'] = result
            rates[name] = read_rates(directory, samples)
            report['arms'][name]['raw_rates'] = rates[name]
        if run_cfg.build_only:
            report['outcome'] = 'build-only'
            return report
        rates['composed'] = compose_rates(rates['single'])
        report['summaries'] = {name: dict(n=len(values), mean=statistics.mean(values),
                                        variance=statistics.variance(values)) for name, values in rates.items()}
        report['composed_samples'] = rates['composed']
        report['comparison'] = ks_equivalence(rates['joint'], rates['composed'],
                                             delta=experiment.delta, alpha=experiment.alpha, method=experiment.method)
        report['plot_file'] = plot_cdfs(rates['joint'], rates['composed'], report['comparison'], root)
        # A small execution check may compute a distance, but must never claim
        # statistical independence/equivalence just because it finished running.
        report['outcome'] = 'smoke-only' if smoke else report['comparison']['outcome']
        return report
    except Exception as exc:
        report['error'] = str(exc)
        raise
    finally:
        Path(report['report_path']).write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        if run_cfg.results_dir is not None:
            destination = Path(run_cfg.results_dir)
            destination.mkdir(parents=True, exist_ok=True)
            if 'plot_file' in report:
                shutil.copy2(root / report['plot_file'], destination / report['plot_file'])
            shutil.copy2(report['report_path'], destination / f'{root.name}.json')
        logging.getLogger(__name__).warning('DNS composition report: %s', report['report_path'])
