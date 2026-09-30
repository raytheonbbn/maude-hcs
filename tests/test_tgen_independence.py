"""Opt-in statistical experiment plus a small real-generator/SMC execution check."""
from dataclasses import replace
import json
import pytest

from .utils.tgen_independence import CONTEXT, Experiment, run_experiment


def experiment():
    return Experiment(**json.loads((CONTEXT / 'experiment.json').read_text()))


def test_dns_composition_smoke(pytestconfig):
    # Four composed samples are enough to exercise both arms, not to infer independence.
    report = run_experiment(replace(experiment(), samples=4), pytestconfig.run_cfg, smoke=True)
    if report['outcome'] == 'build-only':
        pytest.skip('Built both experiment arms')
    assert report['outcome'] == 'smoke-only'


def test_dns_observable_independence(pytestconfig):
    if not pytestconfig.getoption('--tgen-statistical'):
        pytest.skip('Enable the fixed-budget experiment with --tgen-statistical')
    cfg = experiment()
    samples = pytestconfig.getoption('--tgen-samples')
    if samples is not None:
        cfg = replace(cfg, samples=samples)
    report = run_experiment(cfg, pytestconfig.run_cfg)
    if report['outcome'] == 'build-only':
        pytest.skip('Built both experiment arms')
    assert report['outcome'] == 'pass', (
        f"DNS observable composition {report['outcome']}: {report['comparison']}; "
        f"report: {report['report_path']}"
    )
