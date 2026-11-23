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

IW                = 10
RTO_MIN           = 0.2
DELACK_MIN         = 0.040        # Linux TCP_DELACK_MIN (40ms delayed ACK timer)
TCP_MAX_QUICKACKS  = 16           # Linux include/net/tcp.h TCP_MAX_QUICKACKS
RCV_GROW_START_SEG = 72           # Segment index where tcp_rcv_space_adjust expands sk_rcvbuf
RCV_GROW_END_SEG   = 264          # Segment index where rcv_ssthresh reaches autotuned tcp_space ceiling
CUBIC_C           = 0.4
CUBIC_B           = 0.7
RACK_FRAC         = 0.25

TCP_HEADER_BYTES  = 32
IP_HEADER_BYTES   = 20
HEADER_BYTES      = IP_HEADER_BYTES + TCP_HEADER_BYTES  # 52B
MTU_SIZE_BYTES    = 1500
MSS_SIZE_BYTES    = MTU_SIZE_BYTES - HEADER_BYTES       # 1448B


def hs_times(ow_offset: float, is_new: bool = True) -> np.ndarray:
    """
    Returns the 5 forward (Client -> Server) TCP + TLS handshake timestamps for new connections:
      1. SYN                   sent at t = 0.0
      2. ACK (TCP 3-way HS)    sent at t = 1.0 * RTT (2 * OWD)
      3. TLS Client Hello      sent at t = 1.0 * RTT (2 * OWD)
      4. ACK (TLS HS)          sent at t = 2.0 * RTT (4 * OWD)
      5. TLS Change Cipher     sent at t = 2.0 * RTT (4 * OWD)
    """
    if not is_new:
        return np.empty(0, dtype=float)
    return np.array([
        ow_offset,
        2.0 * OWD + ow_offset,
        2.0 * OWD + ow_offset,
        4.0 * OWD + ow_offset,
        4.0 * OWD + ow_offset,
    ], dtype=float)


def hs_ack_times(ow_offset: float, is_new: bool = True) -> np.ndarray:
    """
    Returns the 4 reverse (Server -> Client) TCP + TLS handshake timestamps for new connections:
      1. SYN-ACK               departing Server at t = 1.0 * OWD (0.5 * RTT)
      2. ACK (TLS ClientHello) departing Server at t = 3.0 * OWD (1.5 * RTT)
      3. TLS Server Hello      departing Server at t = 3.0 * OWD (1.5 * RTT)
      4. ACK (TLS ChangeCipher) departing Server at t = 5.0 * OWD (2.5 * RTT)
    """
    if not is_new:
        return np.empty(0, dtype=float)
    return np.array([
        1.0 * OWD + ow_offset,
        3.0 * OWD + ow_offset,
        3.0 * OWD + ow_offset,
        5.0 * OWD + ow_offset,
    ], dtype=float)


def hs_sizes(is_new: bool = True) -> list[int]:
    """Returns the 5 forward handshake packet sizes in bytes: [52, 52, 1500, 52, 1500]."""
    if not is_new:
        return []
    return [
        HEADER_BYTES,
        HEADER_BYTES,
        MTU_SIZE_BYTES,
        HEADER_BYTES,
        MTU_SIZE_BYTES,
    ]


def hs_ack_sizes(is_new: bool = True) -> list[int]:
    """Returns the 4 reverse handshake packet sizes in bytes: [52, 52, 1500, 52]."""
    if not is_new:
        return []
    return [
        HEADER_BYTES,
        HEADER_BYTES,
        MTU_SIZE_BYTES,
        HEADER_BYTES,
    ]


def tcp_delivery_sizes(msg_size: int, delivery_times=None, ack_times=None, is_new: bool | None = None):
    """
    Computes wire packet sizes (including 52B IP+TCP headers) for forward and reverse timelines.
    When ack_times is omitted, returns the forward data size list (including forward handshake
    sizes when is_new=True). When ack_times is provided, returns (data_sizes, ack_sizes).
    """
    if isinstance(msg_size, bool) or not isinstance(msg_size, int) or msg_size <= 0:
        raise ValueError("msg_size must be a positive integer")
    num_original_segments = (msg_size + MSS_SIZE_BYTES - 1) // MSS_SIZE_BYTES
    if is_new is None:
        if delivery_times is not None:
            is_new = len(delivery_times) > num_original_segments
        else:
            is_new = True
    last_payload_bytes = msg_size - (num_original_segments - 1) * MSS_SIZE_BYTES
    last_pkt_size_bytes = last_payload_bytes + HEADER_BYTES
    data_sizes = (
        hs_sizes(bool(is_new))
        + [MTU_SIZE_BYTES] * max(0, num_original_segments - 1)
        + [last_pkt_size_bytes]
    )
    if ack_times is None:
        return data_sizes
    hs_rev = hs_ack_sizes(bool(is_new))
    num_data_acks = max(0, len(ack_times) - len(hs_rev))
    ack_sizes = hs_rev + [HEADER_BYTES] * num_data_acks
    return data_sizes, ack_sizes


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
    """Encapsulates TCP congestion and receiver quickack state across connection transfers."""
    def __init__(self, cwnd=10.0, w_max=None, t_since=0.0, in_slow_start=True,
                 last_send_time=None, last_ack_time=None, quickacks_left=None):
        self.cwnd = float(cwnd)
        self.w_max = float(w_max if w_max is not None else (self.cwnd / CUBIC_B))
        self.t_since = float(t_since)
        self.in_slow_start = bool(in_slow_start)
        self.last_send_time = last_send_time
        self.last_ack_time = last_ack_time
        self.quickacks_left = quickacks_left

    def __repr__(self):
        return (f"TcpState(cwnd={self.cwnd:.6f}, w_max={self.w_max:.6f}, "
                f"t_since={self.t_since:.6f}, in_slow_start={self.in_slow_start}, "
                f"last_send_time={self.last_send_time}, last_ack_time={self.last_ack_time})")

def init_tcp_state():
    return TcpState(10.0, 10.0 / CUBIC_B, 0.0, in_slow_start=True)

# ─────────────────────── Timeline Generation ───────────────────────

def _compute_delayed_ack_times(times_dest, max_k, *, is_new=True, state=None, start_time=0.0, flts=None, ss_max_k=None):
    """
    Computes expected ACK arrival times at the IXP and the Sender under Linux QuickACK,
    Delayed ACKs, and reverse-path ACK loss (net/ipv4/tcp_input.c & net/ipv4/tcp_output.c).

    In Linux TCP:
      - On the first data segment of a new connection (icsk_ack.ato == 0 in
        tcp_event_data_recv), tcp_incr_quickack(sk, TCP_MAX_QUICKACKS) initializes
        the quickack budget `quick = TCP_MAX_QUICKACKS` (16).
      - On a reused connection (is_new=False), the receiver retains any remaining
        `quickacks_left` from the prior transfer (defaulting to 0 if already exhausted
        or unspecified), and replenishes `quick = TCP_MAX_QUICKACKS` if the receiver
        idle gap since the previous received data segment exceeds RTO_MIN
        (now - icsk_ack.lrcvtime > icsk_rto in tcp_event_data_recv).
      - Receive-window autotuning QuickACKs (tcp_rcv_space_adjust & tcp_grow_window):
        Once Flight 3 completes (after segment RCV_GROW_START_SEG = 72) while the
        sender is still ramping up in Slow Start (k <= ss_max_k) and no packet-loss
        hole has opened, Linux's receive-buffer autotuner expands sk_rcvbuf /
        tcp_space(sk) up to ~384 KB (RCV_GROW_END_SEG = 264 segments). While
        rcv_ssthresh grows in order, tcp_grow_window sets `icsk_ack.quick |= 1` on
        each segment, forcing an immediate QuickACK (delta_k = 1). Once a loss
        opens an out-of-order hole (triggering compressed SACKs in tcp_data_queue_ofo)
        or the sender exits Slow Start into Congestion Avoidance, window growth stops.
      - In __tcp_ack_snd_check, each arriving segment triggers an immediate cumulative
        ACK if either:
          1. `quick > 0` (tcp_in_quickack_mode), or
          2. at least 2 full-sized segments are unacknowledged (`pending >= 2`).
      - Otherwise (`quick == 0` and `pending == 1`), the receiver arms the delayed ACK
        timer for `t_k + DELACK_MIN` (40ms). If the next segment arrives before that
        deadline, both segments are cumulatively ACKed upon the 2nd segment's arrival;
        if not (or at the end of the transfer), the timer fires at `t_k + DELACK_MIN`.
      - Every emitted ACK calls tcp_event_ack_sent -> tcp_dec_quickack_mode(sk, 1),
        decrementing `quick = max(0, quick - 1)`.
      - Reverse-path ACK loss:
          * When an emitted ACK is dropped on the reverse path (prob p2 before IXP,
            p_e2e before Sender), it is cumulatively covered by subsequent surviving
            ACKs (even across flight boundaries) or repaired via the sender's Tail
            Loss Probe (TLP), whichever completes first.
    """
    ack_times_ixp    = np.full(max_k + 1, np.nan)
    ack_times_sender = np.full(max_k + 1, np.nan)
    ack_depart       = np.full(max_k + 1, np.nan)
    ack_times_ixp[0]    = 0.0
    ack_times_sender[0] = 0.0

    if is_new:
        quick = TCP_MAX_QUICKACKS
        prev_t = None
    else:
        quick = (int(state.quickacks_left)
                 if state is not None and getattr(state, 'quickacks_left', None) is not None
                 else 0)
        if (state is not None and state.last_send_time is not None
                and state.last_ack_time is not None and start_time >= state.last_ack_time):
            prev_t = (float(state.last_send_time) + OWD) - float(start_time)
        else:
            prev_t = None

    ss_limit = RCV_GROW_END_SEG if ss_max_k is None else min(RCV_GROW_END_SEG, int(ss_max_k))
    if ss_limit <= RCV_GROW_START_SEG:
        rcv_grow_end = RCV_GROW_START_SEG
    elif _path.drop_prob <= 1e-10:
        rcv_grow_end = ss_limit
    else:
        p_surv = 1.0 - _path.drop_prob
        expected_grow = sum(
            p_surv ** (j - RCV_GROW_START_SEG)
            for j in range(RCV_GROW_START_SEG + 1, ss_limit + 1)
        )
        # Round to an even number of segments so delayed-ACK pairing stays aligned
        rcv_grow_end = RCV_GROW_START_SEG + 2 * int(round(expected_grow / 2.0))

    pending = 0
    deadline = None
    last_k = 0
    running_t = 0.0

    for k in range(1, max_k + 1):
        if not np.isfinite(times_dest[k]):
            break
        t_k = max(running_t, float(times_dest[k]))
        running_t = t_k

        # If a pending delayed ACK timer expired before segment k arrived, emit it first
        if pending > 0 and deadline < t_k:
            ack_depart[last_k] = deadline
            quick = max(0, quick - 1)
            pending = 0
            deadline = None

        # tcp_event_data_recv: replenish quickacks if intra-transfer receive gap > RTO_MIN
        if prev_t is not None and (t_k - prev_t) > RTO_MIN:
            quick = TCP_MAX_QUICKACKS
        prev_t = t_k

        # tcp_grow_window: while in Slow Start and rcv_ssthresh grows in-order toward
        # the autotuned tcp_space(sk) ceiling, Linux executes `icsk_ack.quick |= 1`.
        if RCV_GROW_START_SEG < k <= rcv_grow_end:
            quick = max(quick, 1)

        if pending == 0:
            deadline = t_k + DELACK_MIN
        pending += 1
        last_k = k

        # __tcp_ack_snd_check: immediate ACK if in quickack mode or >= 2 segments pending
        if quick > 0 or pending >= 2:
            ack_depart[k] = t_k
            quick = max(0, quick - 1)
            pending = 0
            deadline = None
        elif t_k >= deadline:
            ack_depart[k] = deadline
            quick = max(0, quick - 1)
            pending = 0
            deadline = None

    if pending > 0:
        ack_depart[last_k] = deadline
        quick = max(0, quick - 1)

    # Apply reverse-path propagation and reverse-path ACK loss recovery
    is_none = _path.drop_prob <= 1e-10
    p_rev_ixp = 0.0 if is_none else _link2.drop_prob
    p_rev_snd = 0.0 if is_none else _path.drop_prob
    p_probe_ok = (1.0 - p_rev_snd) ** 2
    p_probe_fail = 1.0 - p_probe_ok

    emitted_ks = [k for k in range(1, max_k + 1) if np.isfinite(ack_depart[k])]
    if emitted_ks:
        eff_dep_ixp = np.zeros(len(emitted_ks), dtype=float)
        eff_dep_snd = np.zeros(len(emitted_ks), dtype=float)

        for idx in range(len(emitted_ks) - 1, -1, -1):
            k = emitted_ks[idx]
            t_dep = float(ack_depart[k])
            if flts is not None and flts[k] > 0:
                flt_id = flts[k]
                flt_size = int(np.sum(flts[1:max_k + 1] == flt_id))
            else:
                flt_size = 2 if idx > 0 else 1
            pto_ack = _tlp_pto(max(1, flt_size))
            t_tlp_rec = t_dep + pto_ack + p_probe_ok * RTT + p_probe_fail * RTO_MIN

            if idx == len(emitted_ks) - 1:
                rec_dep_ixp = t_tlp_rec
                rec_dep_snd = t_tlp_rec
            else:
                rec_dep_ixp = min(eff_dep_ixp[idx + 1], t_tlp_rec)
                rec_dep_snd = min(eff_dep_snd[idx + 1], t_tlp_rec)

            eff_dep_ixp[idx] = (1.0 - p_rev_ixp) * t_dep + p_rev_ixp * rec_dep_ixp
            eff_dep_snd[idx] = (1.0 - p_rev_snd) * t_dep + p_rev_snd * rec_dep_snd
            ack_times_ixp[k]    = eff_dep_ixp[idx] + OWD2
            ack_times_sender[k] = eff_dep_snd[idx] + OWD

    return ack_times_ixp, ack_times_sender, quick


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
                in_slow_start = True
                t_since = 0.0
        if in_slow_start:
            W_ss = max(1, int(round(cwnd)))
        else:
            pass

    ss_max_k = 0
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

            # Recovery depends on packets actually sent, even when the final
            # flight does not fill the congestion window. Keep the existing
            # window-based congestion/slow-start evolution separate.
            window_flight_size = min(int(W_ss), LOCAL_MAX_CWND)
            actual_flight_size = min(window_flight_size, max_k - seg)
            dt_rack = (2.0 * RTT + RTT * RACK_FRAC) * (0.5 if is_none else 1.0)
            pto = _tlp_pto(actual_flight_size)
            p_drop = p_l if is_none else _path.drop_prob
            p_probe_ok = (1.0 - p_drop) ** 2
            p_probe_fail = 1.0 - p_probe_ok
            dt_tlp_single = pto + p_probe_ok * RTT + p_probe_fail * RTO_MIN
            dt_tlp_multi = pto + p_probe_ok * (2.0 * RTT) + p_probe_fail * RTO_MIN

            # Per-segment recovery:
            # If segment i is dropped, there are rem = actual_flight_size - 1 - i subsequent
            # segments in the flight. If at least one subsequent segment arrives (1 - p_drop^rem),
            # RACK detects the loss after RTT + RTT * RACK_FRAC; if all subsequent segments are
            # also lost (p_drop^rem, including i == actual_flight_size - 1 where rem == 0),
            # recovery waits for the Tail Loss Probe (PTO), falling back to RTO_MIN if the
            # TLP probe or its reverse ACK is also dropped.
            dt_tlp_seg = dt_tlp_single * (0.5 if is_none else 1.0)

            for i in range(actual_flight_size):
                k = seg + i + 1
                if k <= max_k:
                    rem = actual_flight_size - 1 - i
                    p_tail_from_i = (p_drop ** rem) if not is_none else 0.0
                    dt_seg_recovery = (1.0 - p_tail_from_i) * dt_rack + p_tail_from_i * dt_tlp_seg
                    # Arrival at IXP (Link 1) vs Final Destination (Link 1 + Link 2)
                    times_ixp[k]  = t + OWD1 + i * SER1 + p_drop * dt_seg_recovery
                    times_dest[k] = t + OWD  + i * SER  + p_drop * dt_seg_recovery
                    flts[k]       = flt
            seg += actual_flight_size

            if is_none:
                dt = p0 * RTT + p_l * dt_rack
            else:
                # Flight-level RACK-TLP decomposition (including reverse-path ACK loss):
                #   1. flight_p0 = (1 - p)^F: zero forward loss -> RTT if final ACK survives
                #      (prob 1 - p), or TLP recovery dt_tlp_single if final ACK is lost (prob p)
                #   2. p_rack = (1 - p) - (1 - p)^F: interior loss(es), last segment arrives -> RACK
                #   3. p_tlp_single = (1 - p)^(F - 1) * p: only last segment lost -> TLP probe
                #      repairs directly in PTO + RTT (prob (1 - p)^2), or PTO + RTO_MIN if probe/ACK dropped
                #   4. p_tlp_multi = p - p_tlp_single: last segment + earlier segment(s) lost ->
                #      TLP probe SACK triggers RACK recovery in PTO + 2*RTT (prob (1 - p)^2), or PTO + RTO_MIN
                flight_p0 = (1.0 - p_drop) ** actual_flight_size
                dt_zero_fwd = (1.0 - p_drop) * RTT + p_drop * dt_tlp_single
                p_rack = max(0.0, (1.0 - p_drop) - flight_p0)
                p_tlp_single = ((1.0 - p_drop) ** max(0, actual_flight_size - 1)) * p_drop
                p_tlp_multi = max(0.0, p_drop - p_tlp_single)
                dt = (flight_p0 * dt_zero_fwd
                      + p_rack * dt_rack
                      + p_tlp_single * dt_tlp_single
                      + p_tlp_multi * dt_tlp_multi)
            t += dt
            flt += 1

            # RFC 3465 Appropriate Byte Counting: cwnd grows by the number of
            # segments actually sent and acknowledged in the flight.
            W_next_ss = min(W_ss + actual_flight_size, LOCAL_MAX_CWND)
            p0_next, _, el_fwd_next, _ = _path.flight_stats_path(W_next_ss)

            if el_fwd >= 0.5 or el_fwd_next >= 0.5 or (seg + W_ss > BUFFER_CAPACITY) or window_flight_size >= LOCAL_MAX_CWND:
                last_p0 = p0_next if p_l == 0.0 else p0
                exited_due_to_loss = True
                break
            W_ss = W_next_ss

        ss_max_k = int(seg)
        if exited_due_to_loss:
            in_slow_start = False
            p_l_last = 1.0 - last_p0
            cwnd = max(2.0, min(last_p0 * float(W_next_ss) + p_l_last * max(float(W_ss) * CUBIC_B, 2.0), LOCAL_MAX_CWND))
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
            actual_flight_size = min(W, max_k - seg_start)

            dt_rack = 2.0 * RTT + RTT * RACK_FRAC
            if is_none:
                E_dt_nominal = p0 * RTT + pp * dt_rack + pa * RTO_MIN
                p_fast_or_tlp = pp
                p_rto = pa
            else:
                p_drop = _path.drop_prob
                p_probe_ok = (1.0 - p_drop) ** 2
                p_probe_fail = 1.0 - p_probe_ok
                # Timing uses the actual flight; window statistics p0/pa
                # remain unchanged for the congestion update below.
                pto = _tlp_pto(actual_flight_size)
                flight_p0 = (1.0 - p_drop) ** actual_flight_size
                p_rack = max(0.0, (1.0 - p_drop) - flight_p0)
                p_tlp_single = ((1.0 - p_drop) ** max(0, actual_flight_size - 1)) * p_drop
                p_tlp_multi = max(0.0, p_drop - p_tlp_single)
                dt_tlp_single = pto + p_probe_ok * RTT + p_probe_fail * RTO_MIN
                dt_tlp_multi = pto + p_probe_ok * (2.0 * RTT) + p_probe_fail * RTO_MIN
                dt_zero_fwd = (1.0 - p_drop) * RTT + p_drop * dt_tlp_single
                E_dt_nominal = (flight_p0 * dt_zero_fwd
                                + p_rack * dt_rack
                                + p_tlp_single * dt_tlp_single
                                + p_tlp_multi * dt_tlp_multi)
                # Under RACK-TLP, full RTO reset to cwnd=1 occurs when the entire flight
                # AND its TLP probe round-trip fail (pa * p_probe_fail)
                p_rto = pa * p_probe_fail
                p_fast_or_tlp = max(0.0, (1.0 - p0) - p_rto)

            serialized_segments = E_del if is_none else float(actual_flight_size)
            E_dt = max(serialized_segments * SER, E_dt_nominal)

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

            # Flight-aggregated newly ACKed segment credit: a full window
            # contributes one segment, a partial flight contributes proportionally less.
            w_reno = cwnd + (actual_flight_size / max(1.0, cwnd))
            w_no   = max(_cubic_w(t_since, w_max), w_reno)

            cwnd_next = p0 * w_no + p_fast_or_tlp * (cwnd * CUBIC_B) + p_rto * 1.0
            cwnd = max(2.0, min(cwnd_next, LOCAL_MAX_CWND))
            flt += 1

    ack_times_ixp, ack_times_sender, quickacks_left = _compute_delayed_ack_times(
        times_dest, max_k, is_new=is_new, state=state, start_time=start_time, flts=flts, ss_max_k=ss_max_k)

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
                           last_send_time=last_send_time, last_ack_time=last_ack_time,
                           quickacks_left=quickacks_left)
    return times_ixp, times_dest, ack_times_ixp, ack_times_sender, flts, total_el, final_state

# ─────────────────────── Public API ───────────────────────

_cache: dict = {}

def simulate_transfer(num_segments, is_new=True, state=None, *, start_time):
    """
    Simulates transmission of num_segments, returning
    (times_ixp, times_dest, ack_times_ixp, ack_times_sender, final_state).
    For new connections (is_new=True), prepends the 5 forward handshake packet
    timestamps to times_ixp/times_dest and the 4 reverse handshake packet
    timestamps to ack_times_ixp/ack_times_sender.
    """
    t_ixp, t_dest, ack_ixp, ack_sender, _, _, final_state = _build_timeline(
        num_segments, is_new=is_new, state=state, start_time=start_time)
    ack_ixp_slice = ack_ixp[1:num_segments + 1]
    ack_sender_slice = ack_sender[1:num_segments + 1]
    return (
        np.concatenate((hs_times(OWD1, is_new), t_ixp[1:num_segments + 1])),
        np.concatenate((hs_times(OWD, is_new), t_dest[1:num_segments + 1])),
        np.concatenate((hs_ack_times(OWD2, is_new), ack_ixp_slice[np.isfinite(ack_ixp_slice)])),
        np.concatenate((hs_ack_times(OWD, is_new), ack_sender_slice[np.isfinite(ack_sender_slice)])),
        final_state,
    )

def expected_time_k(k, max_k=None):
    """Returns (t_ixp, t_dest, t_ack_ixp, t_ack_sender, flight_id) for segment k."""
    global _cache
    target_n = max(int(max_k), k) if max_k is not None else max(2000, k + 500)
    cached_max_k = _cache.get('max_k')
    if ('times_dest' not in _cache
            or (max_k is not None and cached_max_k != target_n)
            or (max_k is None and (cached_max_k is not None or k >= len(_cache['times_dest'])))):
        t_ixp, t_dest, ack_ixp, ack_sender, f, el, _ = _build_timeline(target_n)
        _cache = {
            'max_k': target_n if max_k is not None else None,
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
