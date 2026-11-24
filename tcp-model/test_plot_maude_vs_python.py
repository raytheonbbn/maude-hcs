"""Focused validation for the Python/Maude transfer comparison.

Run with: python -m unittest discover -s tcp-model -p test_plot_maude_vs_python.py
"""
import importlib.util
import math
import unittest
from unittest import mock

import plot_maude_vs_python as comparison


class ComparisonChecks(unittest.TestCase):
    def state(self, **changes):
        values = dict(cwnd=20.0, w_max=30.0, t_since=0.1,
                      in_slow_start=True, last_send_time=1.0, last_ack_time=1.04)
        values.update(changes)
        return comparison.tcp_analytical_model.TcpState(**values)

    def compare(self, py_times=None, md_times=None, py_state=None, md_state=None,
                py_ack_ixp=None, py_ack_sender=None, md_ack_ixp=None, md_ack_sender=None,
                expected_segments=1):
        return comparison._compare_transfer(
            [0.1] if py_times is None else py_times,
            self.state() if py_state is None else py_state,
            [0.1] if md_times is None else md_times,
            self.state() if md_state is None else md_state,
            py_ack_ixp=[0.11] if py_ack_ixp is None else py_ack_ixp,
            py_ack_sender=[0.12] if py_ack_sender is None else py_ack_sender,
            md_ack_ixp=[0.11] if md_ack_ixp is None else md_ack_ixp,
            md_ack_sender=[0.12] if md_ack_sender is None else md_ack_sender,
            expected_segments=expected_segments, label='test transfer')

    def test_packet_counts_are_checked_before_zip(self):
        for py_times, md_times in (([0.1], [0.1, 0.2]), ([], []), ([0.1, 0.2], [0.1, 0.2])):
            with self.subTest(py_times=py_times, md_times=md_times):
                with self.assertRaisesRegex(ValueError, 'expected 1 data arrivals'):
                    self.compare(py_times=py_times, md_times=md_times)

    def test_ack_counts_are_checked_even_when_the_last_ack_matches(self):
        for location in ('ixp', 'sender'):
            arguments = dict(py_times=[0.1, 0.2], md_times=[0.1, 0.2],
                             py_ack_ixp=[0.21, 0.22], md_ack_ixp=[0.21, 0.22],
                             py_ack_sender=[0.23, 0.24], md_ack_sender=[0.23, 0.24],
                             expected_segments=2)
            arguments[f'md_ack_{location}'] = arguments[f'md_ack_{location}'][1:]
            with self.subTest(location=location):
                with self.assertRaisesRegex(ValueError, 'ACK count differs'):
                    self.compare(**arguments)

    def test_each_ack_timestamp_is_compared_even_when_the_last_ack_matches(self):
        for location in ('ixp', 'sender'):
            arguments = dict(py_times=[0.1, 0.2, 0.3], md_times=[0.1, 0.2, 0.3],
                             py_ack_ixp=[0.11, 0.21, 0.31], md_ack_ixp=[0.11, 0.21, 0.31],
                             py_ack_sender=[0.12, 0.22, 0.32], md_ack_sender=[0.12, 0.22, 0.32],
                             expected_segments=3)
            arguments[f'md_ack_{location}'][1] += 0.001
            with self.subTest(location=location):
                with self.assertRaisesRegex(ValueError, 'ACK 2 arrival differs'):
                    self.compare(**arguments)

    def test_nonfinite_ack_timestamps_are_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            for side in ('py', 'md'):
                for location in ('ixp', 'sender'):
                    with self.subTest(value=value, side=side, location=location):
                        with self.assertRaisesRegex(ValueError, 'nonfinite .* ACK arrival'):
                            self.compare(**{f'{side}_ack_{location}': [value]})

    def test_empty_or_excess_ack_lists_are_rejected(self):
        for timestamps in ([], [0.11, 0.12]):
            with self.subTest(timestamps=timestamps):
                with self.assertRaisesRegex(ValueError, 'ACK count must be between 1 and 1'):
                    self.compare(py_ack_ixp=timestamps, md_ack_ixp=timestamps,
                                 py_ack_sender=timestamps, md_ack_sender=timestamps)

    def test_ixp_and_sender_ack_counts_must_match_within_each_model(self):
        with self.assertRaisesRegex(ValueError, 'Python IXP/sender ACK counts differ'):
            self.compare(py_times=[0.1, 0.2], md_times=[0.1, 0.2], expected_segments=2,
                         py_ack_ixp=[0.21], md_ack_ixp=[0.21],
                         py_ack_sender=[0.22, 0.23], md_ack_sender=[0.22, 0.23])

    def test_ack_tolerance_accepts_only_roundoff(self):
        self.compare(md_ack_ixp=[0.11 + 1e-12], md_ack_sender=[0.12 + 1e-12])
        for location in ('ixp', 'sender'):
            with self.subTest(location=location):
                with self.assertRaisesRegex(ValueError, 'ACK 1 arrival differs'):
                    self.compare(**{f'md_ack_{location}': [0.121]})

    def test_every_state_field_is_compared(self):
        for field, value in dict(cwnd=21.0, w_max=31.0, t_since=0.2,
                                 in_slow_start=False, last_send_time=1.1, last_ack_time=1.14).items():
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, field):
                    self.compare(md_state=self.state(**{field: value}))

    def test_tolerance_accepts_roundoff_and_rejects_real_difference(self):
        self.compare(md_times=[0.1 + 1e-12], md_state=self.state(cwnd=20.0 + 1e-12))
        with self.assertRaisesRegex(ValueError, 'segment 1 arrival differs'):
            self.compare(md_times=[0.101])

    def test_nonfinite_arrivals_and_state_are_rejected(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, 'nonfinite arrival'):
                    self.compare(py_times=[value], md_times=[value])
                for field in ('cwnd', 'w_max', 't_since', 'last_send_time', 'last_ack_time'):
                    with self.subTest(field=field):
                        with self.assertRaisesRegex(ValueError, 'nonfinite state'):
                            self.compare(py_state=self.state(**{field: value}),
                                         md_state=self.state(**{field: value}))

    def test_optional_timestamps_are_not_confused_with_zero(self):
        self.compare(py_state=self.state(last_send_time=None, last_ack_time=None),
                     md_state=self.state(last_send_time=None, last_ack_time=None))
        for field in ('last_send_time', 'last_ack_time'):
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, field):
                    self.compare(py_state=self.state(**{field: None}),
                                 md_state=self.state(**{field: 0.0}))

    def test_byte_counts_use_ceiling_division_and_reject_invalid_inputs(self):
        for size, expected in ((1, 1), (1448, 1), (1449, 2)):
            self.assertEqual(comparison._segment_count(size), expected)
        for value in (0, -1, 1.5, True):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, 'positive integer'):
                    comparison._segment_count(value)


class AdapterChecks(unittest.TestCase):
    def test_handshake_entries_are_removed_only_for_new_connections(self):
        state = dict(cwnd=20.0, w_max=30.0, t_since=0.1, in_slow_start=True,
                     last_send_time=1.0, last_ack_time=1.04)
        for is_new, count in ((True, 40), (False, 80)):
            raw = list(range(count + (5 if is_new else 0)))
            ixp_acks = [0.1 + i * 0.01 for i in range(count // 2)]
            sender_acks = [value + 0.01 for value in ixp_acks]
            result = dict(destination_times=raw, ixp_times=raw,
                          ack_ixp_times=ixp_acks, ack_sender_times=sender_acks, state=state)
            with self.subTest(is_new=is_new):
                with mock.patch.object(comparison.importlib.util, 'find_spec', return_value=object()), \
                     mock.patch.object(comparison, '_evaluate_maude_transfer', return_value=result):
                    times, returned_ixp_acks, returned_sender_acks, returned_state = comparison.get_maude_transfer(
                        'none', count * 1448, is_new=is_new, start_time=0.0, backend='binding')
                    self.assertEqual(times, raw[5:] if is_new else raw)
                    self.assertEqual(returned_ixp_acks, ixp_acks)
                    self.assertEqual(returned_sender_acks, sender_acks)
                    self.assertEqual(returned_state.last_ack_time, 1.04)
        result = dict(destination_times=[0.1] * 40, ixp_times=[0.1] * 40, state=state)
        with mock.patch.object(comparison.importlib.util, 'find_spec', return_value=object()), \
             mock.patch.object(comparison, '_evaluate_maude_transfer', return_value=result):
            with self.assertRaisesRegex(RuntimeError, 'expected 45 entries'):
                comparison.get_maude_transfer('none', 57920, start_time=0.0, backend='binding')

    def test_subprocess_errors_and_missing_or_invalid_results_are_reported(self):
        marker = comparison._MAUDE_RESULT_MARKER
        cases = (
            (2, '', 'parse failed', 'subprocess failed'),
            (0, 'no result', '', 'exactly one JSON result'),
            (0, marker + '{}\n' + marker + '{}', '', 'exactly one JSON result'),
            (0, marker + '{invalid', '', 'invalid result JSON'),
        )
        for code, stdout, stderr, message in cases:
            with self.subTest(message=message, code=code):
                completed = comparison.subprocess.CompletedProcess([], code, stdout, stderr)
                with mock.patch.object(comparison.importlib.util, 'find_spec', return_value=object()), \
                     mock.patch.object(comparison.subprocess, 'run', return_value=completed):
                    with self.assertRaisesRegex(RuntimeError, message):
                        comparison._run_maude_subprocess({})

    def test_unparsed_or_unreduced_maude_results_are_rejected(self):
        request = dict(tcp_maude_path='/unused/tcp.maude', num_bytes=1448,
                       drop_p=0.0, one_way_delay=0.01, is_new=True,
                       state=None, start_time=0.0)
        unresolved = mock.Mock()
        unresolved.arguments.return_value = []
        unresolved.symbol.return_value = 'tcpTimelineResult'
        for term, message in ((None, 'could not parse transfer'),
                              (unresolved, 'did not reduce to tlR')):
            with self.subTest(message=message):
                fake_maude = mock.Mock()
                fake_maude.load.return_value = True
                fake_maude.getModule.return_value.parseTerm.return_value = term
                with mock.patch.dict(comparison.sys.modules, {'maude': fake_maude}), \
                     mock.patch.object(comparison, '_MAUDE_SOURCE_PATH', None):
                    with self.assertRaisesRegex(RuntimeError, message):
                        comparison._evaluate_maude_transfer(request)

    def test_calculation_errors_do_not_silently_select_another_backend(self):
        with mock.patch.object(comparison.importlib.util, 'find_spec', return_value=object()), \
             mock.patch.object(comparison, '_evaluate_maude_transfer', side_effect=RuntimeError('bad result')), \
             mock.patch.object(comparison, '_run_maude_subprocess') as fallback:
            with self.assertRaisesRegex(RuntimeError, 'bad result'):
                comparison.get_maude_transfer('none', 1448, start_time=0.0)
            fallback.assert_not_called()


@unittest.skipUnless(importlib.util.find_spec('maude'), 'Maude Python binding required')
class RealTransferChecks(unittest.TestCase):
    def test_new_and_reused_transfers_through_both_backends(self):
        for backend in ('binding', 'subprocess'):
            for profile in ('none', 'fair'):
                py_state = md_state = None
                for is_new, size in ((True, 57920), (False, 115840)):
                    with self.subTest(backend=backend, profile=profile, is_new=is_new):
                        py_start = 0.0 if is_new else py_state.last_ack_time
                        md_start = 0.0 if is_new else md_state.last_ack_time
                        py_times, py_ack_ixp, py_ack_sender, py_state = comparison.get_python_transfer(
                            profile, size, is_new=is_new, state=py_state, start_time=py_start)
                        md_times, md_ack_ixp, md_ack_sender, md_state = comparison.get_maude_transfer(
                            profile, size, is_new=is_new, state=md_state, start_time=md_start,
                            backend=backend)
                        comparison._compare_transfer(
                            py_times, py_state, md_times, md_state,
                            py_ack_ixp=py_ack_ixp, py_ack_sender=py_ack_sender,
                            md_ack_ixp=md_ack_ixp, md_ack_sender=md_ack_sender,
                            expected_segments=comparison._segment_count(size), label='real transfer')

    def test_small_and_odd_transfers_have_matching_ack_counts_and_times(self):
        # Explicit small examples; ACK counts are not generally ceil(segments / 2)
        # when interarrival gaps can trigger the delayed ACK timer.
        cases = ((1, 1), (1448, 1), (1449, 1), (3 * 1448, 2), (11 * 1448, 6))
        for backend in ('binding', 'subprocess'):
            for size, expected_acks in cases:
                py_state = md_state = None
                for is_new in (True, False):
                    with self.subTest(backend=backend, size=size, is_new=is_new):
                        py_start = 0.0 if is_new else py_state.last_ack_time
                        md_start = 0.0 if is_new else md_state.last_ack_time
                        py_times, py_ack_ixp, py_ack_sender, py_state = comparison.get_python_transfer(
                            'none', size, is_new=is_new, state=py_state, start_time=py_start)
                        md_times, md_ack_ixp, md_ack_sender, md_state = comparison.get_maude_transfer(
                            'none', size, is_new=is_new, state=md_state, start_time=md_start,
                            backend=backend)
                        self.assertEqual(len(py_ack_sender), expected_acks)
                        self.assertEqual(len(md_ack_sender), expected_acks)
                        comparison._compare_transfer(
                            py_times, py_state, md_times, md_state,
                            py_ack_ixp=py_ack_ixp, py_ack_sender=py_ack_sender,
                            md_ack_ixp=md_ack_ixp, md_ack_sender=md_ack_sender,
                            expected_segments=comparison._segment_count(size), label='small/odd transfer')


if __name__ == '__main__':
    unittest.main()
