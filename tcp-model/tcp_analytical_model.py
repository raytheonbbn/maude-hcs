import numpy as np

# ==============================================================================
# TCP Analytical Model over a Bidirectional 4-State Gilbert-Elliott Channel
# ==============================================================================
#
# Computes E[T_k]: expected arrival time of the k-th TCP data segment at the
# server, measured from the client's first SYN transmission.
#
# Models TCP as implemented in Ubuntu 22.04 (Linux 5.15+):
#   - CUBIC congestion control (default)
#   - SACK (Selective Acknowledgment)
#   - RACK-TLP (Recent ACK / Tail Loss Probe) loss detection
#   - 3-way handshake with SYN retransmission & exponential backoff
#   - Slow Start (cwnd doubles per RTT, exits on first loss)
#   - Congestion Avoidance (CUBIC + Reno friendliness)
#   - Fast Retransmit / Fast Recovery via SACK
#   - Retransmission Timeout (RTO) on complete flight loss
#
# Channel: Bidirectional 4-state Gilbert-Elliott Markov chain
#   State 0: Good           — packet delivered
#   State 1: Gap in burst   — packet delivered
#   State 2: Burst loss     — packet DROPPED
#   State 3: Isolated loss  — packet DROPPED
#
# Loss is symmetric: applied in both the forward (data) and reverse (ACK) paths.
# ==============================================================================

# ─────────────────────── Channel Parameters ───────────────────────

p13 = 0.005   # Good → Burst loss
p31 = 0.20    # Burst loss → Good
p32 = 0.40    # Burst loss → Gap
p23 = 0.30    # Gap → Burst loss
p14 = 0.002   # Good → Isolated loss

# Base 4-state Markov transition matrix for a single path direction
P_base = np.array([
    [1 - p13 - p14, 0.0,           p13,           p14],    # State 0: Good
    [p31,           1 - p23 - p31, p23,           0.0],    # State 1: Gap
    [p31,           p32,           1 - p31 - p32, 0.0],    # State 2: Burst
    [1.0,           0.0,           0.0,           0.0],    # State 3: Isolated
])

L_base = np.array([0.0, 0.0, 1.0, 1.0])   # Loss indicator vector per single path state

# Construct the joint 16-state Kronecker product environment representing (Forward, Reverse) states
P = np.kron(P_base, P_base)

# Loss matrices mapping independent path interactions
# Joint state space index mapped as: (fwd_state * 4) + rev_state
L_fwd = np.kron(L_base, np.ones(4))
L_rev = np.kron(np.ones(4), L_base)

# ─────────────────────── Network Parameters ───────────────────────

O   = 0.02                       # One-way propagation delay (s)
RTT = 2 * O                      # Round-trip time (s)
SER = 1514 * 8 / 1e9             # Per-packet serialization delay at 1 Gbps
MAX_CWND = 60                    # Physical ceiling for the network path (in segments)
BUFFER_CAPACITY = 55             # Physical limit where tail-drop loss occurs

# ─────────────────────── TCP Parameters (Ubuntu 22.04) ───────────────────────

IW        = 10      # Initial window (segments)
RTO_INIT  = 1.0     # SYN retransmission timeout (s)
RTO_MIN   = 0.2     # Minimum RTO (s)
CUBIC_C   = 0.4     # CUBIC scaling constant
CUBIC_B   = 0.7     # CUBIC multiplicative decrease factor
RACK_FRAC = 0.25    # RACK reordering window ≈ RTT / 4

# ─────────────────────── Derived Quantities ───────────────────────

_N    = 16

# Compute stationary distributions for single path to find baseline roots
_vals_b, _vecs_b = np.linalg.eig(P_base.T)
_i_b = np.argmin(np.abs(_vals_b - 1.0))
pi_stat_base = np.real(_vecs_b[:, _i_b])
pi_stat_base = pi_stat_base / pi_stat_base.sum()

# The stationary distribution of the joint 16-state matrix
pi_stat = np.kron(pi_stat_base, pi_stat_base)

# Step execution operators tracking delivery over both independent paths
# For data to succeed: forward must deliver. For ACK to succeed: reverse must deliver.
M_fwd_ok = np.diag(1.0 - L_fwd) @ P
M_fwd_drop = np.diag(L_fwd) @ P

M_rev_ok = np.diag(1.0 - L_rev) @ P
M_rev_drop = np.diag(L_rev) @ P

p_loss_stat = float(pi_stat_base @ L_base)      # Stationary single-path loss rate

# ─────────────────────── Profile Switching Scaffolding ───────────────────────
PROFILES = {
    "none":      {"p13": 0.0,     "p31": 1.0,  "p32": 0.0,  "p23": 0.0,  "p14": 0.0},
    "excellent": {"p13": 0.0005,  "p31": 0.50, "p32": 0.10, "p23": 0.20, "p14": 0.0001},
    "good":      {"p13": 0.002,   "p31": 0.35, "p32": 0.15, "p23": 0.30, "p14": 0.0005},
    "fair":      {"p13": 0.005,   "p31": 0.20, "p32": 0.40, "p23": 0.30, "p14": 0.002},
    "poor":      {"p13": 0.015,   "p31": 0.15, "p32": 0.25, "p23": 0.50, "p14": 0.005},
    "bad":       {"p13": 0.04,    "p31": 0.10, "p32": 0.30, "p23": 0.60, "p14": 0.015}
}

def set_active_profile(profile_name):
    """Dynamically swap global matrices to reflect target loss configurations profile definitions."""
    global P_base, P, M_fwd_ok, M_fwd_drop, M_rev_ok, M_rev_drop, pi_stat, p_loss_stat, _cache
    if profile_name not in PROFILES:
        return
    prof = PROFILES[profile_name]
    _p13, _p31, _p32, _p23, _p14 = prof["p13"], prof["p31"], prof["p32"], prof["p23"], prof["p14"]
    
    P_base = np.array([
        [1 - _p13 - _p14, 0.0,           _p13,           _p14],
        [_p31,           1 - _p23 - _p31, _p23,           0.0],
        [_p31,           _p32,           1 - _p31 - _p32, 0.0],
        [1.0,           0.0,           0.0,           0.0],
    ])
    P = np.kron(P_base, P_base)
    
    _vals_b, _vecs_b = np.linalg.eig(P_base.T)
    _i_b = np.argmin(np.abs(_vals_b - 1.0))
    pi_stat_base = np.real(_vecs_b[:, _i_b])
    pi_stat_base = pi_stat_base / pi_stat_base.sum()
    pi_stat = np.kron(pi_stat_base, pi_stat_base)
    
    M_fwd_ok = np.diag(1.0 - L_fwd) @ P
    M_fwd_drop = np.diag(L_fwd) @ P
    M_rev_ok = np.diag(1.0 - L_rev) @ P
    M_rev_drop = np.diag(L_rev) @ P
    p_loss_stat = float(pi_stat_base @ L_base)
    _cache.clear()
# ─────────────────────────────────────────────────────────────────────────────

# ==============================================================================
#  Channel Analysis
# ==============================================================================

def _flight_stats(W, pi):
    """
    Compute loss statistics for a flight of W packets through the bidirectional
    GE channel starting from the 16-state joint distribution pi.

    Tracks:
      p0 : probability that all data packets and their ACKs arrive cleanly.
      pa : probability of complete RTO timeout. This occurs if either all data packets 
           fail the forward path, or if all returning ACKs fail the reverse path.
      el : expected total number of packet drop events seen on the path.
    """
    # 1. Forward Path execution (Data Segment delivery)
    v_fwd_all_ok = pi.copy()
    v_fwd_all_drop = pi.copy()
    v_after_fwd = pi.copy()
    el_fwd = 0.0

    for _ in range(W):
        el_fwd += float(v_after_fwd @ L_fwd)
        v_fwd_all_ok = v_fwd_all_ok @ M_fwd_ok
        v_fwd_all_drop = v_fwd_all_drop @ M_fwd_drop
        v_after_fwd = v_after_fwd @ P

    # 2. Reverse Path execution (ACK delivery tracking back)
    v_rev_all_ok = v_fwd_all_ok.copy()
    v_rev_all_drop = v_after_fwd.copy()  # ACKs are generated from whatever survived the forward path
    v_after_rev = v_after_fwd.copy()
    el_rev = 0.0

    for _ in range(W):
        el_rev += float(v_after_rev @ L_rev)
        v_rev_all_ok = v_rev_all_ok @ M_rev_ok
        v_rev_all_drop = v_rev_all_drop @ M_rev_drop
        v_after_rev = v_after_rev @ P

    p0 = float(np.clip(v_rev_all_ok.sum(), 0, 1))
    
    p_fwd_fail = float(np.clip(v_fwd_all_drop.sum(), 0, 1))
    p_rev_fail = float(np.clip(v_rev_all_drop.sum(), 0, 1))
    # Timeout hits if either direction encounters a complete flight block
    pa = float(np.clip(p_fwd_fail + (1.0 - p_fwd_fail) * p_rev_fail, 0, 1))
    
    el = el_fwd + el_rev
    s = v_after_rev.sum()
    
    return p0, pa, el, (v_after_rev / s if s > 0 else pi_stat.copy())

# ==============================================================================
#  3-Way Handshake
# ==============================================================================

def _handshake():
    """
    Assume the 3-way handshake completed perfectly on the very first try.
    Returns the baseline path propagation delays and synchronized end states.
    """
    return RTT, pi_stat @ P @ P

# ==============================================================================
#  CUBIC Window
# ==============================================================================

def _cubic_w(t, w_max):
    """W(t) = C·(t − K)³ + W_max,  K = ((1−β)·W_max / C)^{1/3}."""
    K = ((1 - CUBIC_B) * w_max / CUBIC_C) ** (1.0 / 3.0)
    return max(1.0, CUBIC_C * (t - K) ** 3 + w_max)

# ==============================================================================
#  Flight-by-Flight Timeline Builder
# ==============================================================================

def _build_timeline(max_k=2000):
    """
    Build E[T_k] for k = 1 … max_k.

    Phase 1 — Handshake
        Expected SYN exchange time with possible retransmissions.

    Phase 2 — Slow Start
        Window doubles each flight. Flight durations use probability-
        weighted RTT and SACK-recovery penalties from the GE model.
        SS ends when the per-flight loss probability exceeds 50%.

    Phase 3 — Congestion Avoidance (CUBIC)
        Expected-value model: for each flight the next cwnd is
            cwnd_next = p0·w_grow + p_partial·w_fast_rec + p_all·1
        Converges quickly to the CUBIC steady state.
    """
    times = np.full(max_k + 1, np.nan)
    flts  = np.zeros(max_k + 1, dtype=int)
    times[0] = 0.0

    # ── Phase 1: Handshake ──
    t_hs, pi = _handshake()
    t   = t_hs
    seg = 0
    flt = 1

    # ── Phase 2: Slow Start ──
    W_ss = IW
    last_p0 = 1.0

    while seg < max_k:
        p0, pa, el, pi_next = _flight_stats(W_ss, pi)
        p_l = 1.0 - p0  # Probability that Slow Start ends this flight

        # Check if the flight pushes total segments past the physical ceiling
        if seg + W_ss > BUFFER_CAPACITY:
            # The capacity is reached mid-flight, causing drops on the tail end
            dropped_packets = (seg + W_ss) - BUFFER_CAPACITY
            p_l = dropped_packets / W_ss
            p0 = 1.0 - p_l
            
        # Override loss probability if the flight exceeds buffer capacity
#        if W_ss > BUFFER_CAPACITY:
#            p_l = (W_ss - BUFFER_CAPACITY) / W_ss
#            p0 = 1.0 - p_l

        # 1. Clamp the flight size to ensure doubling doesn't overshoot MAX_CWND
        current_flight_size = min(int(W_ss), MAX_CWND)

        # Record arrival times (burst at 1 Gbps)
        for i in range(current_flight_size):
            k = seg + i + 1
            if k <= max_k:
                times[k] = t + O + i * SER
                flts[k]  = flt
        seg += current_flight_size

        # Tweaks the dt calculation to scale the recovery overhead for local buffers
        LOCAL_RECOVERY_FACTOR = 0.5  # Adjust this to damp the vertical overshoot
        
        # Expected flight duration uses the actual flight size sent
        #   no loss  → 1 RTT
        #   loss     → 2 RTT + RACK quarter-RTT for SACK/RACK recovery
        dt_loss = (2 * RTT + RTT * RACK_FRAC) * LOCAL_RECOVERY_FACTOR
        dt = p0 * RTT + p_l * dt_loss
        t += dt
        flt += 1

        # 2. Bound the next step evaluation by MAX_CWND
        W_next_ss = min(W_ss * 2, MAX_CWND)
        p0_next, pa_next, el_next, _ = _flight_stats(W_next_ss, pi)

        # Let it stay in Slow Start until it expects more than 0.5 packet drops on average
        # OR if we just explicitly forced a physical buffer overflow drop
        if el_next > 0.5 or p_l > 0.0 or current_flight_size >= MAX_CWND:
            # Ensures that transition to Congestion Avoidance adjust window appropriately
            last_p0 = p0_next if p_l == 0.0 else p0
            break
        W_ss = W_next_ss
        
    # ── Transition to CA ──
    # Expected post-SS cwnd weighted by last flight's loss probability
    p_l_last = 1.0 - last_p0
    cwnd = last_p0 * (W_ss * 2) + p_l_last * max(W_ss * CUBIC_B, 2.0)
    cwnd = max(2.0, cwnd)

    # Bound the initial window by the physical link ceiling
    cwnd = max(2.0, min(cwnd, MAX_CWND))

    # CUBIC state
    w_max   = min(cwnd / CUBIC_B, MAX_CWND)
    t_since = 0.0                 # time since last loss (CUBIC clock)
    
    # ── Phase 3: Congestion Avoidance ──
    for _ in range(100_000):
        if seg >= max_k:
            break

        W = max(1, int(round(cwnd)))
        p0, pa, el, pi_next = _flight_stats(W, pi)
        pp = max(0.0, 1.0 - p0 - pa)

        # 1. Scale the expected delivery step size to represent a full pipeline 
        # volume turnover. This stops the model from micro-stepping and 
        # compounding artificial loss boundaries.
        E_del = W * (MAX_CWND / max(1.0, cwnd))

        # 2. Map the continuous time step to the exact packet index boundaries
        seg_start = int(np.floor(seg))
        seg_end   = int(np.floor(seg + E_del))

        # Calculate the expected time step duration for this flight step
        #   p0 -> clean RTT
        #   pp -> SACK recovery overhead
        #   pa -> Complete loss forces a minimum RTO wait
        E_dt_nominal = p0 * RTT + pp * (2 * RTT + RTT * RACK_FRAC) + pa * RTO_MIN

        # Smoothly bound the time step by the physical serialization capacity.
        # As the window saturates, the continuous pipeline time-delta scales down
        # to match the wire-speed delivery rate instead of dropping to an idle pause.
        E_dt = max(E_del * SER, E_dt_nominal * (E_del / MAX_CWND))

        # Record arrival times for any packet boundary crossed during this flight step
        for k_idx in range(seg_start + 1, seg_end + 1):
            if k_idx <= max_k:
                # Interpolate sub-flight serialization delay across the continuous window
                fractional_offset = (k_idx - 1 - seg_start) / max(1.0, E_del)
                times[k_idx] = t + O + (fractional_offset * W * SER)
                flts[k_idx]  = flt

        # 3. Accumulate data progress precisely as a float
        seg += E_del
        t   += E_dt
        pi   = pi_next

        # ── Window dynamics (Executed using the elapsed epoch time) ──

        # 1. Update the CUBIC clock cleanly first
        p_loss_event = pp + pa
        if p_loss_event > 1e-15:
            # Shift the maximum window history proportionally based on loss probability
            w_max = (1.0 - p_loss_event) * w_max + p_loss_event * cwnd

            # Smoothly damp the expected time accumulation to reflect backoff probabilities
            t_since = (1.0 - p_loss_event) * (t_since + E_dt)
        else:
            # Advance the timeline clock cleanly by the epoch duration
            t_since += E_dt

        # 2. Let the window growth track the newly updated clock state
        w_reno = cwnd + (1.0 / max(1.0, cwnd))
        w_no   = max(_cubic_w(t_since, w_max), w_reno)

        # 3. Compute the smooth, blended window target across all 3 outcomes
        cwnd_next = p0 * w_no + pp * (cwnd * CUBIC_B) + pa * 1.0

        # 4. Enforce the physical path limits
        cwnd = max(2.0, min(cwnd_next, MAX_CWND))

        flt += 1

    return times, flts

# ==============================================================================
#  Public API
# ==============================================================================

_cache: dict = {}

def expected_time_k(k):
    """
    Expected arrival time of the k-th TCP data segment at the server,
    measured from the client's first SYN transmission.

    Returns (time_in_seconds, flight_number).
    """
    global _cache
    if 'times' not in _cache or k >= len(_cache['times']):
        n = max(2000, k + 500)
        t, f = _build_timeline(n)
        _cache = {'times': t, 'flights': f}
    if k <= 0:
        return 0.0, 0
    return float(_cache['times'][k]), int(_cache['flights'][k])


def get_tc_netem_params(P_mat, L_mat):
    """Convert the single-path transition matrix to tc-netem loss-state percentages."""
    # Netem setup pulls from baseline 4-state parameters to initialize individual interfaces
    return (np.clip(P_base[0, 2] * 100, 0.0, 100.0), np.clip(P_base[2, 0] * 100, 0.0, 100.0),
            np.clip(P_base[2, 1] * 100, 0.0, 100.0), np.clip(P_base[1, 2] * 100, 0.0, 100.0),
            np.clip(P_base[0, 3] * 100, 0.0, 100.0))
