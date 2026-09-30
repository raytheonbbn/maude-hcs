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

    def __post_init__(self):
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
    # TODO: no need to replace, instead set perf = false in the experiment
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
                      {'nsims': f'{samples}-{samples}', 'seed': seed, 'jobs': 1})
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


def ks_equivalence(x, y, *, delta, alpha):
    """A fixed-look bound on distributional distance, not an equality p-value."""
    if not 0 < alpha < 1 or not 0 < delta < 1:
        raise ValueError('alpha and delta must be between 0 and 1')
    if not x or not y or any(not math.isfinite(v) for v in [*x, *y]):
        raise ValueError('Expected nonempty finite samples')
    distance = float(ks_2samp(x, y).statistic)
    # Each empirical CDF gets a DKW bound at alpha/2. Triangle and union
    # bounds give a confidence interval for the true KS distance.
    margin = sum(math.sqrt(math.log(4 / alpha) / (2 * n)) for n in (len(x), len(y)))
    lower, upper = max(0., distance - margin), min(1., distance + margin)
    return dict(distance=distance, lower=lower, upper=upper, delta=delta, alpha=alpha,
                outcome='pass' if upper < delta else 'fail' if lower > delta else 'inconclusive')


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
                                             delta=experiment.delta, alpha=experiment.alpha)
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
            shutil.copy2(report['report_path'], destination / f'{root.name}.json')
        logging.getLogger(__name__).warning('DNS composition report: %s', report['report_path'])
