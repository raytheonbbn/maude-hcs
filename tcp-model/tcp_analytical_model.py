import numpy as np

# ==============================================================================
# TCP Analytical Model over Two Cascaded Bidirectional IID Loss Links
# ==============================================================================
#
# Computes E[T_k]: expected arrival time of the k-th TCP data segment at both:
#   1. First-hop intermediate node (e.g. Router / IXP)
#   2. Final destination server
# measured from the client's first SYN transmission across two links.
#
# Models TCP as implemented in Ubuntu 22.04 (Linux 5.15+):
#   - CUBIC congestion control (default)
#   - SACK (Selective Acknowledgment)
#   - RACK-TLP (Recent ACK / Tail Loss Probe) loss detection
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

IW        = 10
RTO_MIN   = 0.2
CUBIC_C   = 0.4
CUBIC_B   = 0.7
RACK_FRAC = 0.25

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

# ─────────────────────── Timeline Generation ───────────────────────

def _build_timeline(max_k=2000):
    times_first = np.full(max_k + 1, np.nan)
    times_dest  = np.full(max_k + 1, np.nan)
    flts        = np.zeros(max_k + 1, dtype=int)
    
    times_first[0] = 0.0
    times_dest[0]  = 0.0
    total_el = 0.0

    # Phase 1: Handshake (TCP 3-way HS + TLS HS completes at t = 2 * RTT; App Data starts at t = 2 * RTT)
    t = 2.0 * RTT
    seg = 0
    flt = 1

    # Phase 2: Slow Start
    LOCAL_MAX_CWND = 1000
    W_ss = IW
    last_p0 = 1.0
    is_none = _path.drop_prob <= 1e-10

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

        for i in range(current_flight_size):
            k = seg + i + 1
            if k <= max_k:
                # Arrival at First Hop (Link 1) vs Final Destination (Link 1 + Link 2)
                times_first[k] = t + OWD1 + i * SER1
                times_dest[k]  = t + OWD  + i * SER
                flts[k]        = flt
        seg += current_flight_size

        dt_recovery = (2.0 * RTT + RTT * RACK_FRAC) * (0.5 if is_none else 1.0)
        dt = p0 * RTT + p_l * dt_recovery
        t += dt
        flt += 1

        W_next_ss = min(W_ss * 2, LOCAL_MAX_CWND)
        p0_next, _, el_fwd_next, _ = _path.flight_stats_path(W_next_ss)

        if el_fwd_next >= 0.5 or (seg + W_ss > BUFFER_CAPACITY) or current_flight_size >= LOCAL_MAX_CWND:
            last_p0 = p0_next if p_l == 0.0 else p0
            break
        W_ss = W_next_ss

    # Transition to CA
    p_l_last = 1.0 - last_p0
    cwnd = max(2.0, min(last_p0 * float(W_ss * 2) + p_l_last * max(float(W_ss) * CUBIC_B, 2.0), LOCAL_MAX_CWND))
    w_max = min(cwnd / CUBIC_B, LOCAL_MAX_CWND)
    t_since = 0.0

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

        E_dt_nominal = p0 * RTT + pp * (2.0 * RTT + RTT * RACK_FRAC) + pa * RTO_MIN
        E_dt = max(E_del * SER, E_dt_nominal)

        for k_idx in range(seg_start + 1, seg_end + 1):
            if k_idx <= max_k:
                fractional_offset = (k_idx - 1 - seg_start) / max(1.0, E_del)
                times_first[k_idx] = t + OWD1 + (fractional_offset * W * SER1)
                times_dest[k_idx]  = t + OWD  + (fractional_offset * W * SER)
                flts[k_idx]        = flt

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

        cwnd_next = p0 * w_no + pp * (cwnd * CUBIC_B) + pa * 1.0
        cwnd = max(2.0, min(cwnd_next, LOCAL_MAX_CWND))
        flt += 1

    return times_first, times_dest, flts, total_el

# ─────────────────────── Public API ───────────────────────

_cache: dict = {}

def expected_time_k(k):
    """Returns (t_first_hop, t_destination, flight_id) for segment k."""
    global _cache
    if 'times_dest' not in _cache or k >= len(_cache['times_dest']):
        n = max(2000, k + 500)
        t_first, t_dest, f, el = _build_timeline(n)
        _cache = {
            'times_first': t_first,
            'times_dest': t_dest,
            'flights': f,
            'total_el': el
        }
    if k <= 0:
        return 0.0, 0.0, 0
    return (
        float(_cache['times_first'][k]),
        float(_cache['times_dest'][k]),
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