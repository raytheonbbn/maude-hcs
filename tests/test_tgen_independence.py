"""Each observable gets a test result; a module fixture shares its model runs."""
from dataclasses import replace

import pytest

from .utils.tgen_independence import load_suite, run_suite, select_suite

CONFIG = load_suite()

def configured_suite(config):
    try:
        return select_suite(CONFIG, tgen_type=config.getoption('--tgen-type'),
                            window_size=config.getoption('--window_size'))
    except ValueError as exc:
        raise pytest.UsageError(str(exc)) from exc


def pytest_generate_tests(metafunc):
    if 'case_id' in metafunc.fixturenames:
        suite = configured_suite(metafunc.config)
        # Filter collection as well as execution; excluded types never run.
        names = [e.case_id(f, v) for e in suite.experiments for f, v in e.cases()]
        metafunc.parametrize('case_id', names, ids=names)


@pytest.fixture(scope='module')
def selected_suite(pytestconfig):
    return configured_suite(pytestconfig)


@pytest.fixture(scope='module')
def smoke_report(pytestconfig, selected_suite):
    # Selected source kinds execute once per arm, regardless of feature count.
    return run_suite(replace(selected_suite, samples=4), pytestconfig.run_cfg, smoke=True)


@pytest.fixture(scope='module')
def statistical_report(pytestconfig, selected_suite):
    if not pytestconfig.getoption('--tgen-statistical'):
        pytest.skip('Enable the fixed-budget suite with --tgen-statistical')
    samples = pytestconfig.getoption('--tgen-samples')
    cfg = selected_suite if samples is None else replace(selected_suite, samples=samples)
    return run_suite(cfg, pytestconfig.run_cfg)


def assert_case(report, case_id, expected):
    result = report['results'][case_id]
    if result['outcome'] == 'build-only':
        pytest.skip('Built both populations')
    assert result['outcome'] in expected, f"{case_id}: {result}; report: {report['report_path']}"


def test_composition_smoke(smoke_report, case_id):
    # Four joint runs can legitimately contain no packets. Keep that outcome
    # in the report; this test checks plumbing, not evidence of composition.
    assert_case(smoke_report, case_id, ('smoke-only', 'inactive'))


def test_composition_statistical(statistical_report, case_id):
    assert_case(statistical_report, case_id, ('pass',))


def test_composition_short_window(pytestconfig, selected_suite):
    # This fixed-duration DNS regression must not override a user's selection.
    if pytestconfig.getoption('--window_size') is not None:
        pytest.skip('Explicit window override; covered by the selected suite')
    if not any(e.tgen_type == 'dnsTgen' for e in selected_suite.experiments):
        pytest.skip('DNS not selected')
    config = replace(CONFIG, experiments=[CONFIG.experiments[0]], samples=4, window_size=30)
    report = run_suite(config, pytestconfig.run_cfg, smoke=True)
    for case_id in report['results']:
        assert_case(report, case_id, ('smoke-only',))
    assert report['experiment']['window_size'] == 30
