import numpy as np

# ==============================================================================
# TCP Analytical Model over Two Cascaded Bidirectional IID Loss Links
# ==============================================================================
#
# Computes E[T_k]: expected arrival time of the k-th TCP data segment and its
# corresponding TCP ACK at:
#   1. IXP intermediate node: times_ixp, ack_times_ixp
#   2. Final destination server / sender: times_dest, ack_times_sender
# measured from the client's first SYN transmission across two links.
#
# Models TCP as implemented in Ubuntu 22.04 (Linux 5.15+):
#   - CUBIC congestion control (default)
#   - SACK (Selective Acknowledgment)
#   - RACK-TLP (Recent ACK / Tail Loss Probe, RFC 8985) loss detection
#   - Linux Delayed ACKs (every 2nd full-sized segment, plus delayed ACK timer)
#   - Slow Start and Congestion Avoidance
#   - Independent and Identically Distributed (IID) packet loss channel
# ==============================================================================

PROFILES = {
    "none":      0.0,
    "excellent": 0.001,   # 0.1% loss
    "good":      0.005,   # 0.5% loss
    "fair":      0.010,   # 1.0% loss
    "poor":      0.030,   # 3.0% loss
    "bad":       0.050,   # 5.0% loss
}


def resolve_profile(p):
    """Resolves a profile specification (string, float, or dict) to a drop probability float."""
    if isinstance(p, (int, float)):
        return float(np.clip(p, 0.0, 1.0))
    if isinstance(p, str):
        if p in PROFILES:
            return PROFILES[p]
        try:
            return float(np.clip(float(p), 0.0, 1.0))
        except ValueError:
            pass
    if isinstance(p, dict):
        if "dropP" in p:
            return float(np.clip(p["dropP"], 0.0, 1.0))
        if "drop_p" in p:
            return float(np.clip(p["drop_p"], 0.0, 1.0))
        if "p" in p:
            return float(np.clip(p["p"], 0.0, 1.0))
    raise ValueError(f"Unknown or invalid loss profile: {p}")


class IIDLink:
    """Represents a single link with independent and identically distributed (IID) packet loss."""
    def __init__(self, drop_prob: float):
        self.drop_prob = float(np.clip(drop_prob, 0.0, 1.0))

    def flight_stats(self, W: int):
        """Evaluates closed-form IID loss statistics for a flight of W packets."""
        p = self.drop_prob
        p0 = (1.0 - p) ** W
        pa = p ** W
        el = float(W) * p
        return p0, pa, el


class MultiHopPath:
    """Chains Link 1 and Link 2 under independent Bernoulli drop models."""
    def __init__(self, link1: IIDLink, link2: IIDLink):
        self.link1 = link1
        self.link2 = link2
        # End-to-end composite drop probability: p_e2e = 1 - (1 - p1) * (1 - p2)
        p1 = self.link1.drop_prob
        p2 = self.link2.drop_prob
        self.drop_prob = float(np.clip(1.0 - (1.0 - p1) * (1.0 - p2), 0.0, 1.0))

    def flight_stats_path(self, W: int):
        p = self.drop_prob
        p0 = (1.0 - p) ** W
        pa = p ** W
        el = float(W) * p
        p1 = self.link1.drop_prob
        p2 = self.link2.drop_prob
        attr = {
            "link1_drop_prob": 1.0 - (1.0 - p1) ** W,
            "link2_drop_prob": ((1.0 - p1) ** W) * (1.0 - (1.0 - p2) ** W),
            "e2e_success_prob": p0,
        }
        return p0, pa, el, attr


# ─────────────────────── Network Parameters ───────────────────────
# Per-Hop Delays
OWD1 = 0.010                      # Link 1 one-way propagation delay (s) [e.g. 10ms]
OWD2 = 0.010                      # Link 2 one-way propagation delay (s) [e.g. 10ms]
OWD  = OWD1 + OWD2                # Total path one-way propagation delay (20ms)
O    = OWD                        # Backward compatibility alias
RTT  = 2.0 * OWD                  # Total Round-trip time (40ms)

SER1 = 1514.0 * 8.0 / 1.0e9       # Per-packet serialization delay on Link 1 (1 Gbps)
SER2 = 1514.0 * 8.0 / 1.0e9       # Per-packet serialization delay on Link 2 (1 Gbps)
SER  = SER1 + SER2                # Aggregate per-packet serialization delay across 2 hops

MAX_CWND = 1000                   # Physical ceiling for the network path
BUFFER_CAPACITY = 1000            # Physical limit where tail-drop loss occurs

# ─────────────────────── TCP Parameters ───────────────────────

IW         = 10
RTO_MIN    = 0.2
DELACK_MIN = 0.040                # Linux TCP_DELACK_MIN (40ms delayed ACK timer)
CUBIC_C    = 0.4
CUBIC_B    = 0.7
RACK_FRAC  = 0.25


def _tlp_pto(flight_size: int) -> float:
    """Computes Linux RFC 8985 Tail Loss Probe Timeout (PTO) for a flight of W segments."""
    if flight_size <= 1:
        return max(2.0 * RTT, 1.5 * RTT + DELACK_MIN)
    return 2.0 * RTT

# ─────────────────────── Global Path Setup ───────────────────────

_ACTIVE_PROFILE_NAME = "fair"
_ACTIVE_PROFILE_L2_NAME = "fair"
_link1 = IIDLink(PROFILES["fair"])
_link2 = IIDLink(PROFILES["fair"])
_path = MultiHopPath(_link1, _link2)

def set_active_profile(profile_name_l1, profile_name_l2=None):
    """Set distinct profiles for Link 1 and Link 2."""
    global _link1, _link2, _path, _cache, _ACTIVE_PROFILE_NAME, _ACTIVE_PROFILE_L2_NAME
    if profile_name_l2 is None:
        profile_name_l2 = profile_name_l1
        
    _ACTIVE_PROFILE_NAME = profile_name_l1
    _ACTIVE_PROFILE_L2_NAME = profile_name_l2
    p1 = resolve_profile(profile_name_l1)
    p2 = resolve_profile(profile_name_l2)
    _link1 = IIDLink(p1)
    _link2 = IIDLink(p2)
    _path = MultiHopPath(_link1, _link2)
    _cache.clear()

def _cubic_w(t, w_max):
    K = ((1.0 - CUBIC_B) * w_max / CUBIC_C) ** (1.0 / 3.0)
    return max(1.0, CUBIC_C * (t - K) ** 3 + w_max)

class TcpState:
    """Encapsulates TCP congestion state across connection transfers."""
    def __init__(self, cwnd=10.0, w_max=None, t_since=0.0, in_slow_start=True,
                 last_send_time=None, last_ack_time=None):
        self.cwnd = float(cwnd)
        self.w_max = float(w_max if w_max is not None else (self.cwnd / CUBIC_B))
        self.t_since = float(t_since)
        self.in_slow_start = bool(in_slow_start)
        self.last_send_time = last_send_time
        self.last_ack_time = last_ack_time

    def __repr__(self):
        return (f"TcpState(cwnd={self.cwnd:.6f}, w_max={self.w_max:.6f}, "
                f"t_since={self.t_since:.6f}, in_slow_start={self.in_slow_start}, "
                f"last_send_time={self.last_send_time}, last_ack_time={self.last_ack_time})")

def init_tcp_state():
    return TcpState(10.0, 10.0 / CUBIC_B, 0.0, in_slow_start=True)

# ─────────────────────── Timeline Generation ───────────────────────

def _compute_delayed_ack_times(times_dest, max_k):
    """
    Computes expected ACK arrival times at the IXP and the Sender under Linux Delayed ACKs.

    In Linux TCP (net/ipv4/tcp_input.c):
      - When an unacknowledged segment k arrives at times_dest[k], the receiver arms
        the delayed ACK timer for times_dest[k] + DELACK_MIN (40ms).
      - If a 2nd segment (k + 1) arrives before the delayed ACK timer expires
        (times_dest[k + 1] <= times_dest[k] + DELACK_MIN), the receiver immediately
        emits one cumulative ACK at t_ack_depart = max(times_dest[k], times_dest[k + 1])
        (recorded at index k + 1, leaving index k as NaN), and advances by 2 segments.
      - Otherwise (if k is the final segment or the next segment arrives after the
        delayed ACK timer expires), the timer fires at t_ack_depart = times_dest[k] + DELACK_MIN,
        emitting an ACK at index k, and advances by 1 segment.
      - Once generated at the destination at t_ack_depart:
          ack_times_ixp    = t_ack_depart + OWD2
          ack_times_sender = t_ack_depart + OWD
    """
    ack_times_ixp    = np.full(max_k + 1, np.nan)
    ack_times_sender = np.full(max_k + 1, np.nan)
    ack_times_ixp[0]    = 0.0
    ack_times_sender[0] = 0.0

    k = 1
    while k <= max_k and np.isfinite(times_dest[k]):
        t_k = float(times_dest[k])
        if k + 1 <= max_k and np.isfinite(times_dest[k + 1]) and float(times_dest[k + 1]) <= t_k + DELACK_MIN:
            # 2nd segment arrives before delayed ACK timer expires -> immediate cumulative ACK
            t_ack_depart = max(t_k, float(times_dest[k + 1]))
            ack_times_ixp[k + 1]    = t_ack_depart + OWD2
            ack_times_sender[k + 1] = t_ack_depart + OWD
            k += 2
        else:
            # Delayed ACK timer expires before any next segment arrives
            t_ack_depart = t_k + DELACK_MIN
            ack_times_ixp[k]    = t_ack_depart + OWD2
            ack_times_sender[k] = t_ack_depart + OWD
            k += 1

    return ack_times_ixp, ack_times_sender


def _build_timeline(max_k=2000, is_new=True, state=None, start_time=None):
    times_ixp  = np.full(max_k + 1, np.nan)
    times_dest = np.full(max_k + 1, np.nan)
    flts       = np.zeros(max_k + 1, dtype=int)
    
    times_ixp[0]  = 0.0
    times_dest[0] = 0.0
    total_el = 0.0

    LOCAL_MAX_CWND = 1000
    is_none = _path.drop_prob <= 1e-10

    if start_time is None:
        start_time = (state.last_ack_time if state is not None and state.last_ack_time is not None else 0.0)

    if is_new:
        # Phase 1: Handshake (TCP 3-way HS + TLS HS completes at t = 2 * RTT; App Data starts at t = 2 * RTT)
        t = 2.0 * RTT
        seg = 0
        flt = 1
        W_ss = IW
        in_slow_start = True
    else:
        # Reused connection: bypass Handshake
        t = 0.0
        seg = 0
        flt = 1
        if state is None:
            state = init_tcp_state()
        in_slow_start = getattr(state, 'in_slow_start', False)
        cwnd = max(2.0, min(float(state.cwnd), float(LOCAL_MAX_CWND)))
        w_max = max(1.0, min(float(state.w_max), float(LOCAL_MAX_CWND)))
        t_since = float(state.t_since)
        # Linux's default tcp_slow_start_after_idle behavior is only applied
        # when the previous flight has drained and the sender has been idle
        # for more than its RTO. RTO_MIN is the model's RTO approximation.
        if (state.last_send_time is not None and state.last_ack_time is not None
                and start_time >= state.last_ack_time):
            idle = start_time - state.last_send_time
            if idle > RTO_MIN:
                while idle > RTO_MIN and cwnd > float(IW):
                    cwnd = max(float(IW), float(int(cwnd) // 2))
                    idle -= RTO_MIN
                in_slow_start = cwnd <= float(IW)
                if in_slow_start:
                    cwnd = min(cwnd, float(IW))
                    t_since = 0.0
        if in_slow_start:
            W_ss = max(1, int(round(cwnd)))
        else:
            pass

    if in_slow_start:
        last_p0 = 1.0
        exited_due_to_loss = False

        while seg < max_k:
            p0, pa, el_fwd, attr = _path.flight_stats_path(W_ss)
            p_l = 1.0 - p0

            if is_none and (seg + W_ss > BUFFER_CAPACITY):
                dropped_packets = (seg + W_ss) - BUFFER_CAPACITY
                p_l = dropped_packets / float(W_ss)
                p0 = 1.0 - p_l
                total_el += float(dropped_packets)
            else:
                total_el += el_fwd

            current_flight_size = min(int(W_ss), LOCAL_MAX_CWND)
            dt_rack = (2.0 * RTT + RTT * RACK_FRAC) * (0.5 if is_none else 1.0)
            pto = _tlp_pto(current_flight_size)
            p_drop = p_l if is_none else _path.drop_prob
            dt_tlp_single = pto + (1.0 - p_drop) * RTT + p_drop * RTO_MIN
            dt_tlp_multi = pto + (1.0 - p_drop) * (2.0 * RTT) + p_drop * RTO_MIN

            # Per-segment recovery:
            # If segment i is dropped, there are rem = current_flight_size - 1 - i subsequent
            # segments in the flight. If at least one subsequent segment arrives (1 - p_drop^rem),
            # RACK detects the loss after RTT + RTT * RACK_FRAC; if all subsequent segments are
            # also lost (p_drop^rem, including i == current_flight_size - 1 where rem == 0),
            # recovery waits for the Tail Loss Probe (PTO), falling back to RTO_MIN if the
            # TLP probe itself is also dropped.
            dt_tlp_seg = dt_tlp_single * (0.5 if is_none else 1.0)

            for i in range(current_flight_size):
                k = seg + i + 1
                if k <= max_k:
                    rem = current_flight_size - 1 - i
                    p_tail_from_i = (p_drop ** rem) if not is_none else 0.0
                    dt_seg_recovery = (1.0 - p_tail_from_i) * dt_rack + p_tail_from_i * dt_tlp_seg
                    # Arrival at IXP (Link 1) vs Final Destination (Link 1 + Link 2)
                    times_ixp[k]  = t + OWD1 + i * SER1 + p_drop * dt_seg_recovery
                    times_dest[k] = t + OWD  + i * SER  + p_drop * dt_seg_recovery
                    flts[k]       = flt
            seg += current_flight_size

            if is_none:
                dt = p0 * RTT + p_l * dt_rack
            else:
                # Flight-level RACK-TLP decomposition:
                #   1. p0 = (1 - p)^W: zero loss -> RTT
                #   2. p_rack = (1 - p) - (1 - p)^W: interior loss(es), last segment arrives -> RACK
                #   3. p_tlp_single = (1 - p)^(W - 1) * p: only last segment lost -> TLP probe
                #      repairs directly in PTO + RTT (prob 1 - p), or PTO + RTO_MIN if probe dropped
                #   4. p_tlp_multi = p - p_tlp_single: last segment + earlier segment(s) lost ->
                #      TLP probe SACK triggers RACK recovery in PTO + 2*RTT (prob 1 - p), or PTO + RTO_MIN
                p_rack = max(0.0, (1.0 - p_drop) - p0)
                p_tlp_single = ((1.0 - p_drop) ** max(0, current_flight_size - 1)) * p_drop
                p_tlp_multi = max(0.0, p_drop - p_tlp_single)
                dt = (p0 * RTT
                      + p_rack * dt_rack
                      + p_tlp_single * dt_tlp_single
                      + p_tlp_multi * dt_tlp_multi)
            t += dt
            flt += 1

            W_next_ss = min(W_ss * 2, LOCAL_MAX_CWND)
            p0_next, _, el_fwd_next, _ = _path.flight_stats_path(W_next_ss)

            if el_fwd >= 0.5 or el_fwd_next >= 0.5 or (seg + W_ss > BUFFER_CAPACITY) or current_flight_size >= LOCAL_MAX_CWND:
                last_p0 = p0_next if p_l == 0.0 else p0
                exited_due_to_loss = True
                break
            W_ss = W_next_ss

        if exited_due_to_loss:
            in_slow_start = False
            p_l_last = 1.0 - last_p0
            cwnd = max(2.0, min(last_p0 * float(W_ss * 2) + p_l_last * max(float(W_ss) * CUBIC_B, 2.0), LOCAL_MAX_CWND))
            w_max = min(cwnd / CUBIC_B, LOCAL_MAX_CWND)
            t_since = 0.0
        else:
            in_slow_start = True
            cwnd = float(W_next_ss)
            w_max = min(cwnd / CUBIC_B, LOCAL_MAX_CWND)
            t_since = 0.0

    if not in_slow_start:
        # Phase 3: Congestion Avoidance
        for _ in range(100_000):
            if seg >= max_k:
                break

            W = max(1, int(round(cwnd)))
            p0, pa, el_fwd, attr = _path.flight_stats_path(W)

            if is_none and W > BUFFER_CAPACITY and W > int(round(w_max)):
                ca_dropped = W - BUFFER_CAPACITY
                p_l_ca = ca_dropped / float(W)
                p0 = max(0.0, 1.0 - p_l_ca)
                pa = 0.0
                total_el += float(ca_dropped)
            else:
                total_el += el_fwd

            pp = max(0.0, 1.0 - p0 - pa)
            E_del = float(W)

            seg_start = int(np.floor(seg))
            seg_end   = int(np.floor(seg + E_del))

            dt_rack = 2.0 * RTT + RTT * RACK_FRAC
            if is_none:
                E_dt_nominal = p0 * RTT + pp * dt_rack + pa * RTO_MIN
                p_fast_or_tlp = pp
                p_rto = pa
            else:
                p_drop = _path.drop_prob
                pto = _tlp_pto(W)
                p_rack = max(0.0, (1.0 - p_drop) - p0)
                p_tlp_single = ((1.0 - p_drop) ** max(0, W - 1)) * p_drop
                p_tlp_multi = max(0.0, p_drop - p_tlp_single)
                dt_tlp_single = pto + (1.0 - p_drop) * RTT + p_drop * RTO_MIN
                dt_tlp_multi = pto + (1.0 - p_drop) * (2.0 * RTT) + p_drop * RTO_MIN
                E_dt_nominal = (p0 * RTT
                                + p_rack * dt_rack
                                + p_tlp_single * dt_tlp_single
                                + p_tlp_multi * dt_tlp_multi)
                # Under RACK-TLP, full RTO reset to cwnd=1 occurs when the entire flight
                # AND its TLP probe are lost (pa * p_drop)
                p_rto = pa * p_drop
                p_fast_or_tlp = max(0.0, (1.0 - p0) - p_rto)

            E_dt = max(E_del * SER, E_dt_nominal)

            for k_idx in range(seg_start + 1, seg_end + 1):
                if k_idx <= max_k:
                    fractional_offset = (k_idx - 1 - seg_start) / max(1.0, E_del)
                    times_ixp[k_idx]  = t + OWD1 + (fractional_offset * W * SER1)
                    times_dest[k_idx] = t + OWD  + (fractional_offset * W * SER)
                    flts[k_idx]       = flt

            seg += E_del
            t   += E_dt

            # CUBIC dynamics
            p_loss_event = pp + pa
            if p_loss_event > 1e-15:
                w_max = (1.0 - p_loss_event) * w_max + p_loss_event * cwnd
                t_since = (1.0 - p_loss_event) * (t_since + E_dt)
            else:
                t_since += E_dt

            w_reno = cwnd + (1.0 / max(1.0, cwnd))
            w_no   = max(_cubic_w(t_since, w_max), w_reno)

            cwnd_next = p0 * w_no + p_fast_or_tlp * (cwnd * CUBIC_B) + p_rto * 1.0
            cwnd = max(2.0, min(cwnd_next, LOCAL_MAX_CWND))
            flt += 1

    ack_times_ixp, ack_times_sender = _compute_delayed_ack_times(times_dest, max_k)

    valid_dest = times_dest[np.isfinite(times_dest)]
    valid_ack_sender = ack_times_sender[np.isfinite(ack_times_sender)]
    if len(valid_dest) > 1:
        last_dest = float(np.max(valid_dest[1:]))
        last_send_time = start_time + last_dest - OWD
        last_ack_time = start_time + float(np.max(valid_ack_sender[1:]))
    else:
        last_send_time = state.last_send_time if state is not None else None
        last_ack_time = state.last_ack_time if state is not None else None
    final_state = TcpState(cwnd=cwnd, w_max=w_max, t_since=t_since,
                           in_slow_start=in_slow_start,
                           last_send_time=last_send_time, last_ack_time=last_ack_time)
    return times_ixp, times_dest, ack_times_ixp, ack_times_sender, flts, total_el, final_state

# ─────────────────────── Public API ───────────────────────

_cache: dict = {}

def simulate_transfer(num_segments, is_new=True, state=None, *, start_time):
    """
    Simulates transmission of num_segments, returning
    (times_ixp, times_dest, ack_times_ixp, ack_times_sender, final_state),
    where ack_times_ixp and ack_times_sender contain one timestamp per emitted ACK packet.
    """
    t_ixp, t_dest, ack_ixp, ack_sender, _, _, final_state = _build_timeline(
        num_segments, is_new=is_new, state=state, start_time=start_time)
    ack_ixp_slice = ack_ixp[1:num_segments + 1]
    ack_sender_slice = ack_sender[1:num_segments + 1]
    return (
        t_ixp[1:num_segments + 1],
        t_dest[1:num_segments + 1],
        ack_ixp_slice[np.isfinite(ack_ixp_slice)],
        ack_sender_slice[np.isfinite(ack_sender_slice)],
        final_state,
    )

def expected_time_k(k):
    """Returns (t_ixp, t_dest, t_ack_ixp, t_ack_sender, flight_id) for segment k."""
    global _cache
    if 'times_dest' not in _cache or k >= len(_cache['times_dest']):
        n = max(2000, k + 500)
        t_ixp, t_dest, ack_ixp, ack_sender, f, el, _ = _build_timeline(n)
        _cache = {
            'times_ixp': t_ixp,
            'times_dest': t_dest,
            'ack_times_ixp': ack_ixp,
            'ack_times_sender': ack_sender,
            'flights': f,
            'total_el': el
        }
    if k <= 0:
        return 0.0, 0.0, 0.0, 0.0, 0
    return (
        float(_cache['times_ixp'][k]),
        float(_cache['times_dest'][k]),
        float(_cache['ack_times_ixp'][k]),
        float(_cache['ack_times_sender'][k]),
        int(_cache['flights'][k])
    )

def get_total_retransmissions():
    global _cache
    if 'total_el' in _cache:
        return float(_cache['total_el'])
    return 0.0

def get_tc_netem_params(link_obj=None):
    """Returns packet loss percentage for tc netem (loss <pct>%)."""
    if link_obj is None:
        link_obj = _link1
    return getattr(link_obj, 'drop_prob', 0.0) * 100.0
