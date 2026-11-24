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
DEFAULT_MAUDE_PATH = Path(os.environ.get(
    'TCP_MAUDE_PATH', Path(script_dir).parent / 'maude_hcs/lib/network/tcp.maude'))


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
        state_term = 'makeTcpState({}, {}, {}, {}, {}, {}, {})'.format(
            literal(state['cwnd'], 'cwnd'), literal(state['w_max'], 'w_max'),
            literal(state['t_since'], 't_since'),
            'true' if state['in_slow_start'] else 'false',
            literal(-1.0 if state['last_send_time'] is None else state['last_send_time'], 'last_send_time'),
            literal(-1.0 if state['last_ack_time'] is None else state['last_ack_time'], 'last_ack_time'),
            literal(-1.0 if state.get('quickacks_left') is None else state['quickacks_left'], 'quickacks_left'))
    def link(drop_p):
        return '(dropP: {}, oneWayDelay: {})'.format(
            literal(drop_p, 'drop_p'),
            literal(request['one_way_delay'], 'one_way_delay'))
    expression = 'tcpTimelineResult({}, {}, {}, {}, {}, {})'.format(
        request['num_bytes'], link(request['drop_p']),
        link(request.get('drop_p_l2', request['drop_p'])),
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
    expected = {'cwnd:_', 'wMax:_', 'tSince:_', 'inSS:_', 'lastSend:_', 'lastAck:_',
                'quickacksLeft:_'}
    if set(fields) != expected:
        raise RuntimeError(f'Expected seven TCP state fields; received {sorted(fields)}')
    quick = fields['quickacksLeft:_']
    if quick != -1.0 and (quick < 0.0 or not quick.is_integer()):
        raise RuntimeError(f'Invalid receiver QuickACK budget: {quick}')

    size_term = module.parseTerm('tcpDeliverySizes({}, ({}), ({}))'.format(
        request['num_bytes'], arguments[0], arguments[3]))
    if size_term is None:
        raise RuntimeError('Maude could not parse packet-size calculation')
    size_term.reduce()
    size_arguments = list(size_term.arguments())
    if str(size_term.symbol()).replace('`', '') != 'packetSizes' or len(size_arguments) != 2:
        raise RuntimeError(f'Packet sizes did not reduce to packetSizes: {size_term}')
    def sizes(node):
        return [int(str(value)) for value in flatten(node, '_::_', 'nilNatList')]
    return {
        'destination_times': times(arguments[0], 'destination arrival time'),
        'ixp_times': times(arguments[1], 'IXP arrival time'),
        'ack_ixp_times': times(arguments[2], 'IXP ACK arrival time'),
        'ack_sender_times': times(arguments[3], 'sender ACK arrival time'),
        'data_sizes': sizes(size_arguments[0]),
        'ack_sizes': sizes(size_arguments[1]),
        'state': {
            'cwnd': fields['cwnd:_'], 'w_max': fields['wMax:_'],
            't_since': fields['tSince:_'], 'in_slow_start': fields['inSS:_'],
            'last_send_time': None if fields['lastSend:_'] < 0.0 else fields['lastSend:_'],
            'last_ack_time': None if fields['lastAck:_'] < 0.0 else fields['lastAck:_'],
            'quickacks_left': None if quick < 0.0 else int(quick),
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


def get_maude_timeline(profile, num_bytes, is_new=True, state=None, *, start_time,
                       backend='auto', profile_l2=None, tcp_maude_path=None):
    """Return all four packet streams, wire sizes, and updated TcpState."""
    expected_count = _segment_count(num_bytes)
    if backend not in ('auto', 'binding', 'subprocess'):
        raise ValueError(f'Unknown Maude backend: {backend}')
    request = {
        'tcp_maude_path': str(DEFAULT_MAUDE_PATH if tcp_maude_path is None else tcp_maude_path),
        'num_bytes': int(num_bytes),
        'drop_p': _finite_float(tcp_analytical_model.resolve_profile(profile), 'drop probability'),
        'drop_p_l2': _finite_float(tcp_analytical_model.resolve_profile(
            profile if profile_l2 is None else profile_l2), 'link 2 drop probability'),
        'one_way_delay': 0.01, 'is_new': bool(is_new),
        'start_time': _finite_float(start_time, 'start_time'), 'state': None,
    }
    if state is not None:
        request['state'] = {name: getattr(state, name) for name in (
            'cwnd', 'w_max', 't_since', 'in_slow_start', 'last_send_time', 'last_ack_time',
            'quickacks_left')}
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
    result = dict(result)
    result['state'] = tcp_analytical_model.TcpState(**result['state'])
    return result


def get_maude_transfer(profile, num_bytes, is_new=True, state=None, *, start_time,
                       backend='auto', profile_l2=None, tcp_maude_path=None):
    """Return data-phase times/ACKs, excluding the new-connection handshakes."""
    result = get_maude_timeline(profile, num_bytes, is_new=is_new, state=state,
                               start_time=start_time, backend=backend,
                               profile_l2=profile_l2, tcp_maude_path=tcp_maude_path)
    return _data_phase(result, is_new)


# Arrival times are seconds; allow 1 ns absolute error plus small relative roundoff.
ABS_TOL = 1.0e-9
REL_TOL = 1.0e-9
STATE_FIELDS = (
    'cwnd', 'w_max', 't_since', 'in_slow_start',
    'last_send_time', 'last_ack_time',
    'quickacks_left',
)
MSS_BYTES = 1448


def _segment_count(num_bytes):
    if isinstance(num_bytes, bool) or not isinstance(num_bytes, int) or num_bytes <= 0:
        raise ValueError('num_bytes must be a positive integer')
    return (num_bytes + MSS_BYTES - 1) // MSS_BYTES


def get_python_timeline(profile, num_bytes, is_new=True, state=None, *, start_time,
                        profile_l2=None):
    num_segments = _segment_count(num_bytes)
    tcp_analytical_model.set_active_profile(profile, profile_l2)
    t_ixp, t_dest, ack_ixp, ack_sender, final_state = tcp_analytical_model.simulate_transfer(
        num_segments, is_new=is_new, state=state, start_time=start_time)
    data_sizes, ack_sizes = tcp_analytical_model.tcp_delivery_sizes(
        num_bytes, delivery_times=t_dest, ack_times=ack_sender, is_new=is_new)
    return dict(destination_times=list(t_dest), ixp_times=list(t_ixp),
                ack_ixp_times=list(ack_ixp), ack_sender_times=list(ack_sender),
                data_sizes=data_sizes, ack_sizes=ack_sizes, state=final_state)


def _data_phase(result, is_new):
    forward_skip, reverse_skip = (5, 4) if is_new else (0, 0)
    return (result['destination_times'][forward_skip:],
            result['ack_ixp_times'][reverse_skip:],
            result['ack_sender_times'][reverse_skip:], result['state'])


def get_python_transfer(profile, num_bytes, is_new=True, state=None, *, start_time,
                        profile_l2=None):
    """Return data-phase times/ACKs, excluding the new-connection handshakes."""
    return _data_phase(get_python_timeline(profile, num_bytes, is_new=is_new, state=state,
                                         start_time=start_time, profile_l2=profile_l2), is_new)


def _compare_transfer(py_times, py_state, md_times, md_state, *,
                      py_ack_ixp, py_ack_sender, md_ack_ixp, md_ack_sender,
                      expected_segments, label, is_new=False):
    expected_forward = expected_segments + (5 if is_new else 0)
    if len(py_times) != expected_forward or len(md_times) != expected_forward:
        raise ValueError(
            f'{label}: expected {expected_forward} data arrivals; '
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
        min_acks = 5 if is_new else 1
        max_acks = expected_segments + (4 if is_new else 0)
        if not min_acks <= len(py_acks) <= max_acks:
            raise ValueError(
                f'{label}: {location} ACK count must be between {min_acks} and '
                f'{max_acks}, got {len(py_acks)}')
        for index, (py_ack, md_ack) in enumerate(zip(py_acks, md_acks), start=1):
            if not math.isfinite(py_ack) or not math.isfinite(md_ack):
                raise ValueError(f'{label}: nonfinite {location} ACK arrival at ACK {index}')
            max_time_diff = max(max_time_diff, abs(py_ack - md_ack))
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
            equal = (field in ('last_send_time', 'last_ack_time', 'quickacks_left')
                     and py_value is None and md_value is None)
        elif field == 'quickacks_left':
            equal = (type(py_value) is int and type(md_value) is int
                     and py_value >= 0 and py_value == md_value)
        else:
            if not math.isfinite(py_value) or not math.isfinite(md_value):
                raise ValueError(f'{label}: nonfinite state field {field}')
            equal = math.isclose(py_value, md_value, rel_tol=REL_TOL, abs_tol=ABS_TOL)
        if not equal:
            raise ValueError(
                f'{label}: state field {field} differs: '
                f'Python={py_value!r}, Maude={md_value!r}')

    return max_time_diff


def compare_timelines(python, maude, *, num_bytes, is_new, label):
    """Check every packet timestamp/size and all seven retained state fields."""
    count = _segment_count(num_bytes)
    max_diff = _compare_transfer(
        python['destination_times'], python['state'],
        maude['destination_times'], maude['state'],
        py_ack_ixp=python['ack_ixp_times'], py_ack_sender=python['ack_sender_times'],
        md_ack_ixp=maude['ack_ixp_times'], md_ack_sender=maude['ack_sender_times'],
        expected_segments=count, label=label, is_new=is_new)
    if len(python['ixp_times']) != len(python['destination_times']) or len(maude['ixp_times']) != len(maude['destination_times']):
        raise ValueError(f'{label}: IXP forward packet count differs')
    for index, (py_time, md_time) in enumerate(zip(python['ixp_times'], maude['ixp_times']), 1):
        if not math.isfinite(py_time) or not math.isfinite(md_time):
            raise ValueError(f'{label}: nonfinite IXP forward arrival at packet {index}')
        max_diff = max(max_diff, abs(py_time - md_time))
        if not math.isclose(py_time, md_time, rel_tol=REL_TOL, abs_tol=ABS_TOL):
            raise ValueError(f'{label}: IXP forward packet {index} arrival differs: '
                             f'Python={py_time!r}, Maude={md_time!r}')
    for size_key, time_key in (('data_sizes', 'destination_times'),
                                ('ack_sizes', 'ack_sender_times')):
        if len(python[size_key]) != len(python[time_key]) or len(maude[size_key]) != len(maude[time_key]):
            raise ValueError(f'{label}: {size_key} count differs from packet timeline')
        if python[size_key] != maude[size_key]:
            raise ValueError(f'{label}: {size_key} differs between Python and Maude')
    return max_diff


def check_case(profile, num_bytes, *, is_new, start_time, state=None,
               maude_state=None, profile_l2=None, backend='auto', tcp_maude_path=None,
               label=None):
    """Run a parity check against the independent Maude implementation."""
    label = label or f'{profile}/{profile_l2 or profile}, {num_bytes} bytes'
    python = get_python_timeline(profile, num_bytes, is_new=is_new, state=state,
                                 start_time=start_time, profile_l2=profile_l2)
    maude = get_maude_timeline(profile, num_bytes, is_new=is_new,
                               state=state if maude_state is None else maude_state,
                               start_time=start_time, profile_l2=profile_l2,
                               backend=backend, tcp_maude_path=tcp_maude_path)
    max_diff = compare_timelines(python, maude, num_bytes=num_bytes,
                                 is_new=is_new, label=label)
    data_acks = len(python['ack_sender_times']) - (4 if is_new else 0)
    print(f'PASS {label}: {data_acks} data ACKs; max packet-time difference '
          f'{max_diff:.6e} s; all packet sizes and seven state fields agree')
    return python, maude


def check_edge_cases(*, backend='auto', tcp_maude_path=None):
    """Exercise retained budgets, receiver growth, idle restart, and two-hop loss."""
    options = dict(backend=backend, tcp_maude_path=tcp_maude_path)
    checked = 0
    for profile in ('none', 'good'):
        for size in (1, 1449, 11 * MSS_BYTES):
            check_case(profile, size, is_new=True, start_time=0.0,
                       label=f'{profile}, short new transfer ({size} bytes)', **options)
            checked += 1
        python, maude = check_case(profile, 3 * MSS_BYTES, is_new=True, start_time=0.0,
                                   label=f'{profile}, retained-budget initial transfer', **options)
        check_case(profile, 5 * MSS_BYTES, is_new=False, state=python['state'],
                   maude_state=maude['state'], start_time=python['state'].last_ack_time,
                   label=f'{profile}, retained-budget reused transfer', **options)
        checked += 2

    for start in (0.199999, 0.2, 0.200001, 0.400001):
        state = tcp_analytical_model.TcpState(
            80.0, 100.0, 1.0, in_slow_start=False,
            last_send_time=0.0, last_ack_time=0.04, quickacks_left=0)
        check_case('good', 5 * MSS_BYTES, is_new=False, state=state,
                   start_time=start, label=f'good, idle interval {start:.6f} s', **options)
        checked += 1
    state = tcp_analytical_model.TcpState(
        80.0, 100.0, 1.0, in_slow_start=False,
        last_send_time=0.0, last_ack_time=0.4, quickacks_left=0)
    check_case('good', 5 * MSS_BYTES, is_new=False, state=state, start_time=0.21,
               label='good, previous flight has not drained', **options)
    checked += 1
    legacy = tcp_analytical_model.TcpState(20.0, 30.0, 0.0, in_slow_start=True)
    check_case('none', 5 * MSS_BYTES, is_new=False, state=legacy, start_time=0.0,
               label='none, reused state with unspecified QuickACK budget', **options)
    checked += 1
    for first, second in (('excellent', 'good'), ('good', 'excellent')):
        check_case(first, 300 * MSS_BYTES, profile_l2=second, is_new=True, start_time=0.0,
                   label=f'{first}/{second}, asymmetric 300-segment transfer', **options)
        checked += 1
    return checked


def _plot_ack_panel(ax, python, maude, *, is_new, title):
    """Plot data-phase ACK packets by ordinal at both observation points."""
    reverse_skip = 4 if is_new else 0
    max_diff = 0.0
    for key, observation, color in (
            ('ack_ixp_times', 'IXP', 'tab:blue'),
            ('ack_sender_times', 'Sender', 'tab:orange')):
        py_acks = python[key][reverse_skip:]
        md_acks = maude[key][reverse_skip:]
        ax.plot(range(1, len(py_acks) + 1), py_acks,
                label=f'{observation}: Python', color=color, linewidth=3, alpha=0.4)
        ax.plot(range(1, len(md_acks) + 1), md_acks,
                label=f'{observation}: Maude', color=color, linewidth=1.5,
                linestyle='--', marker='x', markersize=3,
                markevery=max(1, len(md_acks) // 25))
        max_diff = max(max_diff, max(
            (abs(py_ack - md_ack) for py_ack, md_ack in zip(py_acks, md_acks)),
            default=0.0))
    py_count = len(python['ack_sender_times']) - reverse_skip
    md_count = len(maude['ack_sender_times']) - reverse_skip
    ax.set_title(title)
    ax.set_xlabel('Data ACK packet number')
    ax.set_ylabel('Expected ACK arrival time from transfer start (s)')
    ax.text(0.98, 0.03,
            f'Data ACKs: Python {py_count}, Maude {md_count}\n'
            f'Max ACK time difference: {max_diff:.2e} s',
            transform=ax.transAxes, ha='right', va='bottom', fontsize=9,
            bbox=dict(facecolor='white', alpha=0.85, edgecolor='none'))
    ax.legend(loc='upper left', fontsize=9)
    ax.grid(True)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Compare all Python/Maude packet times, sizes, ACK counts, and retained TCP state.')
    parser.add_argument('--maude-backend', choices=('auto', 'binding', 'subprocess'),
                        default='auto', help='Maude execution path (default: auto)')
    parser.add_argument('--tcp-maude-path', type=Path, default=DEFAULT_MAUDE_PATH,
                        help='Maude source path (default: repository network/tcp.maude)')
    parser.add_argument('--profiles', nargs='+', choices=tuple(tcp_analytical_model.PROFILES),
                        default=['none', 'excellent', 'good', 'fair'])
    parser.add_argument('--segments', type=int, default=300,
                        help='Segments per plotted new/reused transfer (default: 300)')
    parser.add_argument('--output', default=os.path.join(script_dir, 'results', 'maude_vs_python_comparison.png'),
                        help='Data-arrival plot path (default: results/maude_vs_python_comparison.png)')
    parser.add_argument('--ack-output', type=Path,
                        help='ACK plot path (default: alongside --output, with _acks appended)')
    args = parser.parse_args(argv)
    if args.segments <= 0:
        parser.error('--segments must be positive')
    output = Path(args.output)
    ack_output = (args.ack_output if args.ack_output is not None else
                  output.with_name(f'{output.stem}_acks{output.suffix}'))
    if output.resolve() == ack_output.resolve():
        parser.error('--output and --ack-output must name different files')
    from matplotlib.path import Path as MplPath
    # Workaround for Python 3.14 super() deepcopy recursion in matplotlib.
    MplPath.__deepcopy__ = lambda self, memo: MplPath(
        self.vertices.copy(), self.codes.copy() if self.codes is not None else None)
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(len(args.profiles), 2, figsize=(14, 4 * len(args.profiles)),
                              squeeze=False)
    ack_fig, ack_axes = plt.subplots(
        len(args.profiles), 2, figsize=(14, 4 * len(args.profiles)), squeeze=False)
    ack_fig.suptitle('Python vs Maude: data ACK arrival times (handshake ACKs omitted)',
                      fontsize=14)
    options = dict(backend=args.maude_backend, tcp_maude_path=args.tcp_maude_path)
    checked = 0
    try:
        for row, profile in enumerate(args.profiles):
            python = maude = None
            for col, is_new in enumerate((True, False)):
                transfer = 'New connection' if is_new else 'Reused connection'
                start_time = 0.0 if is_new else python['state'].last_ack_time
                label = f'{profile}, {transfer.lower()} ({args.segments} segments)'
                python, maude = check_case(
                    profile, args.segments * MSS_BYTES, is_new=is_new,
                    state=None if is_new else python['state'],
                    maude_state=None if is_new else maude['state'], start_time=start_time,
                    label=label, **options)
                checked += 1
                forward_skip = 5 if is_new else 0
                ax = axes[row, col]
                ax.plot(range(1, args.segments + 1), python['destination_times'][forward_skip:],
                        label='Python Analytical', linewidth=4, color='blue', alpha=0.5)
                ax.plot(range(1, args.segments + 1), maude['destination_times'][forward_skip:],
                        label='Maude Model', linewidth=2, color='red', linestyle='--')
                ax.set_title(f'{profile.capitalize()} - {transfer}')
                ax.set_xlabel('Data segment index (k)')
                ax.set_ylabel('Expected arrival time (s)')
                ax.legend()
                ax.grid(True)
                _plot_ack_panel(ack_axes[row, col], python, maude, is_new=is_new,
                                title=f'{profile.capitalize()} - {transfer}')
        checked += check_edge_cases(**options)
        fig.tight_layout()
        ack_fig.tight_layout(rect=(0, 0, 1, 0.97))
        output.parent.mkdir(parents=True, exist_ok=True)
        ack_output.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output, dpi=300)
        ack_fig.savefig(ack_output, dpi=300)
        print(f'\nAll {checked} transfer comparisons passed.')
        print(f'Data-arrival plot saved to {output}')
        print(f'ACK comparison plot saved to {ack_output}')
    finally:
        plt.close(fig)
        plt.close(ack_fig)


if __name__ == '__main__':
    main()
