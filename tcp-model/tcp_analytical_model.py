import numpy as np

# ==============================================================================
# TCP Analytical Model over Two Cascaded Bidirectional 16-State Links
# ==============================================================================
#
# Computes E[T_k]: expected arrival time of the k-th TCP data segment at the
# server, measured from the client's first SYN transmission across two links.
#
# Models TCP as implemented in Ubuntu 22.04 (Linux 5.15+):
#   - CUBIC congestion control (default)
#   - SACK (Selective Acknowledgment)
#   - RACK-TLP (Recent ACK / Tail Loss Probe) loss detection
#   - Slow Start and Congestion Avoidance
#
# Multi-Hop Architecture:
#   - Evaluates Link 1 (e.g. Wi-Fi/Access) and Link 2 (e.g. Core/Backhaul)
#   - Maintains independent 16-state vectors for each link
#   - Traverses flights sequentially without requiring 256-state expansion
# ==============================================================================

PROFILES = {
    "none":      {"p13": 0.0,     "p31": 1.0,  "p32": 0.0,  "p23": 0.0,  "p14": 0.0},
    "excellent": {"p13": 0.0005,  "p31": 0.50, "p32": 0.10, "p23": 0.20, "p14": 0.0001},
    "good":      {"p13": 0.002,   "p31": 0.35, "p32": 0.15, "p23": 0.30, "p14": 0.0005},
    "fair":      {"p13": 0.005,   "p31": 0.20, "p32": 0.40, "p23": 0.30, "p14": 0.002},
    "poor":      {"p13": 0.015,   "p31": 0.15, "p32": 0.25, "p23": 0.50, "p14": 0.005},
    "bad":       {"p13": 0.04,    "p31": 0.10, "p32": 0.30, "p23": 0.60, "p14": 0.015}
}

class Link16State:
    """Represents a single 16-state bidirectional Gilbert-Elliott link."""
    def __init__(self, p13, p31, p32, p23, p14):
        self.P_base = np.array([
            [1 - p13 - p14, 0.0,           p13,           p14],
            [p31,           1 - p23 - p31, p23,           0.0],
            [p31,           p32,           1 - p31 - p32, 0.0],
            [1.0,           0.0,           0.0,           0.0],
        ])
        self.L_base = np.array([0.0, 0.0, 1.0, 1.0])
        
        # 16-state joint matrix
        self.P = np.kron(self.P_base, self.P_base)
        self.L_fwd = np.kron(self.L_base, np.ones(4))
        self.L_rev = np.kron(np.ones(4), self.L_base)
        
        self.M_fwd_ok = np.diag(1.0 - self.L_fwd) @ self.P
        self.M_fwd_drop = np.diag(self.L_fwd) @ self.P
        self.M_rev_ok = np.diag(1.0 - self.L_rev) @ self.P
        self.M_rev_drop = np.diag(self.L_rev) @ self.P
        
        # Stationary distribution
        vals_b, vecs_b = np.linalg.eig(self.P_base.T)
        i_b = np.argmin(np.abs(vals_b - 1.0))
        pi_base = np.real(vecs_b[:, i_b])
        pi_base /= pi_base.sum()
        self.pi_stat = np.kron(pi_base, pi_base)

    def flight_stats(self, W, pi):
        """Evaluates a flight of W packets through this single 16-state link."""
        v_fwd_ok = pi.copy()
        v_fwd_drop = pi.copy()
        v_after_fwd = pi.copy()
        el_fwd = 0.0

        for _ in range(W):
            el_fwd += float(v_after_fwd @ self.L_fwd)
            v_fwd_ok = v_fwd_ok @ self.M_fwd_ok
            v_fwd_drop = v_fwd_drop @ self.M_fwd_drop
            v_after_fwd = v_after_fwd @ self.P

        v_rev_ok = v_fwd_ok.copy()
        v_rev_drop = v_after_fwd.copy()
        v_after_rev = v_after_fwd.copy()
        el_rev = 0.0

        for _ in range(W):
            el_rev += float(v_after_rev @ self.L_rev)
            v_rev_ok = v_rev_ok @ self.M_rev_ok
            v_rev_drop = v_rev_drop @ self.M_rev_drop
            v_after_rev = v_after_rev @ self.P

        p0 = float(np.clip(v_rev_ok.sum(), 0, 1))
        p_fwd_fail = float(np.clip(v_fwd_drop.sum(), 0, 1))
        p_rev_fail = float(np.clip(v_rev_drop.sum(), 0, 1))
        pa = float(np.clip(p_fwd_fail + (1.0 - p_fwd_fail) * p_rev_fail, 0, 1))
        
        s = v_after_rev.sum()
        pi_next = v_after_rev / s if s > 0 else self.pi_stat.copy()
        return p0, pa, el_fwd, el_rev, pi_next


class MultiHopPath:
    """Chains Link 1 and Link 2 without expanding the state space to 256 states."""
    def __init__(self, link1: Link16State, link2: Link16State):
        self.link1 = link1
        self.link2 = link2

    def flight_stats_path(self, W, pi1, pi2):
        # Pass sequentially through Hop 1 then Hop 2
        p0_1, pa_1, el_fwd_1, el_rev_1, pi1_next = self.link1.flight_stats(W, pi1)
        p0_2, pa_2, el_fwd_2, el_rev_2, pi2_next = self.link2.flight_stats(W, pi2)

        # End-to-end combinations
        p0_total = p0_1 * p0_2
        pa_total = pa_1 + (1.0 - pa_1) * pa_2
        el_fwd_total = el_fwd_1 + el_fwd_2
        el_total = el_fwd_total + el_rev_1 + el_rev_2

        # Intermediate attribution
        hop_attribution = {
            "link1_drop_prob": 1.0 - p0_1,
            "link2_drop_prob": p0_1 * (1.0 - p0_2),
            "e2e_success_prob": p0_total
        }

        return p0_total, pa_total, el_fwd_total, el_total, pi1_next, pi2_next, hop_attribution


# ─────────────────────── Network Parameters ───────────────────────

O   = 0.02                       # Total path one-way propagation delay (s)
RTT = 2 * O                      # Round-trip time (s)
SER = 1514 * 8 / 1e9             # Per-packet serialization delay at 1 Gbps
MAX_CWND = 60                    # Physical ceiling for the network path
BUFFER_CAPACITY = 55             # Physical limit where tail-drop loss occurs

# ─────────────────────── TCP Parameters ───────────────────────

IW        = 10
RTO_MIN   = 0.2
CUBIC_C   = 0.4
CUBIC_B   = 0.7
RACK_FRAC = 0.25

# ─────────────────────── Global Path Setup ───────────────────────

_ACTIVE_PROFILE_NAME = "fair"
_link1 = Link16State(**PROFILES["fair"])
_link2 = Link16State(**PROFILES["fair"])
_path = MultiHopPath(_link1, _link2)

def set_active_profile(profile_name_l1, profile_name_l2=None):
    """Set distinct profiles for Link 1 and Link 2."""
    global _link1, _link2, _path, _cache, _ACTIVE_PROFILE_NAME
    if profile_name_l2 is None:
        profile_name_l2 = profile_name_l1
        
    _ACTIVE_PROFILE_NAME = profile_name_l1
    _link1 = Link16State(**PROFILES[profile_name_l1])
    _link2 = Link16State(**PROFILES[profile_name_l2])
    _path = MultiHopPath(_link1, _link2)
    _cache.clear()

def _cubic_w(t, w_max):
    K = ((1 - CUBIC_B) * w_max / CUBIC_C) ** (1.0 / 3.0)
    return max(1.0, CUBIC_C * (t - K) ** 3 + w_max)

# ─────────────────────── Timeline Generation ───────────────────────

def _build_timeline(max_k=2000):
    global _ACTIVE_PROFILE_NAME
    
    times = np.full(max_k + 1, np.nan)
    flts  = np.zeros(max_k + 1, dtype=int)
    times[0] = 0.0
    total_el = 0.0

    # Phase 1: Handshake
    t = RTT
    pi1 = _link1.pi_stat @ _link1.P @ _link1.P
    pi2 = _link2.pi_stat @ _link2.P @ _link2.P
    seg = 0
    flt = 1

    # Phase 2: Slow Start
    LOCAL_MAX_CWND = 50 if _ACTIVE_PROFILE_NAME != "none" else MAX_CWND
    W_ss = IW
    last_p0 = 1.0

    while seg < max_k:
        p0, pa, el_fwd, _, pi1_next, pi2_next, attr = _path.flight_stats_path(W_ss, pi1, pi2)
        p_l = 1.0 - p0

        if _ACTIVE_PROFILE_NAME == "none" and (seg + W_ss > BUFFER_CAPACITY):
            dropped_packets = (seg + W_ss) - BUFFER_CAPACITY
            p_l = dropped_packets / W_ss
            p0 = 1.0 - p_l
            total_el += float(dropped_packets)
        else:
            total_el += el_fwd

        current_flight_size = min(int(W_ss), LOCAL_MAX_CWND)

        for i in range(current_flight_size):
            k = seg + i + 1
            if k <= max_k:
                times[k] = t + O + i * SER
                flts[k]  = flt
        seg += current_flight_size

        dt_recovery = (2 * RTT + RTT * RACK_FRAC) * (0.5 if _ACTIVE_PROFILE_NAME == "none" else 1.0)
        dt = p0 * RTT + p_l * dt_recovery
        t += dt
        pi1, pi2 = pi1_next, pi2_next
        flt += 1

        W_next_ss = min(W_ss * 2, LOCAL_MAX_CWND)
        p0_next, _, el_fwd_next, _, _, _, _ = _path.flight_stats_path(W_next_ss, pi1, pi2)

        if el_fwd_next > 0.5 or p_l > 0.0 or current_flight_size >= LOCAL_MAX_CWND:
            last_p0 = p0_next if p_l == 0.0 else p0
            break
        W_ss = W_next_ss

    # Transition to CA
    p_l_last = 1.0 - last_p0
    cwnd = max(2.0, min(last_p0 * (W_ss * 2) + p_l_last * max(W_ss * CUBIC_B, 2.0), LOCAL_MAX_CWND))
    w_max = min(cwnd / CUBIC_B, LOCAL_MAX_CWND)
    t_since = 0.0

    # Phase 3: Congestion Avoidance
    for _ in range(100_000):
        if seg >= max_k:
            break

        W = max(1, int(round(cwnd)))
        p0, pa, el_fwd, _, pi1_next, pi2_next, attr = _path.flight_stats_path(W, pi1, pi2)

        if _ACTIVE_PROFILE_NAME == "none" and W > BUFFER_CAPACITY and W > int(round(w_max)):
            ca_dropped = W - BUFFER_CAPACITY
            p_l_ca = ca_dropped / W
            p0 = max(0.0, 1.0 - p_l_ca)
            pa = 0.0
            total_el += float(ca_dropped)
        else:
            total_el += el_fwd

        pp = max(0.0, 1.0 - p0 - pa)
        E_del = W * (LOCAL_MAX_CWND / max(1.0, cwnd))

        seg_start = int(np.floor(seg))
        seg_end   = int(np.floor(seg + E_del))

        E_dt_nominal = p0 * RTT + pp * (2 * RTT + RTT * RACK_FRAC) + pa * RTO_MIN
        E_dt = max(E_del * SER, E_dt_nominal * (E_del / LOCAL_MAX_CWND))

        for k_idx in range(seg_start + 1, seg_end + 1):
            if k_idx <= max_k:
                fractional_offset = (k_idx - 1 - seg_start) / max(1.0, E_del)
                times[k_idx] = t + O + (fractional_offset * W * SER)
                flts[k_idx]  = flt

        seg += E_del
        t   += E_dt
        pi1, pi2 = pi1_next, pi2_next

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

    return times, flts, total_el

# ─────────────────────── Public API ───────────────────────

_cache: dict = {}

def expected_time_k(k):
    global _cache
    if 'times' not in _cache or k >= len(_cache['times']):
        n = max(2000, k + 500)
        t, f, el = _build_timeline(n)
        _cache = {'times': t, 'flights': f, 'total_el': el}
    if k <= 0:
        return 0.0, 0
    return float(_cache['times'][k]), int(_cache['flights'][k])

def get_total_retransmissions():
    global _cache
    if 'total_el' in _cache:
        return float(_cache['total_el'])
    return 0.0