"""Real Maude literals, stuck states and parallel-run error propagation."""
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import json
import subprocess
import sys

import maude
import pytest

from .runners.smc_validation import CheckedSimulator, InvalidSimulation, validated_simulations
from .utils import tgen_independence as tgen
from .utils.context import RunConfig


@pytest.fixture
def literal_simulator(tmp_path):
    maude.input('''mod SMC-VALIDATION-TEST is
      protecting FLOAT . protecting BOOL .
      sort Config . op done : -> Config . op run : Config Float -> Config .
      op unresolved : Config -> Float .
    endm''')
    module = maude.getModule('SMC-VALIDATION-TEST')
    simulator = SimpleNamespace(module=module, state=module.parseTerm('done'),
                                restart=lambda: None)
    return CheckedSimulator(simulator, tmp_path, 105)


@pytest.mark.parametrize('expression,expected', [('0.0', 0.0), ('2.5', 2.5),
                                                ('1.0 + 2.0', 3.0), ('true', 1.0), ('false', 0.0)])
def test_reduced_literals_are_valid(literal_simulator, expression, expected):
    assert literal_simulator.rval(expression) == expected
    assert not literal_simulator.failed


def test_symbolic_float_is_an_error(literal_simulator, tmp_path):
    assert float(literal_simulator.module.parseTerm('unresolved(done)')) == 0.0
    with pytest.raises(InvalidSimulation):
        literal_simulator.rval('unresolved(C:Config)')
    assert literal_simulator.failed
    error = json.loads(next(tmp_path.glob('smc-error-*.json')).read_text())
    assert error['query'] == 'unresolved(C:Config)' and error['seed'] == 105
    assert Path(error['state_file']).read_text() == 'done'


def test_stuck_run_detected_even_for_constant_observation(literal_simulator):
    literal_simulator.simulator.state = literal_simulator.module.parseTerm('run(done, 60.0)')
    with pytest.raises(InvalidSimulation, match='unresolved run'):
        literal_simulator.restart()
    assert literal_simulator.failed
    with pytest.raises(InvalidSimulation):
        literal_simulator.rval('0.0')


@pytest.mark.parametrize('kind,server', [('masTgen', 'masNetSrv'), ('minTgen', 's3NetSrv')])
def test_missing_server_is_error_and_repaired_model_is_active(tmp_path, monkeypatch, kind, server):
    suite = tgen.load_suite()
    entry = next(e for e in suite.experiments if e.tgen_type == kind)
    suite = replace(suite, experiments=[entry], samples=4, window_size=[60])
    original = tgen.prepare_arm
    def missing_server(*args, **kwargs):
        test, directory, scenario = original(*args, **kwargs)
        path = directory / 'test.maude'
        path.write_text(path.read_text().replace(f'    {server}\n', ''))
        # Exercise parallel error handling: an exception in a worker must not hang.
        return replace(test, arg={**test.arg, 'jobs': 2}), directory, scenario
    monkeypatch.setattr(tgen, 'prepare_arm', missing_server)
    broken = tgen.run_suite(suite, RunConfig(tmp_path, None))
    assert all(c['outcome'] == 'error' for c in broken['results'].values())
    assert all('unresolved run' in c['reason'] for c in broken['results'].values())
    errors = [e for arm in broken['groups'][f'{entry.id}__w60s']['arms'].values()
              for e in arm.get('validation_errors', [])]
    assert errors
    assert all((Path(broken['report_path']).parent / e['state_file']).is_file() for e in errors)
    monkeypatch.setattr(tgen, 'prepare_arm', original)
    repaired = tgen.run_suite(suite, RunConfig(tmp_path, None), smoke=True)
    for case in repaired['results'].values():
        assert case['outcome'] in ('smoke-only', 'inactive'), case
    # Tiny random batches may legitimately be empty. Separately pin the model's
    # counter and random seed to exercise a complete request/response exchange.
    directory = repaired['groups'][f'{entry.id}__w60s']['arms']['single']['build']
    checked = subprocess.run([sys.executable, '-c', '''
import maude, sys
maude.init(randomSeed=0)
assert maude.load(sys.argv[1] + '/test-run.maude')
m = maude.getCurrentModule()
state = m.parseTerm('run({0.0 | nil} initState(205), 60.0)')
state.rewrite()
assert str(state.symbol()) != 'run'
query = m.parseTerm('float(countTCPPkt(ixpN, getTsPL(getAdversary(C:Config)), 0.0, 60.0))')
value = maude.Substitution({m.parseTerm('C:Config'): state}).instantiate(query)
value.reduce()
assert float(value) > 6, str(value)
''', directory], capture_output=True, text=True, timeout=30)
    assert checked.returncode == 0, checked.stderr


@pytest.mark.parametrize('kind,channel,actor', [('masTgen', 'mastodon', 'masNetSrv'),
                                               ('minTgen', 'skyhook', 's3NetSrv')])
@pytest.mark.parametrize('clients,tgens', [(0, True), (1, False), (2, False), (1, True), (2, True)])
def test_shared_server_population(kind, channel, actor, clients, tgens):
    """One transport per application server, including mixed and multi-client models."""
    from maude_hcs.generate_cp3 import parse_scenario_yaml, generate_all_tgen_instances, gen_addresses_file, gen_main_file
    from maude_hcs.lib import GLOBALS
    scenario = GLOBALS.TOP_LEVEL_DIR / 'use-cases/challenge-problem-3/cp3_scenarios/scenario1/pwnd_cp3_scenario_1.yaml'
    duration, _, networks, net_ids, short, loss, nodes, profiles, definitions, models = parse_scenario_yaml(scenario)
    nodes = [(ch, net, clients, profs) for ch, net, _, profs in nodes if ch == channel] if clients else []
    instances = generate_all_tgen_instances({kind: definitions[kind]}, net_ids, short) if tgens else []
    _, ids = gen_addresses_file(nodes, instances, net_ids, 'test', False)
    generated = gen_main_file(instances, networks, loss, profiles, duration, models,
                              ids, nodes, 'test', net_ids, 0, 0, ['ixpN'])
    initial = generated.split('eq initState(j) =', 1)[1].split('rCtr(', 1)[0]
    assert initial.split().count(actor) == 1
    assert not any(token.startswith('skyCl') and token.endswith('NetSrv') for token in initial.split())


@pytest.mark.parametrize('channel', ['mastodon', 'skyhook'])
def test_existing_hcs_fixture_completes_short_smc(tmp_path, channel):
    """Exercise the existing multi-client HCS models with a bounded duration."""
    from .utils.context import Context, TestRunner
    context = Context('isolated_channel', Path(__file__).parent / 'contexts/isolated_channel')
    original = next(t for t in context.get_test_cfgs()
                    if t.runner == TestRunner.SMC and t.name == f'isolated_{channel}_smc')
    cfg = replace(original.build_cfg, gen_args=replace(original.build_cfg.gen_args,
                  run_time=60, hcs_delay=0, tgen_delay=0))
    run_cfg = RunConfig(tmp_path, None)
    directory = tgen.build(cfg, run_cfg, context.directory)
    suite = tgen.load_suite()
    manifest = tgen.query_manifest([suite.experiments[1]], 60)
    # Reuse the performance-mode observation adapter: removes the unused
    # baseline timer and records TCP without changing HCS application behavior.
    tgen.install_observation(directory, manifest, 60)
    test = replace(original, build_cfg=cfg, arg={'nsims': '1-1', 'jobs': 1, 'seed': 205})
    tgen.run(test, directory, run_cfg)
    rows = tgen.read_rows(directory, 1, manifest)
    for feature in suite.experiments[1].features:
        tgen.check_direct(rows, manifest, feature, 'ixpN', 60)
    _, counts = tgen.reconstruct(rows, manifest, 'tcpPktSize', 'ixpN', 60)
    assert counts[0] > 0


def test_sample_boundary_propagates_failure_without_stranding_workers(literal_simulator, tmp_path, monkeypatch):
    import umaudemc.statistical as statistical
    calls = []
    def sample(*args):
        calls.append(1)
        literal_simulator.rval('unresolved(C:Config)')
        pytest.fail('A failed observation must abort the sample')
    monkeypatch.setattr(statistical, 'run', sample)
    with pytest.raises(ValueError, match='Invalid SMC arm'):
        with validated_simulations(tmp_path, 105):
            assert statistical.run(None, [None], literal_simulator) == [0.0]
            assert statistical.run(None, [None], literal_simulator) == [0.0]
    assert len(calls) == 1
    assert statistical.run is sample  # Scoped hooks restored on failure.
