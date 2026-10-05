"""Composition math, explicit selection, shared execution and portable reports."""
from dataclasses import replace
from pathlib import Path
import json

import pytest
import yaml

from maude_hcs.query import parse_quatex
from .utils import tgen_independence as tgen
from .utils.context import RunConfig


def suite():
    return replace(tgen.load_suite(), window_size=[60])


def test_explicit_matrix():
    config = suite()
    assert config.family_size == 18
    assert len({e.tgen_type for e in config.experiments}) == 6
    assert all(e.vantage_points == ['ixpN'] for e in config.experiments)
    assert config.multiplicity == 'none'
    assert config.effective_alpha == .05
    assert tgen.Suite(experiments=config.experiments).multiplicity == 'none'
    assert replace(config, multiplicity='bonferroni').effective_alpha == .05 / 18
    names = [e.case_id(f, v, 60) for e in config.experiments for f, v in e.cases()]
    assert len(set(names)) == 18


@pytest.mark.parametrize('changes', [dict(window_size=0), dict(window_size=-1), dict(window_size=True),
                                     dict(window_size=1.5), dict(window_size=[]), dict(window_size=[60, 60]),
                                     dict(window_size=[True]), dict(window_size=[0]), dict(window_size=[1.5]),
                                     dict(window_size=[60, -1]), dict(window_size="60"), dict(samples=1), dict(population=1),
                                     dict(window_start=1), dict(method='wrong'), dict(multiplicity='wrong')])
def test_invalid_suite(changes):
    with pytest.raises(ValueError):
        replace(suite(), **changes).validate()


@pytest.mark.parametrize('changes', [dict(tgen_type='unknown'), dict(profile='absent'),
                                     dict(features=['unknown']), dict(vantage_points=['cl[1]']),
                                     dict(features=[]), dict(joint_seed=105), dict(network='absent'),
                                     dict(features=['dnsQueryRate', 'dnsQueryRate'])])
def test_invalid_entry(changes):
    config = suite()
    with pytest.raises(ValueError):
        replace(config, experiments=[replace(config.experiments[0], **changes)]).validate()


def test_duplicate_configurations_and_ids():
    config = suite()
    first = config.experiments[0]
    for other in (first, replace(first, id='another')):
        with pytest.raises(ValueError, match='Duplicate|duplicate'):
            replace(config, experiments=[first, other]).validate()


def test_query_manifest_has_unique_names_and_shared_summaries():
    config = suite()
    columns = tgen.query_manifest([config.experiments[0]], 60)
    assert len(columns) == 7  # Three direct features, four distinct count/size summaries.
    assert sum(c['name'] == 'summary_countDNSQuery' for c in columns) == 1
    assert all('getTsML' in c['expression'] for c in columns)
    tcp = tgen.query_manifest([config.experiments[1]], 60)
    assert all('getTsPL' in c['expression'] for c in tcp)
    assert any('sizeTCPPkt' in c['expression'] for c in tcp)


def test_mean_composition_weights_counts_and_keeps_zero_windows():
    config = suite()
    columns = tgen.query_manifest([config.experiments[0]], 60)
    def row(count, size):
        values = {'summary_countDNSQuery': count, 'summary_sizeDNSQuery': size}
        return [values.get(c['name'], 0) for c in columns]
    rows = [row(1, 100), row(3, 900), row(0, 0), row(0, 0)]
    values, counts = tgen.reconstruct(rows, columns, 'dnsQuerySize', 'ixpN', 60, 2)
    assert values == [250, 0] and counts == [4, 0]  # Not mean(100, 300)=200.
    rates, _ = tgen.reconstruct(rows, columns, 'dnsQueryRate', 'ixpN', 37, 2)
    assert rates == [4 / 37, 0]
    with pytest.raises(ValueError, match='blocks'):
        tgen.reconstruct(rows[:3], columns, 'dnsQueryRate', 'ixpN', 37, 2)


def test_raw_rows_preserve_pairing(tmp_path):
    manifest = [dict(integer=True), dict(integer=False)]
    (tmp_path / 'dumps').mkdir()
    path = tmp_path / 'dumps' / 'all_dumps'
    path.write_text('3 0.2\n1 0.9\n')
    assert tgen.read_rows(tmp_path, 2, manifest) == [[3, .2], [1, .9]]
    for data in ('1\n2\n', '1 2\n', 'nan 0\n1 2\n', '1.5 0\n1 2\n', '-1 0\n1 2\n'):
        path.write_text(data)
        with pytest.raises(ValueError):
            tgen.read_rows(tmp_path, 2, manifest)


def test_comparison_modes_and_dependent_control():
    same = tgen.ks_equivalence([0] * 4, [0] * 4, delta=.05, alpha=.05)
    assert same['outcome'] == 'pass' and not same['reject_null']
    assert tgen.ks_equivalence([0] * 4, [0] * 4, delta=.05, alpha=.05, method='bound')['outcome'] == 'inconclusive'
    # Independent Bernoulli sums: probabilities 1/4, 1/2, 1/4. Replicating a
    # single realization creates probabilities 1/2, 0, 1/2 instead.
    independent = [0, 1, 1, 2] * 5000
    replicated = [0, 0, 2, 2] * 5000
    assert tgen.ks_equivalence(independent, independent, delta=.05, alpha=.05, method='bound')['outcome'] == 'pass'
    assert tgen.ks_equivalence(independent, replicated, delta=.05, alpha=.05, method='bound')['outcome'] == 'fail'
    result = tgen.ks_equivalence(independent, replicated, delta=.05, alpha=.05)
    assert result['outcome'] == 'fail' and result['reject_null']
    json.dumps(result, allow_nan=False)


def fake_runner(test, directory, run_cfg):
    """Emulate exactly the raw dump contract, including direct model features."""
    scenario = yaml.safe_load((directory / 'scenario.yaml').read_text())
    network = next(iter(scenario['tgen'].values()))['tgen_per_network']
    population = next(iter(network.values()))['quantity']
    duration = test.build_cfg.gen_args.run_time
    queries = parse_quatex((directory / 'test.quatex').read_text())
    assert len({q.to_name() for q in queries}) == len(queries)
    assert all(q.vantage == 'ixpN' and int(q.end) == duration for q in queries)
    values = []
    for q in queries:
        if q.feat.startswith('summary_'):
            values.append(population * (100 if 'size' in q.feat else 1))
        else:
            values.append(100 if tgen.RECIPES[q.feat].size else population / duration)
    (directory / 'dumps').mkdir()
    count = int(test.arg['nsims'].split('-')[0])
    (directory / 'dumps' / 'all_dumps').write_text((' '.join(map(str, values)) + '\n') * count)
    return {}  # Composition never relies on the runner's sorted result marginals.


@pytest.mark.parametrize('duration', [37, 120])
def test_shared_runs_reports_and_export(tmp_path, monkeypatch, duration):
    calls = []
    def run(*args):
        calls.append(args[0].arg)
        return fake_runner(*args)
    monkeypatch.setattr(tgen, 'run', run)
    config = replace(suite(), window_size=[duration], samples=4)
    cfg = RunConfig(tmp_path, None, results_dir=str(tmp_path / 'export'))
    report = tgen.run_suite(config, cfg, smoke=True)
    assert len(calls) == 12 and len(report['results']) == 18
    assert [c['nsims'] for c in calls] == ['8-8', '4-4'] * 6
    assert all(c['outcome'] == 'smoke-only' for c in report['results'].values())
    root = Path(report['report_path']).parent
    exported = tmp_path / 'export' / report['run_id']
    assert json.loads((exported / 'report.json').read_text()) == report
    plots = [c['plot_file'] for c in report['results'].values()]
    assert len(set(plots)) == 18
    for filename in plots:
        assert (root / filename).read_bytes().startswith(b'\x89PNG')
        assert (exported / filename).read_bytes() == (root / filename).read_bytes()
    for group in report['groups'].values():
        for arm in group['arms'].values():
            assert arm['generation']['run_time'] == duration
            assert (exported / arm['rows_file']).is_file()
    with pytest.raises(ValueError, match='override_run_time'):
        tgen.run_suite(config, replace(cfg, override_run_time=duration + 1))


def test_group_failure_and_unsupported_do_not_stop_suite(tmp_path, monkeypatch):
    config = suite()
    first = replace(config.experiments[0], features=['dnsQueryRate', 'tcpPktInterarrival'])
    config = replace(config, experiments=[first, config.experiments[2], config.experiments[3]],
                     samples=4, multiplicity='bonferroni')
    def run(test, *args):
        if test.name.startswith('ftp-'):
            raise RuntimeError('synthetic execution failure')
        return fake_runner(test, *args)
    monkeypatch.setattr(tgen, 'run', run)
    report = tgen.run_suite(config, RunConfig(tmp_path, None))
    assert report['family_size'] == 8  # Unsupported/error cases retain their alpha allocation.
    assert all(c['alpha'] == .05 / 8 for c in report['results'].values())
    outcomes = {c['feature']: c['outcome'] for c in report['results'].values() if c['tgen_type'] == 'dnsTgen'}
    assert outcomes == {'dnsQueryRate': 'pass', 'tcpPktInterarrival': 'unsupported'}
    assert all(c['outcome'] == 'error' for c in report['results'].values() if c['tgen_type'] == 'ftpTgen')
    assert all(c['outcome'] == 'pass' for c in report['results'].values() if c['tgen_type'] == 'minTgen')


def test_case_failure_and_inactivity_do_not_stop_other_features(tmp_path, monkeypatch):
    config = replace(suite(), experiments=[suite().experiments[0]], samples=4)
    def run(test, directory, cfg):
        fake_runner(test, directory, cfg)
        manifest = tgen.query_manifest(config.experiments, 60)
        path = directory / 'dumps' / 'all_dumps'
        rows = [[float(x) for x in line.split()] for line in path.read_text().splitlines()]
        for row in rows:
            for i, c in enumerate(manifest):
                if c['name'] == 'dnsQuerySize':
                    row[i] = 999  # Violates reconstruction; other query feature still works.
                if c['name'] in ('dnsRespSize', 'summary_countDNSResp', 'summary_sizeDNSResp'):
                    row[i] = 0
        path.write_text('\n'.join(' '.join(map(str, row)) for row in rows) + '\n')
    monkeypatch.setattr(tgen, 'run', run)
    report = tgen.run_suite(config, RunConfig(tmp_path, None))
    outcomes = {c['feature']: c['outcome'] for c in report['results'].values()}
    assert outcomes == {'dnsQueryRate': 'pass', 'dnsQuerySize': 'error', 'dnsRespSize': 'inactive'}


def test_entries_with_same_execution_inputs_share_arms(tmp_path, monkeypatch):
    config = suite()
    first = config.experiments[0]
    entries = [replace(first, features=['dnsQueryRate']), replace(first, id='dns-sizes', features=['dnsQuerySize'])]
    calls = []
    def run(*args):
        calls.append(args[0].name)
        return fake_runner(*args)
    monkeypatch.setattr(tgen, 'run', run)
    report = tgen.run_suite(replace(config, experiments=entries, samples=4), RunConfig(tmp_path, None))
    assert len(calls) == 2 and len(report['groups']) == 1 and len(report['results']) == 2


@pytest.mark.parametrize('alias,kind', [('dns', 'dnsTgen'), ('mastodon', 'masTgen'),
                                       ('ftp', 'ftpTgen'), ('minio', 'minTgen'),
                                       ('gorilla', 'gorTgen'), ('irc', 'ircTgen'),
                                       ('ftpTgen', 'ftpTgen')])
def test_cli_suite_selection(alias, kind):
    original = replace(suite(), multiplicity='bonferroni')
    selected = tgen.select_suite(original, tgen_type=alias, window_size=37)
    assert [e.tgen_type for e in selected.experiments] == [kind]
    assert selected.window_size == [37]
    assert selected.family_size == 3 and selected.effective_alpha == .05 / 3
    assert original.window_size == [60] and original.family_size == 18


def test_cli_selection_defaults_and_errors():
    config = suite()
    assert tgen.select_suite(config) == config
    for options in (dict(tgen_type='unknown'), dict(window_size=0), dict(window_size=-1)):
        with pytest.raises(ValueError):
            tgen.select_suite(config, **options)
    with pytest.raises(ValueError, match='No configured experiments'):
        tgen.select_suite(replace(config, experiments=[config.experiments[0]]), tgen_type='ftp')


def test_configured_windows_and_family():
    config = tgen.load_suite()
    assert config.window_size == [60, 120, 1000]
    assert config.family_size == 54
    assert replace(config, multiplicity='bonferroni').effective_alpha == .05 / 54
    names = [e.case_id(f, v, w) for e in config.experiments
             for f, v in e.cases() for w in config.window_size]
    assert len(set(names)) == 54
    selected = tgen.select_suite(config, tgen_type='mastodon')
    assert selected.family_size == 9 and selected.window_size == config.window_size
    assert tgen.select_suite(selected, window_size=120).family_size == 3


def test_multiple_windows_keep_artifacts_and_alpha_separate(tmp_path, monkeypatch):
    config = replace(suite(), experiments=[suite().experiments[0]],
                     window_size=[60, 120, 1000], samples=4, multiplicity='bonferroni')
    calls = []
    def run(test, directory, cfg):
        calls.append((test.name, test.build_cfg.gen_args.run_time))
        return fake_runner(test, directory, cfg)
    monkeypatch.setattr(tgen, 'run', run)
    cfg = RunConfig(tmp_path, None, results_dir=str(tmp_path / 'export'))
    report = tgen.run_suite(config, cfg)
    assert len(calls) == 6 and len({name for name, _ in calls}) == 6
    assert [w for _, w in calls] == [60, 60, 120, 120, 1000, 1000]
    assert report['family_size'] == 9 and len(report['results']) == 9
    assert report['experiment']['window_size'] == [60, 120, 1000]
    artifacts = []
    for case_id, case in report['results'].items():
        suffix = f"__w{case['window_size']}s"
        assert case_id.endswith(suffix) and case['name'].endswith(suffix)
        assert case['group_id'].endswith(suffix)
        assert case['outcome'] == 'pass'
        assert case['comparison']['alpha'] == .05 / 9
        artifacts.extend([case['samples_file'], case['plot_file']])
        if case['feature'] == 'dnsQueryRate':
            assert case['summaries']['joint']['mean'] == 2 / case['window_size']
    for group_id, group in report['groups'].items():
        w = group['window_size']
        assert group_id.endswith(f'__w{w}s')
        for arm in group['arms'].values():
            assert arm['generation']['run_time'] == w
            assert arm['scenario']['analysis_window_size'] == w
            artifacts.append(arm['rows_file'])
    assert len(set(artifacts)) == len(artifacts)
    exported = tmp_path / 'export' / report['run_id']
    assert all((exported / name).is_file() for name in artifacts)
    # A global run-time override cannot silently collapse a multi-window suite.
    with pytest.raises(ValueError, match='override_run_time'):
        tgen.run_suite(config, replace(cfg, override_run_time=60))


def test_window_failure_does_not_suppress_later_windows(tmp_path, monkeypatch):
    config = replace(suite(), experiments=[suite().experiments[0]],
                     window_size=[60, 120], samples=4)
    def run(test, *args):
        if test.build_cfg.gen_args.run_time == 60:
            raise RuntimeError('synthetic window failure')
        return fake_runner(test, *args)
    monkeypatch.setattr(tgen, 'run', run)
    report = tgen.run_suite(config, RunConfig(tmp_path, None))
    for case in report['results'].values():
        assert case['outcome'] == ('error' if case['window_size'] == 60 else 'pass')
