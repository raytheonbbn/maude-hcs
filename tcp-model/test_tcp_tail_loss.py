"""Regression oracles for partial-flight TLP and delayed ACK timing."""

import importlib.util
import math
import unittest

import tcp_analytical_model as model


class TailLossModelTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(model.set_active_profile, 'fair')

    def assertTimes(self, actual, expected):
        self.assertEqual(len(actual), len(expected))
        for index, (value, target) in enumerate(zip(actual, expected)):
            with self.subTest(index=index):
                self.assertTrue(math.isclose(float(value), target,
                                             rel_tol=1e-10, abs_tol=1e-12),
                                (value, target))

    def test_single_segment_uses_single_segment_pto(self):
        model.set_active_profile(0.1, 0.0)
        ixp, destination, ack_ixp, ack_sender, state = model.simulate_transfer(
            1, is_new=True, start_time=0.0)
        # RTT=.04; PTO=max(2*RTT,1.5*RTT+.04)=.10.
        # Lost-tail recovery=.10+.9*.04+.1*.20=.156.
        # Data arrival=.08 setup+.02 propagation+.1*.156=.1156.
        self.assertTimes(ixp, [0.1056])
        self.assertTimes(destination, [0.1156])
        self.assertTimes(ack_ixp, [0.1656])
        self.assertTimes(ack_sender, [0.1756])
        self.assertAlmostEqual(state.last_ack_time, 0.1756, places=12)

    def test_two_segment_partial_flight_accounts_for_the_real_tail(self):
        model.set_active_profile(0.1, 0.0)
        _, destination, _, ack_sender, _ = model.simulate_transfer(
            2, is_new=True, start_time=0.0)
        # F=2: PTO=.08 and tail recovery=.136. For packet one,
        # its sole later packet survives with probability .9.
        self.assertTimes(destination, [0.10946, 0.113624224])
        self.assertTimes(ack_sender, [0.133624224])

    def test_final_partial_slow_start_flight_preserves_window_growth(self):
        model.set_active_profile(0.001, 0.0)
        _, first_flight, _, _, _ = model.simulate_transfer(
            10, is_new=True, start_time=0.0)
        # One full flight of ten is followed by a partial 20-packet window.
        # These final-packet oracles include the full first flight's .040528274...
        # recovery-weighted step, then F=1,2,3 tail-recovery probabilities.
        final_arrivals = {
            11: 0.1406684341943042,
            12: 0.1406726581943042,
            13: 0.1406968821943042,
        }
        ack_counts = {11: 6, 12: 6, 13: 7}
        for count, expected_last in final_arrivals.items():
            with self.subTest(segments=count):
                _, destination, _, ack_sender, state = model.simulate_transfer(
                    count, is_new=True, start_time=0.0)
                self.assertTimes(destination[:10], first_flight)
                self.assertAlmostEqual(float(destination[-1]), expected_last, places=12)
                self.assertEqual(len(ack_sender), ack_counts[count])
                self.assertEqual(state.cwnd, 40.0)
                self.assertTrue(state.in_slow_start)

    def test_reused_slow_start_keeps_its_congestion_window(self):
        model.set_active_profile(0.001, 0.0)
        before = model.TcpState(20.0, 30.0, 0.0, in_slow_start=True)
        original = vars(before).copy()
        _, destination, _, ack_sender, after = model.simulate_transfer(
            1, is_new=False, state=before, start_time=0.0)
        self.assertTimes(destination, [0.02014016])
        self.assertTimes(ack_sender, [0.08014016])
        self.assertEqual(after.cwnd, 40.0)
        self.assertEqual(vars(before), original)

    def test_reused_ca_uses_partial_flight_duration_for_cubic_time(self):
        model.set_active_profile(0.1, 0.0)
        before = model.TcpState(80.0, 120.0, 1.5, in_slow_start=False)
        _, destination, _, ack_sender, after = model.simulate_transfer(
            1, is_new=False, state=before, start_time=0.0)
        self.assertTimes(destination, [0.02])
        self.assertTimes(ack_sender, [0.08])
        # Actual one-packet flight duration=.9*.04+.1*.156=.0516.
        # Congestion-loss weighting still uses the 80-packet congestion window.
        self.assertAlmostEqual(after.t_since, (0.9 ** 80) * (1.5 + 0.0516), places=14)
        self.assertGreater(after.cwnd, 2.0)

    def test_full_flight_retains_its_existing_timing_and_state(self):
        model.set_active_profile(0.1, 0.0)
        _, destination, _, ack_sender, state = model.simulate_transfer(
            10, is_new=True, start_time=0.0)
        self.assertAlmostEqual(float(destination[0]), 0.1090000000046, places=12)
        self.assertAlmostEqual(float(destination[-1]), 0.113818016, places=12)
        self.assertAlmostEqual(float(ack_sender[-1]), 0.133818016, places=12)
        self.assertAlmostEqual(state.cwnd, 11.5328197213, places=10)
        self.assertAlmostEqual(state.w_max, 16.47545674471429, places=10)
        self.assertEqual(state.t_since, 0.0)
        self.assertFalse(state.in_slow_start)


@unittest.skipUnless(importlib.util.find_spec('maude') is not None,
                     'Maude Python binding is unavailable')
class TailLossMaudeTests(unittest.TestCase):
    assertTimes = TailLossModelTests.assertTimes

    def setUp(self):
        self.addCleanup(model.set_active_profile, 'fair')

    # Independently check Maude data plus both ACK lists for a symmetric path.
    def test_adapter_returns_correct_single_segment_data_and_acks(self):
        import plot_maude_vs_python as comparison

        python = comparison.get_python_transfer(0.1, 1448, start_time=0.0)
        maude = comparison.get_maude_transfer(0.1, 1448, start_time=0.0,
                                               backend='binding')
        # Each hop drops .1, so the end-to-end probability is .19.
        # Recovery=.10+.81*.04+.19*.20=.1704; arrival=.1+.19*.1704.
        for result in (python, maude):
            self.assertTimes(result[0], [0.132376])
            self.assertTimes(result[1], [0.182376])
            self.assertTimes(result[2], [0.192376])
            self.assertAlmostEqual(result[3].last_ack_time, 0.192376, places=12)

    def test_adapter_returns_one_cumulative_ack_for_two_segments(self):
        import plot_maude_vs_python as comparison

        for result in (
                comparison.get_python_transfer(0.1, 2896, start_time=0.0),
                comparison.get_maude_transfer(0.1, 2896, start_time=0.0,
                                               backend='binding')):
            self.assertTimes(result[0], [0.11928044, 0.128600224])
            self.assertTimes(result[1], [0.138600224])
            self.assertTimes(result[2], [0.148600224])


if __name__ == '__main__':
    unittest.main()
