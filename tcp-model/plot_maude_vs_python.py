import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)
import tcp_analytical_model


_MAUDE_SOURCE_PATH = None
_MAUDE_RESULT_MARKER = 'MAUDE_RESULT_JSON:'


def _finite_float(value, label):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{label} is not a number: {value!r}') from exc
    if not math.isfinite(number):
        raise ValueError(f'{label} must be finite, got {value!r}')
    return number


def _evaluate_maude_transfer(request):
    """Evaluate and decode one transfer; shared by both Python execution paths."""
    import maude

    global _MAUDE_SOURCE_PATH
    source = str(Path(request['tcp_maude_path']).resolve())
    if _MAUDE_SOURCE_PATH != source:
        maude.init()  # Returns False when another caller already initialized it.
        if not maude.load(source):
            raise RuntimeError(f'Maude could not load {source}')
        _MAUDE_SOURCE_PATH = source
    module = maude.getModule('TCP-ANALYTICAL-MODEL')
    if module is None:
        raise RuntimeError('Maude module TCP-ANALYTICAL-MODEL is unavailable')

    def literal(value, label):
        return repr(_finite_float(value, label))

    state = request['state']
    state_term = 'initTcpState'
    if state is not None:
        state_term = 'makeTcpState({}, {}, {}, {}, {}, {})'.format(
            literal(state['cwnd'], 'cwnd'), literal(state['w_max'], 'w_max'),
            literal(state['t_since'], 't_since'),
            'true' if state['in_slow_start'] else 'false',
            literal(-1.0 if state['last_send_time'] is None else state['last_send_time'], 'last_send_time'),
            literal(-1.0 if state['last_ack_time'] is None else state['last_ack_time'], 'last_ack_time'))
    link = '(dropP: {}, oneWayDelay: {})'.format(
        literal(request['drop_p'], 'drop_p'),
        literal(request['one_way_delay'], 'one_way_delay'))
    expression = 'tcpTimelineResult({}, {}, {}, {}, {}, {})'.format(
        request['num_bytes'], link, link,
        'true' if request['is_new'] else 'false', state_term,
        literal(request['start_time'], 'start_time'))
    term = module.parseTerm(expression)
    if term is None:
        raise RuntimeError(f'Maude could not parse transfer: {expression}')
    term.reduce()
    arguments = list(term.arguments())
    if str(term.symbol()) != 'tlR' or len(arguments) != 5:
        raise RuntimeError(
            f'Transfer did not reduce to tlR(destination, ixp, ack_ixp, ack_sender, state): {term}')

    def flatten(node, operator, identity):
        symbol = str(node.symbol()).replace('`', '')
        if symbol == identity:
            return []
        if symbol == operator:
            return [leaf for child in node.arguments()
                    for leaf in flatten(child, operator, identity)]
        return [node]

    def times(node, label):
        return [_finite_float(str(value), label)
                for value in flatten(node, '_::_', 'nilFloatList')]

    fields = {}
    for attribute in flatten(arguments[4], '_,_', 'noneAS'):
        name = str(attribute.symbol())
        values = list(attribute.arguments())
        if name in fields or len(values) != 1:
            raise RuntimeError(f'Malformed TCP state attribute: {attribute}')
        if name == 'inSS:_':
            if str(values[0]) not in ('true', 'false'):
                raise RuntimeError(f'Unreduced slow-start state: {values[0]}')
            fields[name] = str(values[0]) == 'true'
        else:
            fields[name] = _finite_float(str(values[0]), name)
    expected = {'cwnd:_', 'wMax:_', 'tSince:_', 'inSS:_', 'lastSend:_', 'lastAck:_'}
    if set(fields) != expected:
        raise RuntimeError(f'Expected six TCP state fields; received {sorted(fields)}')
    return {
        'destination_times': times(arguments[0], 'destination arrival time'),
        'ixp_times': times(arguments[1], 'IXP arrival time'),
        'ack_ixp_times': times(arguments[2], 'IXP ACK arrival time'),
        'ack_sender_times': times(arguments[3], 'sender ACK arrival time'),
        'state': {
            'cwnd': fields['cwnd:_'], 'w_max': fields['wMax:_'],
            't_since': fields['tSince:_'], 'in_slow_start': fields['inSS:_'],
            'last_send_time': None if fields['lastSend:_'] < 0.0 else fields['lastSend:_'],
            'last_ack_time': None if fields['lastAck:_'] < 0.0 else fields['lastAck:_'],
        },
    }


def _run_maude_subprocess(request):
    binding_available = importlib.util.find_spec('maude') is not None
    # Reload this script without running main(), so both paths share decoding.
    worker = (
        'import json, runpy, sys; '
        'scope = runpy.run_path(sys.argv[1], run_name="_maude_worker"); '
        'value = scope["_evaluate_maude_transfer"](json.loads(sys.argv[2])); '
        f'print({_MAUDE_RESULT_MARKER!r} + json.dumps(value, allow_nan=False))')
    if binding_available:
        command = [sys.executable]
    else:
        conda = shutil.which('conda')
        if conda is None:
            raise RuntimeError('Maude is unavailable: no Python binding or conda executable')
        command = [conda, 'run', '-n', 'maude-hcs', 'python3']
    command += ['-c', worker, os.path.abspath(__file__),
                json.dumps(request, allow_nan=False)]
    completed = subprocess.run(command, text=True, capture_output=True, timeout=120)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f'Maude subprocess failed ({completed.returncode}): {detail}')
    payloads = [line[len(_MAUDE_RESULT_MARKER):] for line in completed.stdout.splitlines()
                if line.startswith(_MAUDE_RESULT_MARKER)]
    if len(payloads) != 1:
        raise RuntimeError('Maude subprocess did not return exactly one JSON result')
    try:
        return json.loads(payloads[0])
    except json.JSONDecodeError as exc:
        raise RuntimeError('Maude subprocess returned invalid result JSON') from exc


def get_maude_transfer(profile, num_bytes, is_new=True, state=None, *, start_time,
                       backend='auto'):
    """Return destination data times, IXP/sender ACK times, and updated TcpState."""
    expected_count = _segment_count(num_bytes)
    if backend not in ('auto', 'binding', 'subprocess'):
        raise ValueError(f'Unknown Maude backend: {backend}')
    request = {
        'tcp_maude_path': str(Path(script_dir).parent / 'maude_hcs/lib/network/tcp.maude'),
        'num_bytes': int(num_bytes),
        'drop_p': _finite_float(tcp_analytical_model.resolve_profile(profile), 'drop probability'),
        'one_way_delay': 0.01, 'is_new': bool(is_new),
        'start_time': _finite_float(start_time, 'start_time'), 'state': None,
    }
    if state is not None:
        request['state'] = {name: getattr(state, name) for name in (
            'cwnd', 'w_max', 't_since', 'in_slow_start', 'last_send_time', 'last_ack_time')}
    binding_available = importlib.util.find_spec('maude') is not None
    if backend == 'binding' and not binding_available:
        raise RuntimeError('The selected Python interpreter cannot import maude')
    if backend == 'binding' or (backend == 'auto' and binding_available):
        result = _evaluate_maude_transfer(request)
    else:
        result = _run_maude_subprocess(request)
    expected_full_count = expected_count + (5 if is_new else 0)
    for key in ('destination_times', 'ixp_times'):
        if len(result[key]) != expected_full_count:
            raise RuntimeError(f'{key}: expected {expected_full_count} entries, got {len(result[key])}')
    times = result['destination_times'][5:] if is_new else result['destination_times']
    return (times, result['ack_ixp_times'], result['ack_sender_times'],
            tcp_analytical_model.TcpState(**result['state']))


# Arrival times are seconds; allow 1 ns absolute error plus small relative roundoff.
ABS_TOL = 1.0e-9
REL_TOL = 1.0e-9
STATE_FIELDS = (
    'cwnd', 'w_max', 't_since', 'in_slow_start',
    'last_send_time', 'last_ack_time',
)
MSS_BYTES = 1448


def _segment_count(num_bytes):
    if isinstance(num_bytes, bool) or not isinstance(num_bytes, int) or num_bytes <= 0:
        raise ValueError('num_bytes must be a positive integer')
    return (num_bytes + MSS_BYTES - 1) // MSS_BYTES


def get_python_transfer(profile, num_bytes, is_new=True, state=None, *, start_time):
    num_segments = _segment_count(num_bytes)
    tcp_analytical_model.set_active_profile(profile)
    _, t_dest, ack_ixp, ack_sender, final_state = tcp_analytical_model.simulate_transfer(
        num_segments, is_new=is_new, state=state, start_time=start_time)
    return list(t_dest), list(ack_ixp), list(ack_sender), final_state


def _compare_transfer(py_times, py_state, md_times, md_state, *,
                      py_ack_ixp, py_ack_sender, md_ack_ixp, md_ack_sender,
                      expected_segments, label):
    if len(py_times) != expected_segments or len(md_times) != expected_segments:
        raise ValueError(
            f'{label}: expected {expected_segments} data arrivals; '
            f'Python returned {len(py_times)}, Maude returned {len(md_times)}')

    max_time_diff = 0.0
    for index, (py_time, md_time) in enumerate(zip(py_times, md_times), start=1):
        if not math.isfinite(py_time) or not math.isfinite(md_time):
            raise ValueError(f'{label}: nonfinite arrival time at segment {index}')
        max_time_diff = max(max_time_diff, abs(py_time - md_time))
        if not math.isclose(py_time, md_time, rel_tol=REL_TOL, abs_tol=ABS_TOL):
            raise ValueError(
                f'{label}: segment {index} arrival differs: '
                f'Python={py_time!r}, Maude={md_time!r}')

    for location, py_acks, md_acks in (
            ('IXP', py_ack_ixp, md_ack_ixp),
            ('sender', py_ack_sender, md_ack_sender)):
        if len(py_acks) != len(md_acks):
            raise ValueError(
                f'{label}: {location} ACK count differs: '
                f'Python={len(py_acks)}, Maude={len(md_acks)}')
        if not 1 <= len(py_acks) <= expected_segments:
            raise ValueError(
                f'{label}: {location} ACK count must be between 1 and '
                f'{expected_segments}, got {len(py_acks)}')
        for index, (py_ack, md_ack) in enumerate(zip(py_acks, md_acks), start=1):
            if not math.isfinite(py_ack) or not math.isfinite(md_ack):
                raise ValueError(f'{label}: nonfinite {location} ACK arrival at ACK {index}')
            if not math.isclose(py_ack, md_ack, rel_tol=REL_TOL, abs_tol=ABS_TOL):
                raise ValueError(
                    f'{label}: {location} ACK {index} arrival differs: '
                    f'Python={py_ack!r}, Maude={md_ack!r}')
    for model, ixp_acks, sender_acks in (
            ('Python', py_ack_ixp, py_ack_sender),
            ('Maude', md_ack_ixp, md_ack_sender)):
        if len(ixp_acks) != len(sender_acks):
            raise ValueError(f'{label}: {model} IXP/sender ACK counts differ')

    for field in STATE_FIELDS:
        py_value = getattr(py_state, field)
        md_value = getattr(md_state, field)
        if field == 'in_slow_start':
            equal = type(py_value) is bool and type(md_value) is bool and py_value == md_value
        elif py_value is None or md_value is None:
            equal = (field in ('last_send_time', 'last_ack_time')
                     and py_value is None and md_value is None)
        else:
            if not math.isfinite(py_value) or not math.isfinite(md_value):
                raise ValueError(f'{label}: nonfinite state field {field}')
            equal = math.isclose(py_value, md_value, rel_tol=REL_TOL, abs_tol=ABS_TOL)
        if not equal:
            raise ValueError(
                f'{label}: state field {field} differs: '
                f'Python={py_value!r}, Maude={md_value!r}')

    return max_time_diff


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Compare Python and Maude data/ACK arrival times, ACK counts, and TCP state.')
    parser.add_argument('--maude-backend', choices=('auto', 'binding', 'subprocess'),
                        default='auto', help='Maude execution path (default: auto)')
    parser.add_argument('--output', default=os.path.join(script_dir, 'maude_vs_python_comparison.png'),
                        help='Output plot path')
    args = parser.parse_args(argv)
    profiles = [('none', 'None Profile (Buffer Capacity Path)'),
                ('fair', 'Fair Profile (No-Buffer Path)')]
    from matplotlib.path import Path as MplPath
    # Workaround for Python 3.14 super() deepcopy recursion in matplotlib.
    MplPath.__deepcopy__ = lambda self, memo: MplPath(
        self.vertices.copy(), self.codes.copy() if self.codes is not None else None)
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    try:
        for row, (profile, description) in enumerate(profiles):
            print(f'\nTesting {description}')
            py_state = md_state = None
            for col, (is_new, num_bytes) in enumerate(((True, 57920), (False, 115840))):
                count = _segment_count(num_bytes)
                transfer = 'New connection' if is_new else 'Reused connection'
                label = f'{profile}, transfer {col + 1} ({transfer}, {count} segments)'
                py_start = 0.0 if is_new else py_state.last_ack_time
                md_start = 0.0 if is_new else md_state.last_ack_time
                if py_start is None or md_start is None:
                    raise ValueError(f'{label}: previous transfer did not return an ACK time')
                py_times, py_ack_ixp, py_ack_sender, py_state = get_python_transfer(
                    profile, num_bytes, is_new=is_new, state=py_state, start_time=py_start)
                md_times, md_ack_ixp, md_ack_sender, md_state = get_maude_transfer(
                    profile, num_bytes, is_new=is_new, state=md_state, start_time=md_start,
                    backend=args.maude_backend)
                max_diff = _compare_transfer(
                    py_times, py_state, md_times, md_state,
                    py_ack_ixp=py_ack_ixp, py_ack_sender=py_ack_sender,
                    md_ack_ixp=md_ack_ixp, md_ack_sender=md_ack_sender,
                    expected_segments=count, label=label)
                print(f'PASS {label}: max arrival difference {max_diff:.6e} s; '
                      f'{len(py_ack_sender)} ACKs and all ACK arrival times agree; '
                      'all six TCP state fields agree')
                print(f'  Python final state: {py_state}')
                print(f'  Maude  final state: {md_state}')

                ax = axes[row, col]
                ax.plot(range(1, count + 1), py_times, label='Python Analytical',
                        linewidth=4, color='blue' if is_new else 'green', alpha=0.5)
                ax.plot(range(1, count + 1), md_times, label='Maude Model',
                        linewidth=2, color='red' if is_new else 'purple', linestyle='--')
                ax.set_title(f'{profile.capitalize()} - Transfer {col + 1} ({transfer})')
                ax.set_xlabel('Segment index (k)')
                ax.set_ylabel('Expected arrival time (s)')
                ax.legend()
                ax.grid(True)

        fig.tight_layout()
        fig.savefig(args.output, dpi=300)
        print(f'\nAll four transfer comparisons passed. Plot saved to {args.output}')
    finally:
        plt.close(fig)


if __name__ == '__main__':
    main()
