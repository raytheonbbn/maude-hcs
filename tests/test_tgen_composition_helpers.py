"""Validate composition plumbing independently of expensive Maude simulations."""
from dataclasses import replace
import json

import pytest

from .utils import tgen_independence as dns
from .utils.context import RunConfig


def experiment():
    return dns.Experiment(**json.loads((dns.CONTEXT / 'experiment.json').read_text()))


def test_pairing_and_rounding():
    # Sorted pairing and doubling one sample both give a different distribution.
    assert dns.compose_rates([1, 4, 2, 3]) == [5, 5]
    assert dns.compose_rates([1 / 60, 5 / 60]) == [6 / 60]


@pytest.mark.parametrize('samples', [[], [1], [-1, 1], [float('nan'), 1], [float('inf'), 1], [.001, 1]])
def test_invalid_composition(samples):
    with pytest.raises(ValueError):
        dns.compose_rates(samples)


def test_distance_outcomes():
    compare = lambda x, y: dns.ks_equivalence(x, y, delta=.05, alpha=.05)['outcome']
    assert compare([0] * 4, [0] * 4) == 'inconclusive'
    assert compare([0] * 5000, [0] * 5000) == 'pass'
    assert compare([0] * 5000, [1] * 5000) == 'fail'


@pytest.mark.parametrize('changes', [dict(feature='dnsQuerySize'), dict(samples=1),
                                     dict(joint_seed=105), dict(window_size=30)])
def test_unsupported_experiment(changes):
    with pytest.raises(ValueError):
        replace(experiment(), **changes)


def test_raw_dump_keeps_run_order_and_zeros(tmp_path):
    (tmp_path / 'dumps').mkdir()
    dump = tmp_path / 'dumps' / 'all_dumps'
    dump.write_text('1\n0\n4\n2\n')
    assert dns.read_rates(tmp_path, 4) == [1, 0, 4, 2]
    for data in ('0\n0\n0\n0\n', '1\n', '1 2\n' * 4, 'nan\n' * 4):
        dump.write_text(data)
        with pytest.raises(ValueError):
            dns.read_rates(tmp_path, 4)


def test_guarded_observer_adapter(tmp_path):
    path = tmp_path / 'test.maude'
    path.write_text('mkAdversaryCp3(advAddr, false)\n'
                    '(to baseLineAddr from baseLineAddr : initKs)\nother actors\n')
    dns.install_observation(tmp_path)
    assert path.read_text() == 'mkAdversaryCp3(advAddr, true)\nother actors\n'
    with pytest.raises(ValueError):
        dns.install_observation(tmp_path)


def test_orchestration_uses_framework_and_exports_report(tmp_path, monkeypatch):
    calls = []

    def fake_run(test, directory, cfg):
        calls.append(test.arg)
        (directory / 'dumps').mkdir()
        # Emulate the existing runner's raw dump; no dependency on its sorted output.
        samples = int(test.arg['nsims'].split('-')[0])
        (directory / 'dumps' / 'all_dumps').write_text('1\n' * samples)
        return {'results': {}}

    monkeypatch.setattr(dns, 'run', fake_run)
    cfg = RunConfig(tmp_path, None, results_dir=str(tmp_path / 'results'))
    report = dns.run_experiment(replace(experiment(), samples=4), cfg, smoke=True)
    assert [call['nsims'] for call in calls] == ['8-8', '4-4']
    assert [call['seed'] for call in calls] == [105, 106]
    assert all(call['jobs'] == 1 for call in calls)
    assert report['composed_samples'] == [2] * 4
    assert report['outcome'] == 'smoke-only'
    saved = list((tmp_path / 'results').glob('*.json'))
    assert len(saved) == 1 and json.loads(saved[0].read_text()) == report

    with pytest.raises(ValueError, match='60-second'):
        dns.run_experiment(experiment(), replace(cfg, override_run_time=30))


def test_runner_failure_preserves_error_report(tmp_path, monkeypatch):
    def fail(*args):
        raise RuntimeError('simulation failed')

    monkeypatch.setattr(dns, 'run', fail)
    cfg = RunConfig(tmp_path, None, results_dir=str(tmp_path / 'results'))
    with pytest.raises(RuntimeError, match='simulation failed'):
        dns.run_experiment(replace(experiment(), samples=4), cfg)
    reports = list((tmp_path / 'results').glob('*.json'))
    assert len(reports) == 1
    report = json.loads(reports[0].read_text())
    assert report['outcome'] == 'error'
    assert report['error'] == 'simulation failed'
    assert report['arms']['single']['generation']['tgen_delay'] == 0
