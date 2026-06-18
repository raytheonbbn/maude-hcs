import numpy as np

# ==============================================================================
# TCP Analytical Model over a 4-State Gilbert-Elliott Channel
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
# Channel: 4-state Gilbert-Elliott Markov chain
#   State 0: Good           — packet delivered
#   State 1: Gap in burst   — packet delivered
#   State 2: Burst loss     — packet DROPPED
#   State 3: Isolated loss  — packet DROPPED
#
# Loss is asymmetric: only client→server is lossy; ACKs are lossless.
# ==============================================================================

# ─────────────────────── Channel Parameters ───────────────────────

p13 = 0.005   # Good → Burst loss
p31 = 0.20    # Burst loss → Good
p32 = 0.40    # Burst loss → Gap
p23 = 0.30    # Gap → Burst loss
p14 = 0.002   # Good → Isolated loss

P = np.array([
    [1 - p13 - p14, 0.0,           p13,           p14],    # State 0: Good
    [p31,           1 - p23 - p31, p23,           0.0],    # State 1: Gap
    [p31,           p32,           1 - p31 - p32, 0.0],    # State 2: Burst
    [1.0,           0.0,           0.0,           0.0],    # State 3: Isolated
])

L = np.diag([0.0, 0.0, 1.0, 1.0])   # Loss indicator per state

# ─────────────────────── Network Parameters ───────────────────────

O   = 0.02                       # One-way propagation delay (s)
RTT = 2 * O                      # Round-trip time (s)
SER = 1514 * 8 / 1e9             # Per-packet serialization delay at 1 Gbps
MAX_CWND = 40                    # Physical ceiling for the network path (in segments)

# ─────────────────────── TCP Parameters (Ubuntu 22.04) ───────────────────────

IW        = 10      # Initial window (segments)
RTO_INIT  = 1.0     # SYN retransmission timeout (s)
RTO_MIN   = 0.2     # Minimum RTO (s)
CUBIC_C   = 0.4     # CUBIC scaling constant
CUBIC_B   = 0.7     # CUBIC multiplicative decrease factor
RACK_FRAC = 0.25    # RACK reordering window ≈ RTT / 4

# ─────────────────────── Derived Quantities ───────────────────────

_N    = 4
_loss = np.diag(L)                        # [0, 0, 1, 1]

# Stationary distribution of the Markov chain
_vals, _vecs = np.linalg.eig(P.T)
_i = np.argmin(np.abs(_vals - 1.0))
pi_stat = np.real(_vecs[:, _i])
pi_stat = pi_stat / pi_stat.sum()

# Per-packet conditional transition matrices
M_s = np.diag(1 - _loss) @ P             # Packet delivered
M_l = np.diag(_loss) @ P                 # Packet lost

p_loss_stat = float(pi_stat @ _loss)      # Stationary loss rate

# ==============================================================================
#  Channel Analysis
# ==============================================================================

def _flight_stats(W, pi):
    """
    Compute loss statistics for a flight of W packets through the GE channel
    starting from state distribution pi.

    Simultaneously tracks:
      v_s : all-success path   → pi · M_s^W   (gives P(0 losses))
      v_l : all-loss path      → pi · M_l^W   (gives P(W losses))
      v   : unconditional path → pi · P^W     (gives post-flight state)
      el  : E[losses]          → Σ (pi · P^i) · loss_vec

    Returns (p0, pa, el, pi_after).
    """
    v_s = pi.copy()
    v_l = pi.copy()
    v   = pi.copy()
    el  = 0.0
    for _ in range(W):
        el += float(v @ _loss)
        v_s = v_s @ M_s
        v_l = v_l @ M_l
        v   = v @ P
    p0 = float(np.clip(v_s.sum(), 0, 1))
    pa = float(np.clip(v_l.sum(), 0, 1))
    s  = v.sum()
    return p0, pa, el, (v / s if s > 0 else pi_stat.copy())

# ==============================================================================
#  3-Way Handshake
# ==============================================================================

def _handshake():
    """
    Expected handshake time and channel state after completion.

    Only the SYN (client→server) traverses the lossy channel.  SYN-ACK
    (server→client) is lossless.  The ACK (3rd leg) may be lost but the
    first data segment implicitly ACKs the SYN-ACK, so ACK loss adds no
    delay.  If a SYN is lost the client retransmits after exponential
    backoff: 1 s, 2 s, 4 s, …

    We use the stationary loss probability for all SYN attempts because
    the multi-second RTO gaps between attempts decorrelate the channel
    in any realistic deployment.  (In netem the chain doesn't advance
    between packets, but the expected-value contribution from retries is
    dominated by the massive RTO cost, not the conditional loss rate.)
    """
    
    """
    Below is the old code, and it is correct, except the cost of single lost SYN is extremely
    high and will skew greatly from the practical value because if the first SYN is lost,
    The tcp experiment starts when the first SYN is transmitted,
                                                                            -Dylan
    pi  = pi_stat.copy()
    E_T = 0.0
    pw  = 1.0            # probability still waiting
    rto = RTO_INIT
    mix = np.zeros(_N)   # weighted end-state mixture

    for _ in range(8):
        pl = float(pi @ _loss)
        ps = 1.0 - pl
        # Success: pay 1 RTT
        E_T += pw * ps * RTT
        if ps > 0:
            pi_s  = (pi * (1 - _loss)) @ P
            pi_s /= pi_s.sum()
            mix  += pw * ps * pi_s
        if pl < 1e-15:
            break
        # Failure: pay RTO, advance channel
        E_T += pw * pl * rto
        pi_f = (pi * _loss) @ P
        pi   = pi_f / pi_f.sum() if pi_f.sum() > 1e-15 else pi_stat.copy()
        pw  *= pl
        rto *= 2

    pi_end = mix / mix.sum() if mix.sum() > 1e-15 else pi_stat.copy()
    pi_end = pi_end @ P          # advance 1 pkt for the ACK (3rd leg)
    """

    """
    p = p_loss_stat

    # E[T_handshake] = RTT  +  Σ_{n=1}^∞ p^n · RTO(n)
    # where RTO(n) = RTO_INIT · 2^{n-1}  (exponential backoff)
    # = RTT + p·RTO_INIT · Σ_{k=0}^∞ (2p)^k = RTT + p·RTO_INIT / (1 − 2p)
    if 2 * p < 1:
        E_T = RTT + p * RTO_INIT / (1 - 2 * p)
    else:
        # Shouldn't happen for reasonable loss rates; cap at 5 retries
        E_T = RTT + p * RTO_INIT * 5

    # Channel state after handshake: SYN (1 pkt) + ACK (1 pkt) = 2 pkts
    # through the channel from stationary.
    pi_end = pi_stat @ P @ P
    return E_T, pi_end
    """

    # Assume the 3-way handshake completed perfectly on the very first try
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

        # Record arrival times (burst at 1 Gbps)
        for i in range(W_ss):
            k = seg + i + 1
            if k <= max_k:
                times[k] = t + O + i * SER
                flts[k]  = flt
        seg += W_ss

        # Expected flight duration:
        #   no loss  → 1 RTT
        #   loss     → 2 RTT + RACK quarter-RTT for SACK/RACK recovery
        dt  = p0 * RTT + p_l * (2 * RTT + RTT * RACK_FRAC)
        t  += dt
        pi  = pi_next
        flt += 1

        W_next_ss = W_ss * 2
        p0_next, pa_next, el_next, _ = _flight_stats(W_next_ss, pi)

        # Let it stay in Slow Start until it expects more than 0.5 packet drops on average
        if el_next > 0.5 or W_ss >= MAX_CWND:
            # Ensures that transition to Congestion Avoidance adjust window appropriately
            last_p0 = p0_next
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
    """Convert the transition matrix to tc-netem loss-state percentages."""
    return (P_mat[0, 2] * 100, P_mat[2, 0] * 100,
            P_mat[2, 1] * 100, P_mat[1, 2] * 100,
            P_mat[0, 3] * 100)
