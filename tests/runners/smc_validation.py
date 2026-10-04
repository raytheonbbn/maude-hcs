"""Validate observations before Maude's permissive float conversion loses errors."""
from contextlib import contextmanager
from pathlib import Path
from fractions import Fraction
from unittest.mock import patch
import importlib
import json
import math
import os
import re

import maude
from umaudemc.simulators import parse_hole_term


class InvalidSimulation(ValueError):
    """Caught at the sample boundary so worker queues/barriers stay intact."""


class CheckedSimulator:
    """Wrap the existing simulator; preserve its sampling and random seed behavior."""

    def __init__(self, simulator, directory, seed):
        self.simulator = simulator
        self.directory = Path(directory)
        self.seed = seed
        self.sample = 0
        self.cache = {}
        self.failed = False

    def __getattr__(self, name):
        return getattr(self.simulator, name)

    def record_error(self, reason, observation=None, term=None):
        if not self.failed:
            # Each forked worker writes its own first failure, without contention.
            stem = f'smc-error-{os.getpid()}'
            state_path = self.directory / f'{stem}.maude.txt'
            state_path.write_text(str(self.simulator.state))
            details = dict(reason=reason, seed=self.seed, worker_pid=os.getpid(),
                           worker_sample=self.sample, query=observation,
                           term=str(term) if term is not None else None,
                           state_file=str(state_path))
            (self.directory / f'{stem}.json').write_text(json.dumps(details, indent=2))
        self.failed = True
        raise InvalidSimulation(reason)

    def check_state(self):
        state = self.simulator.state
        if str(state.symbol()) == 'run':
            self.record_error('Simulation stuck in unresolved run(...)')

    def restart(self):
        self.simulator.restart()
        self.sample += 1
        self.check_state()

    def next_step(self):
        self.simulator.next_step()
        self.check_state()

    def rval(self, observation):
        try:
            return self.evaluate(observation)
        except InvalidSimulation:
            raise
        except Exception as exc:
            return self.record_error(f'Observation evaluation failed: {exc}', observation)

    def evaluate(self, observation):
        if self.failed:
            raise InvalidSimulation('A previous sample failed validation')
        if observation == 'steps':
            return float(self.simulator.step)
        if observation == 'time' and hasattr(self.simulator, 'getTimeOp'):
            term = self.simulator.getTimeOp(self.state)
        elif observation == 'time':
            value = self.simulator.get_time()
            return value if math.isfinite(value) else self.record_error('Nonfinite observation', observation)
        elif not isinstance(observation, str):
            # PMaude also supports numeric val(index, state) observations.
            term = self.simulator.val(self.module.parseTerm(str(int(observation))), self.state)
        else:
            if observation not in self.cache:
                self.cache[observation] = parse_hole_term(self.module, observation)
            template, var = self.cache[observation]
            if template is None:
                return self.record_error('Unparseable observation', observation)
            term = (maude.Substitution({var: self.state}).instantiate(template)
                    if var is not None else template.copy())
        term.reduce()
        literal = str(term)
        # A symbolic term can have sort Float and still convert to 0.0 in Python.
        # Require a reduced literal, not just a numeric sort or successful float().
        if literal in ('true', 'false'):
            return float(literal == 'true')
        if re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', literal):
            value = float(literal)
            if math.isfinite(value):
                return value
        if re.fullmatch(r'-?\d+/[1-9]\d*', literal):
            value = float(Fraction(literal))
            if math.isfinite(value):
                return value
        return self.record_error('Observation did not reduce to a finite numeric/Boolean literal', observation, term)


@contextmanager
def validated_simulations(directory, seed):
    """Install a scoped adapter inherited by umaudemc's forked workers."""
    command = importlib.import_module('umaudemc.command.scheck')
    statistical = importlib.import_module('umaudemc.statistical')
    original = command.get_simulator
    original_run = statistical.run
    def factory(*args, **kwargs):
        simulator = original(*args, **kwargs)
        return CheckedSimulator(simulator, directory, seed) if simulator else simulator
    def run_sample(program, qdata, simulator):
        # A worker exception would strand umaudemc's parent queue/barrier. Catch
        # validation failures around the WHOLE QuaTEx sample, including recursive
        # queries, and finish the worker protocol with disposable placeholders.
        # The parent below rejects the entire arm before any dump is accepted.
        if isinstance(simulator, CheckedSimulator) and simulator.failed:
            return [0.0] * len(qdata)
        try:
            return original_run(program, qdata, simulator)
        except InvalidSimulation:
            return [0.0] * len(qdata)
    with patch.object(command, 'get_simulator', factory), patch.object(statistical, 'run', run_sample):
        yield
    errors = sorted(Path(directory).glob('smc-error-*.json'))
    if errors:
        detail = json.loads(errors[0].read_text())
        raise ValueError(f"Invalid SMC arm {directory}: {detail['reason']}; "
                         f"seed={seed}, worker sample={detail['worker_sample']}, "
                         f"query={detail['query']}; state={detail['state_file']}")
