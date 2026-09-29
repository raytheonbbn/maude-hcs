"""Fast tests of the harness itself; no CP3 simulations or reference regeneration."""
import copy
import json
import logging
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from maude_hcs.parse_dump import parse_dump, parse_dump_rows
from .conftest import pytest_collection_modifyitems
from .runners.smc_runner import concat_dumps, smc_runner
from .runners.maude_runner import maude_runner
from .utils.comparison import compare_smc, validate_policy
from .utils.context import Context
from .utils.execution import execute
from .utils.provenance import tree_hash


def echo(value):
    return value


def fail():
    raise ValueError('intentional child failure')


def crash():
    os._exit(17)


def stall():
    time.sleep(30)


def test_worker_success():
    assert execute(echo, ({'answer': 42},), timeout=10) == {'answer': 42}


@pytest.mark.parametrize('target, error, message', [
    (fail, RuntimeError, 'intentional child failure'),
    (crash, RuntimeError, '17'),
    (stall, TimeoutError, 'exceeded'),
])
def test_worker_failure_is_bounded(target, error, message):
    with pytest.raises(error, match=message):
        execute(target, timeout=1.5 if target is stall else 10)


def test_dump_merge_preserves_rows_and_sources(tmp_path):
    (tmp_path/'dump-b').write_text('3 4\n')
    (tmp_path/'dump-a').write_text('1 2')
    (tmp_path/'dump-empty').write_text('')
    (tmp_path/'unrelated').write_text('not a dump')
    assert concat_dumps(tmp_path) == ['dump-a:1', 'dump-b:1']
    assert (tmp_path/'all_dumps').read_text() == '1 2\n3 4\n'
    assert concat_dumps(tmp_path) == ['dump-a:1', 'dump-b:1']
    assert (tmp_path/'dump-a').exists()


@pytest.mark.parametrize('text', ['', '\n'])
def test_empty_dump_rejected(tmp_path, text):
    (tmp_path/'dump').write_text(text)
    with pytest.raises(ValueError, match='no samples'):
        concat_dumps(tmp_path)


def test_joint_samples_and_legacy_marginals():
    text = '2 10\n1 20\n'
    assert parse_dump_rows(text, 2, 2) == [[2, 10], [1, 20]]
    assert parse_dump(text, 2, 2) == [[1, 2], [10, 20]]


@pytest.mark.parametrize('text, queries, runs', [
    ('', 1, 1), ('1 2\n3', 2, 2), ('1\n2', 1, 1),
    ('nan', 1, 1), ('inf', 1, 1), ('oops', 1, 1),
])
def test_invalid_samples_rejected(text, queries, runs):
    with pytest.raises(ValueError):
        parse_dump_rows(text, queries, runs)


@pytest.mark.parametrize('flag, selected', [('regression', 'test_regressions'), ('expected', 'test_expected')])
def test_selection_understands_parametrized_names(flag, selected):
    items = [SimpleNamespace(name=name+'[case]', originalname=name)
             for name in ('test_regressions', 'test_expected', 'test_other')]
    deselected = []
    config = SimpleNamespace(
        run_cfg=SimpleNamespace(regression=flag=='regression', expected=flag=='expected'),
        hook=SimpleNamespace(pytest_deselected=lambda items: deselected.extend(items)))
    pytest_collection_modifyitems(None, config, items)
    assert [item.originalname for item in items] == [selected]
    assert len(deselected) == 2


def result(samples):
    return dict(schema_version=2, provenance={'seed': 0}, query_order=['q'],
                results={'q': dict(query={'name': 'q'}, samples=samples, mean=0, stddev=0)},
                sample_rows=[[x] for x in samples], run_ids=[f'dump:{i}' for i in range(len(samples))])


def test_smoke_compares_values_and_pairing():
    a = result([1, 2])
    compare_smc(a, copy.deepcopy(a), {'mode': 'smoke'})
    b = copy.deepcopy(a)
    b['sample_rows'].reverse()
    with pytest.raises(AssertionError, match='Joint'):
        compare_smc(a, b, {'mode': 'smoke'})
    b = result([1, 3])
    with pytest.raises(AssertionError, match='q'):
        compare_smc(a, b, {'mode': 'smoke'})


@pytest.mark.parametrize('change', ['metadata', 'legacy', 'queries', 'empty', 'nan'])
def test_invalid_references_rejected(change):
    a, b = result([1]), result([1])
    if change == 'metadata': b['provenance']['seed'] = 2
    if change == 'legacy': b.pop('schema_version')
    if change == 'queries': b['results'] = {}
    if change == 'empty': b['results']['q']['samples'] = []
    if change == 'nan': b['results']['q']['samples'] = [float('nan')]
    with pytest.raises(AssertionError):
        compare_smc(a, b, {'mode': 'smoke'})


def test_distribution_requires_evidence_of_equivalence():
    policy = dict(mode='distribution', delta=.05, alpha=.05, min_samples=100)
    compare_smc(result([1]*10000), result([1]*10000), policy)
    # Identical tiny samples do not establish equivalence, even with KS=0.
    with pytest.raises(AssertionError, match='equivalence not established'):
        compare_smc(result([1]*100), result([1]*100), policy)
    with pytest.raises(AssertionError, match='equivalence not established'):
        compare_smc(result([1]*10000), result([2]*10000), policy)
    with pytest.raises(AssertionError, match='Too few'):
        compare_smc(result([1]), result([1]), policy)


@pytest.mark.parametrize('policy', [None, {}, {'mode':'unknown'}, {'mode':'smoke','delta':.5},
                                     {'mode':'distribution','delta':.05,'alpha':.05}])
def test_comparison_policy_is_explicit(policy):
    with pytest.raises(ValueError):
        validate_policy(policy)


def test_unknown_build_option_rejected(tmp_path):
    (tmp_path/'build_cfgs').mkdir()
    (tmp_path/'build_cfgs'/'bad.json').write_text(json.dumps({
        'gen_args': {'typo': True}, 'markov_v1_dirs': [], 'markov_v2_dirs': []}))
    with pytest.raises(ValueError, match='unsupported generation arguments'):
        Context('bad', tmp_path).get_test_cfgs()


def test_fingerprint_normalizes_build_paths(tmp_path):
    a, b = tmp_path/'a', tmp_path/'b'
    a.mkdir(); b.mkdir()
    for p in (a, b):
        (p/'model.maude').write_text(f'sload {p}/actor.maude')
    assert tree_hash(a, [(a, '<BUILD>')]) == tree_hash(b, [(b, '<BUILD>')])
    (b/'model.maude').write_text('changed')
    assert tree_hash(a, [(a, '<BUILD>')]) != tree_hash(b, [(b, '<BUILD>')])


def test_correctness_evaluates_final_config(tmp_path):
    (tmp_path/'test-env.maude').write_text('''mod TEST-ENV is
      protecting BOOL .
      sort Config .
      ops initConfig done : -> Config .
      rl initConfig => done .
    endm''')
    cfg = SimpleNamespace(arg={'initial':'initConfig', 'predicate':'FINAL:Config == done'}, expected='true')
    assert execute(maude_runner, (cfg, tmp_path, None, logging.getLogger('test')), timeout=10) == 'true'


def test_unparseable_predicate_fails(tmp_path):
    (tmp_path/'test-env.maude').write_text('mod TEST-ENV is protecting BOOL . endm')
    cfg = SimpleNamespace(arg='nonexistent-symbol', expected='true')
    with pytest.raises(RuntimeError, match='Unable to parse'):
        execute(maude_runner, (cfg, tmp_path, None, logging.getLogger('test')), timeout=10)


def test_query_ids_include_client_and_vantage():
    from maude_hcs.query import Query, IntegrityQuery, ConfidentialityQuery, parse_quatex
    queries = [Query('cumulative', 'integrity', 0, 30),
               IntegrityQuery('cumulative', 'integrity', 0, 30, 'client1'),
               IntegrityQuery('cumulative', 'integrity', 0, 30, 'client2'),
               ConfidentialityQuery('cumulative', 'detection', 0, 30, 'v1'),
               ConfidentialityQuery('cumulative', 'detection', 0, 30, 'v2')]
    assert len({q.to_name() for q in queries}) == len(queries)
    assert parse_quatex('\n  \n') == []


def test_smc_runner_keeps_joint_samples(tmp_path, monkeypatch):
    import importlib
    from .utils.context import GenArgs
    module = importlib.import_module('tests.runners.smc_runner')
    (tmp_path/'test-run.maude').write_text('')
    (tmp_path/'test.quatex').write_text('eval E[1]; // cumulative latency0 0 30\neval E[2]; // cumulative goodput 0 30\n')
    cfg = SimpleNamespace(arg={'nsims':'2-2','jobs':2}, comparison={'mode':'smoke'},
                          build_cfg=SimpleNamespace(gen_args=GenArgs('test.yaml', 30)))
    monkeypatch.setattr(module.maude, 'init', lambda: None)
    monkeypatch.setattr(module, 'provenance', lambda *args: {'seed': 0})
    def capture(args):
        prefix = Path(args.dump)
        prefix.with_name('dump-0').write_text('1 20\n')
        prefix.with_name('dump-1').write_text('2 10\n')
        return json.dumps({'nsims':2,'queries':[{'line':1,'mean':1.5,'std':.5},
                                               {'line':2,'mean':15,'std':5}]}), ''
    monkeypatch.setattr(module, 'capture_scheck', capture)
    result = smc_runner(cfg, tmp_path, None, logging.getLogger('test'))
    assert result['sample_rows'] == [[1, 20], [2, 10]]
    assert result['run_ids'] == ['dump-0:1', 'dump-1:1']
    assert len(result['results']) == 2
    assert result['results']['cumulative:goodput:t0_t30']['samples'] == [10,20]


def test_duplicate_queries_fail_before_simulation(tmp_path, monkeypatch):
    import importlib
    module = importlib.import_module('tests.runners.smc_runner')
    (tmp_path/'test-run.maude').write_text('')
    (tmp_path/'test.quatex').write_text('eval E[1]; // cumulative q 0 30\n'*2)
    monkeypatch.setattr(module.maude, 'init', lambda: None)
    monkeypatch.setattr(module, 'capture_scheck', lambda args: pytest.fail('must not simulate'))
    with pytest.raises(ValueError, match='duplicate'):
        smc_runner(SimpleNamespace(arg={}), tmp_path, None, logging.getLogger('test'))


def test_missing_or_legacy_reference_requires_explicit_regeneration(tmp_path):
    from .utils.comparison import check_reference
    path = tmp_path/'reference.json'
    with pytest.raises(AssertionError, match='Missing reference'):
        check_reference(path)
    assert not path.exists()
    path.write_text('{"results":{}}')
    with pytest.raises(AssertionError, match='Legacy'):
        check_reference(path, smc=True)
    check_reference(path, smc=True, regenerate=True)
    assert path.read_text() == '{"results":{}}'


def native_error():
    os.write(2, b'Warning: unable to locate file: missing.maude\n')
    return 'true'


def test_native_load_errors_cannot_pass(tmp_path):
    with pytest.raises(RuntimeError, match='Maude diagnostic'):
        execute(native_error, timeout=10, log_dir=tmp_path)
    assert 'missing.maude' in (tmp_path/'stderr.log').read_text()


def spawn_descendant(marker):
    import subprocess
    import sys
    code = '''import signal, sys, time
from pathlib import Path
p = Path(sys.argv[1])
def stop(*args):
    p.write_text('terminated')
    sys.exit(0)
signal.signal(signal.SIGTERM, stop)
p.with_suffix('.ready').write_text('ready')
time.sleep(30)
'''
    subprocess.Popen([sys.executable, '-c', code, str(marker)])
    time.sleep(30)


@pytest.mark.skipif(os.name != 'posix', reason='POSIX process-group cleanup')
def test_timeout_terminates_smc_descendants(tmp_path):
    marker = tmp_path/'child'
    with pytest.raises(TimeoutError):
        execute(spawn_descendant, (marker,), timeout=3)
    assert marker.with_suffix('.ready').exists(), 'child did not start'
    assert marker.read_text() == 'terminated'


def test_baseline_runner_uses_generated_duration_filename(tmp_path, monkeypatch):
    import importlib
    from .utils.context import GenArgs
    module = importlib.import_module('tests.runners.smc_runner')
    (tmp_path/'test-baseline-60.maude').write_text('')
    (tmp_path/'test.quatex').write_text('eval E[1]; // cumulative q 0 30\n')
    monkeypatch.setattr(module.maude, 'init', lambda: None)
    def capture(args):
        assert Path(args.test).name == 'test-baseline-60.maude'
        raise RuntimeError('selected baseline input')
    monkeypatch.setattr(module, 'capture_scheck', capture)
    cfg = SimpleNamespace(arg={'baseline':True},
                          build_cfg=SimpleNamespace(gen_args=GenArgs('test.yaml', 60, baseline_time=60)))
    with pytest.raises(RuntimeError, match='selected baseline input'):
        smc_runner(cfg, tmp_path, None, logging.getLogger('test'))
