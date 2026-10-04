"""Shared TGEN composition experiments using the existing generator and SMC runner."""
from dataclasses import dataclass, asdict, replace
from pathlib import Path
from urllib.parse import quote
import hashlib
import json
import logging
import math
import re
import shutil
import statistics
import tempfile
import uuid

import numpy as np
import yaml
from matplotlib.figure import Figure
from matplotlib.backends.backend_agg import FigureCanvasAgg
from scipy.stats import ks_2samp

from maude_hcs.generate_cp3 import FEATURES
from maude_hcs.lib import GLOBALS
from maude_hcs.query import parse_quatex
from .build import build
from .context import BuildConfig, Context, GenArgs, TestConfig, TestRunner
from ..test_maudehcs import run

CONTEXT = Path(__file__).parents[1] / 'contexts' / 'tgen_independence'


@dataclass(frozen=True)
class Tgen:
    yaml_key: str
    directory: str
    converter: str
    version: int
    actor_label: str
    log: str


TGENS = {
    'dnsTgen': Tgen('tgen_type_dns', 'dns', 'dns-tgen', 1, 'DNS', 'dns'),
    'masTgen': Tgen('tgen_type_mastodon', 'mastodon', 'mastodon-tgen', 1, 'Mastodon', 'tcp'),
    'ftpTgen': Tgen('tgen_type_ftp', 'ftp', 'ftp-tgen', 2, 'FTP', 'tcp'),
    'minTgen': Tgen('tgen_type_minio', 'minio', 'minio-tgen', 2, 'MinIO', 'tcp'),
    'gorTgen': Tgen('tgen_type_gorilla', 'gorilla', 'gorilla-tgen', 2, 'Gorilla', 'tcp'),
    'ircTgen': Tgen('tgen_type_irc', 'irc', 'irc-tgen', 2, 'IRC', 'tcp'),
}


@dataclass(frozen=True)
class Recipe:
    log: str
    count: str
    size: str | None = None

    @property
    def units(self):
        return 'bytes/packet' if self.size else 'packets/second'


# These are the same selectors used by compObsFeatureX. In particular, total
# TCP count/size uses an OR over directions, not the sum of the two directions.
RECIPES = {
    'dnsQueryRate': Recipe('dns', 'countDNSQuery'),
    'dnsQuerySize': Recipe('dns', 'countDNSQuery', 'sizeDNSQuery'),
    'dnsRespSize': Recipe('dns', 'countDNSResp', 'sizeDNSResp'),
    'tcpOutPktRate': Recipe('tcp', 'countTCPOutPkt'),
    'tcpInPktRate': Recipe('tcp', 'countTCPInPkt'),
    'tcpPktSize': Recipe('tcp', 'countTCPPkt', 'sizeTCPPkt'),
}


@dataclass(frozen=True)
class Experiment:
    id: str
    tgen_type: str
    profile: str
    network: str
    single_seed: int
    joint_seed: int
    features: list[str]
    vantage_points: list[str]

    def cases(self):
        return [(feature, vantage) for feature in self.features for vantage in self.vantage_points]

    def case_id(self, feature, vantage):
        return f'{self.id}__{self.tgen_type}__{feature}__{vantage}'

    def group_key(self):
        # Features do not affect source behavior. Entries differing only in their
        # query selection can share the same pair of simulations in this suite.
        return (self.tgen_type, self.profile, self.network, self.single_seed, self.joint_seed)


@dataclass(frozen=True)
class Suite:
    experiments: list[Experiment]
    schema_version: int = 2
    scenario: str = 'scenario1'
    scenario_file: str = 'scenario.yaml'
    window_start: int = 0
    window_size: int = 60
    population: int = 2
    samples: int = 5000
    method: str = 'p-value'
    alpha: float = .05
    delta: float = .05
    multiplicity: str = 'none'

    @property
    def family_size(self):
        return sum(len(e.cases()) for e in self.experiments)

    @property
    def effective_alpha(self):
        return self.alpha / self.family_size if self.multiplicity == 'bonferroni' else self.alpha

    def validate(self, context=CONTEXT):
        if self.schema_version != 2 or self.scenario != 'scenario1':
            raise ValueError('Expected schema_version=2 and scenario1')
        if self.window_start != 0:
            raise ValueError('window_start must be zero')
        for name, minimum in (('window_size', 1), ('population', 2), ('samples', 2)):
            value = getattr(self, name)
            if type(value) is not int or value < minimum:
                raise ValueError(f'{name} must be an integer >= {minimum}')
        if self.method not in {'p-value', 'bound'} or self.multiplicity not in {'bonferroni', 'none'}:
            raise ValueError('Invalid comparison method or multiplicity policy')
        if not 0 < self.alpha < 1 or not 0 < self.delta < 1:
            raise ValueError('alpha and delta must be between 0 and 1')
        if not self.experiments:
            raise ValueError('Select at least one experiment')
        # Paths and IDs are local names, not arbitrary paths or Maude fragments.
        if Path(self.scenario_file).name != self.scenario_file:
            raise ValueError('scenario_file must be a filename in the context')
        scenario = yaml.safe_load((context / self.scenario_file).read_text())
        if scenario['nodes']:
            raise ValueError('Composition fixture must have no HCS clients')
        ids, identities = set(), set()
        for e in self.experiments:
            if not re.fullmatch(r'[A-Za-z0-9_-]+', e.id) or e.id in ids:
                raise ValueError(f'Invalid or duplicate experiment ID: {e.id}')
            ids.add(e.id)
            if e.tgen_type not in TGENS:
                raise ValueError(f'Unknown TGEN type: {e.tgen_type}')
            if not re.fullmatch(r'[A-Za-z0-9_-]+', e.profile):
                raise ValueError('Invalid profile name')
            adapter = TGENS[e.tgen_type]
            if not (context / 'tgen_user_models' / adapter.directory / f'{e.profile}.json').is_file():
                raise ValueError(f'Missing profile: {e.tgen_type}/{e.profile}')
            if e.network not in scenario['network'] or scenario['network'][e.network]['network'] != 'client':
                raise ValueError(f'Expected a configured client placement network: {e.network}')
            if e.single_seed == e.joint_seed or any(type(s) is not int or s < 0 for s in (e.single_seed, e.joint_seed)):
                raise ValueError('Use distinct nonnegative seeds per pair of arms')
            if not e.features or not e.vantage_points or set(e.vantage_points) != {'ixpN'}:
                raise ValueError('Explicit features and ixpN-only vantage_points are required')
            for feature, vantage in e.cases():
                if feature not in FEATURES:
                    raise ValueError(f'Unknown feature: {feature}')
                identity = (e.tgen_type, e.profile, e.network, feature, vantage)
                if identity in identities:
                    raise ValueError(f'Duplicate observable configuration: {identity}')
                identities.add(identity)
        return self


def load_suite(path=CONTEXT / 'experiment.json'):
    data = json.loads(Path(path).read_text())
    data['experiments'] = [Experiment(**e) for e in data['experiments']]
    return Suite(**data).validate(Path(path).parent)


def select_suite(suite, *, tgen_type=None, window_size=None):
    """Apply CLI selection before sampling and computing the statistical family."""
    if tgen_type is not None:
        aliases = {alias.lower(): kind for kind, adapter in TGENS.items()
                   for alias in (kind, adapter.directory)}
        kind = aliases.get(tgen_type.lower())
        if kind is None:
            raise ValueError(f'Unknown TGEN type: {tgen_type}; use ' + ', '.join(TGENS))
        entries = [entry for entry in suite.experiments if entry.tgen_type == kind]
        if not entries:
            raise ValueError(f'No configured experiments for {kind}')
        suite = replace(suite, experiments=entries)
    if window_size is not None:
        suite = replace(suite, window_size=window_size)
    return suite.validate()


def recipe_for(experiment, feature):
    recipe = RECIPES.get(feature)
    return recipe if recipe and recipe.log == TGENS[experiment.tgen_type].log else None


def query_manifest(entries, suite):
    """Deduplicate summaries while keeping each feature's direct reference query."""
    columns = {}
    for e in entries:
        for feature, vantage in e.cases():
            recipe = recipe_for(e, feature)
            if recipe is None:
                continue
            log = 'getTsML' if recipe.log == 'dns' else 'getTsPL'
            args = f'{vantage}, {log}(getAdversary(C)), 0.0, {suite.window_size}.0'
            columns[f'{feature}:{vantage}'] = dict(
                name=feature, vantage=vantage, integer=False,
                expression=f'compObsFeatureX({vantage}, {feature}, {log}(getAdversary(C)), 0.0, {suite.window_size}.0)')
            for operator in (recipe.count, recipe.size):
                if operator:
                    name = f'summary_{operator}'
                    columns[f'{name}:{vantage}'] = dict(
                        name=name, vantage=vantage, integer=True, expression=f'float({operator}({args}))')
    return list(columns.values())


def install_observation(directory, manifest, window_size):
    """Retain passive DNS/TCP logs without baseline collection or pruning."""
    path = directory / 'test.maude'
    lines = path.read_text().splitlines(keepends=True)
    timers = [line for line in lines if '(to baseLineAddr from baseLineAddr : initKs)' in line]
    if len(timers) != 1 or any(line.strip() == 'baseLineAct' for line in lines):
        raise ValueError('Expected performance-mode model with one unused KS timer')
    generated = ''.join(line for line in lines if line not in timers)
    observer = 'mkAdversaryCp3(advAddr, false)'
    if generated.count(observer) != 1:
        raise ValueError('Expected one disabled observer')
    path.write_text(generated.replace(observer, 'mkAdversaryCp3(advAddr, true)'))
    # Five-field comments already carry vantage identity in the existing parser.
    query = ''.join(f'eval E[s.rval("{c["expression"]}")]; // cumulative {c["name"]} 0 {window_size} {c["vantage"]}\n'
                    for c in manifest)
    names = [q.to_name() for q in parse_quatex(query)]
    if len(names) != len(manifest) or len(set(names)) != len(names):
        raise ValueError('Query identities must be unique')
    (directory / 'test.quatex').write_text(query)


def prepare_arm(root, group, population, samples, seed, suite, run_cfg, manifest):
    e = group[0]
    adapter = TGENS[e.tgen_type]
    source = root / f'source-{population}'
    shutil.copytree(root.parent / 'fixture', source)
    scenario = yaml.safe_load((source / suite.scenario_file).read_text())
    scenario.update(conversation_duration=suite.window_size, analysis_window_size=suite.window_size)
    # Keep shared services, but replace source populations rather than appending
    # them to the original DNS-only fixture. No autonomous monitor UM is added.
    scenario['tgen'] = {adapter.yaml_key: {'tgen_per_network': {
        e.network: {'quantity': population, 'profiles': {e.profile: 1.0}}}}}
    (source / suite.scenario_file).write_text(yaml.safe_dump(scenario, sort_keys=False))
    conversion = ((f'tgen_user_models/{adapter.directory}', adapter.converter),)
    cfg = BuildConfig(f'{e.id}-{population}', conversion if adapter.version == 1 else (),
                      conversion if adapter.version == 2 else (),
                      GenArgs(suite.scenario_file, run_time=suite.window_size,
                              hcs_delay=0, tgen_delay=0, performance=True))
    directory = build(cfg, run_cfg, source)
    generated = (directory / 'test.maude').read_text()
    if generated.count(f'--- {adapter.actor_label} TGEN:') != population or 'eq allClientsAddr = nil .' not in generated:
        raise ValueError('Generated model has an unexpected TGEN/HCS population')
    install_observation(directory, manifest, suite.window_size)
    test = TestConfig(Context('tgen_independence', source), f'{e.id}-{population}',
                      'TGEN observable composition', TestRunner.SMC, cfg,
                      {'nsims': f'{samples}-{samples}', 'seed': seed, 'jobs': 0})
    return test, directory, scenario


def read_rows(directory, expected, manifest):
    """Preserve run-level pairing; never use the runner's sorted marginal samples."""
    rows = [[float(value) for value in row.split()]
            for row in (directory / 'dumps' / 'all_dumps').read_text().splitlines()]
    if len(rows) != expected or any(len(row) != len(manifest) for row in rows):
        raise ValueError('Unexpected raw sample dimensions')
    for row in rows:
        for i, column in enumerate(manifest):
            value = row[i]
            if not math.isfinite(value) or value < 0:
                raise ValueError('Expected finite nonnegative observations')
            if column['integer']:
                if value > 2**53 or not math.isclose(value, round(value), rel_tol=0, abs_tol=1e-9):
                    raise ValueError('Count/byte summary is not an exactly representable integer')
                row[i] = round(value)
    return rows


def reconstruct(rows, manifest, feature, vantage, window_size, population=1):
    """Sum sufficient statistics in disjoint blocks before taking rates/means."""
    if not rows or len(rows) % population:
        raise ValueError('Samples must form disjoint complete population blocks')
    recipe = RECIPES[feature]
    index = {(c['name'], c['vantage']): i for i, c in enumerate(manifest)}
    count_index = index[(f'summary_{recipe.count}', vantage)]
    size_index = index[(f'summary_{recipe.size}', vantage)] if recipe.size else None
    values, counts = [], []
    for start in range(0, len(rows), population):
        block = rows[start:start + population]
        count = sum(row[count_index] for row in block)
        size = sum(row[size_index] for row in block) if size_index is not None else None
        if count == 0 and size not in (None, 0):
            raise ValueError('Nonzero byte total with zero packets')
        values.append((size / count if count else 0.) if size is not None else count / window_size)
        counts.append(count)
    return values, counts


def check_direct(rows, manifest, feature, vantage, window_size):
    values, _ = reconstruct(rows, manifest, feature, vantage, window_size)
    index = next(i for i, c in enumerate(manifest) if (c['name'], c['vantage']) == (feature, vantage))
    if any(not math.isclose(value, row[index], rel_tol=1e-10, abs_tol=1e-12)
           for value, row in zip(values, rows)):
        raise ValueError('Summary reconstruction disagrees with direct model feature')


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


def plot_cdfs(joint, composed, comparison, root, *, case_id, feature, vantage, population, window_size):
    """Plot right-continuous ECDFs and the vertical gap at the KS location."""
    joint, composed = np.sort(joint), np.sort(composed)
    support = np.unique(np.concatenate((joint, composed)))
    padding = max(float(np.ptp(support)) * .04, .01)
    grid = np.r_[support[0] - padding, support, support[-1] + padding]
    fig = Figure(figsize=(9, 5.5))
    FigureCanvasAgg(fig)  # Render in workers/headless test environments without a GUI.
    ax = fig.subplots()
    for values, label in ((joint, f'{population} TGENs together'), (composed, 'Composed independent single-TGEN runs')):
        ax.step(grid, np.searchsorted(values, grid, side='right') / len(values),
                where='post', label=f'{label} (n={len(values)})', linewidth=1.8)
    location = comparison['statistic_location']
    heights = [np.searchsorted(values, location, side='right') / len(values)
               for values in (joint, composed)]
    ax.axvline(location, color='0.4', linestyle=':', label=f'KS location = {location:.6g}')
    ax.plot([location, location], heights, color='crimson', marker='o', linewidth=2.5,
            label=f"KS gap = {comparison['distance']:.4g}")
    ax.set(xlabel=f'{feature} at {vantage} ({RECIPES[feature].units}; window 0–{window_size} s)',
           ylabel='Empirical cumulative probability', ylim=(-.025, 1.025),
           title=(f'{case_id}\n'
                  f"KS statistic={comparison['distance']:.6g}, p-value={comparison['pvalue']:.6g}, "
                  f"location={location:.6g}\n"
                  f"Decision mode: {comparison['method']} | outcome: {comparison['outcome']}"))
    ax.grid(alpha=.2)
    ax.legend(loc='best', fontsize=9)
    fig.tight_layout()
    filename = f'{quote(case_id, safe="")}-{uuid.uuid4().hex}.png'
    fig.savefig(root / filename, dpi=160, bbox_inches='tight')
    return filename


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')


def fingerprint(directory):
    """Hash model inputs, excluding generated reports, logs and documentation."""
    digest = hashlib.sha256()
    for path in sorted(directory.rglob('*')):
        if path.is_file() and path.suffix in {'.json', '.yaml', '.maude'}:
            digest.update(str(path.relative_to(directory)).encode() + b'\0' + path.read_bytes())
    return digest.hexdigest()


def analyze_case(case, single, joint, manifest, suite, root, smoke):
    feature, vantage = case['feature'], case['vantage']
    # Test the summary semantics on both arms, independently of the KS decision.
    for rows in (single, joint):
        check_direct(rows, manifest, feature, vantage, suite.window_size)
    observed, observed_counts = reconstruct(joint, manifest, feature, vantage, suite.window_size)
    composed, composed_counts = reconstruct(single, manifest, feature, vantage, suite.window_size, suite.population)
    case['activity'] = dict(joint_nonempty=sum(n > 0 for n in observed_counts),
                            composed_nonempty=sum(n > 0 for n in composed_counts))
    case['summaries'] = {name: dict(n=len(values), mean=statistics.mean(values), variance=statistics.variance(values))
                         for name, values in (('joint', observed), ('composed', composed))}
    samples_file = f'{quote(case["id"], safe="")}-samples.json'
    write_json(root / samples_file, dict(joint=observed, composed=composed))
    case['samples_file'] = samples_file
    if not any(observed_counts) or not any(composed_counts):
        case.update(outcome='inactive', reason='No relevant packets observed in at least one arm; no statistical comparison')
        return
    comparison = ks_equivalence(observed, composed, delta=suite.delta,
                                alpha=suite.effective_alpha, method=suite.method)
    case['comparison'] = comparison
    # Smoke plots must not present the diagnostic decision as a suite pass.
    plot_comparison = dict(comparison, outcome='smoke-only') if smoke else comparison
    case['plot_file'] = plot_cdfs(observed, composed, plot_comparison, root, case_id=case['id'],
                                  feature=feature, vantage=vantage, population=suite.population,
                                  window_size=suite.window_size)
    case['outcome'] = 'smoke-only' if smoke else comparison['outcome']
    case['reason'] = ('Execution and reconstruction checks only' if smoke else
                      comparison.get('decision', 'KS distance confidence interval compared with delta'))


def run_suite(suite, run_cfg, *, smoke=False, context=CONTEXT):
    """Run each unique model pair once and retain every selected case's outcome."""
    suite.validate(context)
    if run_cfg.override_run_time not in (None, suite.window_size):
        raise ValueError('override_run_time must match experiment window_size')
    root = Path(tempfile.mkdtemp(prefix='tgen-composition-', dir=run_cfg.temp_dir))
    report = dict(schema_version=2, run_id=root.name, experiment=asdict(suite),
                  mode='smoke' if smoke else 'statistical', report_path=str(root / 'report.json'),
                  family_size=suite.family_size, effective_alpha=suite.effective_alpha,
                  groups={}, results={})
    shutil.copytree(context, root / 'fixture')
    report['source_sha256'] = fingerprint(root / 'fixture')
    report['library_sha256'] = fingerprint(Path(GLOBALS.LIB_DIR))
    groups = {}
    for e in suite.experiments:
        groups.setdefault(e.group_key(), []).append(e)
        for feature, vantage in e.cases():
            case_id = e.case_id(feature, vantage)
            supported = recipe_for(e, feature) is not None
            report['results'][case_id] = dict(
                id=case_id, name=f'{e.tgen_type}__{feature}__{vantage}',
                tgen_type=e.tgen_type, feature=feature, vantage=vantage,
                profile=e.profile, network=e.network, window_start=suite.window_start,
                window_size=suite.window_size, population=suite.population,
                method=suite.method, alpha=suite.effective_alpha, delta=suite.delta,
                recipe=asdict(RECIPES[feature]) if supported else None,
                outcome='pending' if supported else 'unsupported',
                reason='' if supported else 'No composition recipe for this type and feature; no plot')
    try:
        for entries in groups.values():
            e = entries[0]
            cases = [report['results'][item.case_id(f, v)] for item in entries for f, v in item.cases()
                     if recipe_for(item, f)]
            if not cases:
                continue
            group_id = e.id
            for case in cases:
                case['group_id'] = group_id
            directory = root / group_id
            directory.mkdir()
            manifest = query_manifest(entries, suite)
            group_report = dict(query_manifest=manifest, arms={})
            report['groups'][group_id] = group_report
            rows_by_arm = {}
            try:
                for name, population, samples, seed in (
                        ('single', 1, suite.population * suite.samples, e.single_seed),
                        ('joint', suite.population, suite.samples, e.joint_seed)):
                    test, build_dir, scenario = prepare_arm(directory, entries, population, samples, seed,
                                                           suite, run_cfg, manifest)
                    arm = dict(build=str(build_dir), scenario=scenario, generation=asdict(test.build_cfg.gen_args),
                               smc=test.arg, model_sha256=fingerprint(build_dir))
                    group_report['arms'][name] = arm
                    if run_cfg.build_only:
                        continue
                    # The existing framework owns process isolation and timeouts.
                    run(test, build_dir, run_cfg)
                    # Fail on native model load errors even if SMC emitted numeric rows.
                    for log in (build_dir / 'logs').glob('*stderr*'):
                        if any(marker in log.read_text().lower() for marker in
                               ('unpatchable errors', 'unable to locate file:', 'no parse for term')):
                            raise ValueError(f'Maude load/query error; see {log}')
                    rows = read_rows(build_dir, samples, manifest)
                    rows_by_arm[name] = rows
                    filename = f'{group_id}-{name}-rows.json'
                    write_json(root / filename, rows)
                    arm['rows_file'] = filename
                if run_cfg.build_only:
                    for case in cases:
                        case.update(outcome='build-only', reason='Built both populations; simulation and plots omitted')
                else:
                    for case in cases:
                        try:
                            analyze_case(case, rows_by_arm['single'], rows_by_arm['joint'], manifest, suite, root, smoke)
                        except Exception as exc:
                            case.update(outcome='error', reason=str(exc))
            except Exception as exc:
                # Keep validation evidence with the report, even when temporary
                # builds are cleaned up or the report is exported elsewhere.
                for arm_name, arm in group_report['arms'].items():
                    for diagnostic in sorted(Path(arm['build']).glob('smc-error-*.json')):
                        detail = json.loads(diagnostic.read_text())
                        state = Path(detail['state_file'])
                        state_name = f'{group_id}-{arm_name}-{state.name}'
                        shutil.copy2(state, root / state_name)
                        detail['state_file'] = state_name
                        arm.setdefault('validation_errors', []).append(detail)
                group_report['error'] = str(exc)
                for case in cases:
                    case.update(outcome='error', reason=str(exc))
            # Checkpoint after every group; failure never suppresses later groups.
            write_json(root / 'report.json', report)
    finally:
        write_json(root / 'report.json', report)
        if run_cfg.results_dir is not None:
            # Each run gets its own directory; all JSON/PNG references stay relative.
            destination = Path(run_cfg.results_dir) / root.name
            destination.mkdir(parents=True, exist_ok=True)
            for path in root.iterdir():
                if path.is_file():
                    shutil.copy2(path, destination / path.name)
        logging.getLogger(__name__).warning('TGEN composition report: %s', root / 'report.json')
    return report
