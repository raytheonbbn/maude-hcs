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
        p_l = 1.0 - p0

        # Record arrival times (burst at 1 Gbps)
        for i in range(W_ss):
            k = seg + i + 1
            if k <= max_k:
                times[k] = t + O + i * SER
                flts[k]  = flt
        seg += W_ss
        last_p0 = p0

        # Expected flight duration:
        #   no loss  → 1 RTT
        #   loss     → 2 RTT + RACK quarter-RTT for SACK/RACK recovery
        dt  = p0 * RTT + p_l * (2 * RTT + RTT * RACK_FRAC)
        t  += dt
        pi  = pi_next
        flt += 1

        # Exit SS when loss is more likely than not in the next flight
        W_next_ss = W_ss * 2
        p0_peek, _, _, _ = _flight_stats(W_next_ss, pi)
        if (1 - p0_peek) > 0.5:
            break
        W_ss = W_next_ss

    # ── Transition to CA ──
    # Expected post-SS cwnd weighted by last flight's loss probability
    p_l_last = 1.0 - last_p0
    cwnd = last_p0 * (W_ss * 2) + p_l_last * max(W_ss * CUBIC_B, 2.0)
    cwnd = max(2.0, cwnd)

    # CUBIC state
    w_max   = cwnd / CUBIC_B      # infer W_max from post-loss cwnd
    t_since = 0.0                 # time since last loss (CUBIC clock)

    # ── Phase 3: Congestion Avoidance ──
    for _ in range(100_000):
        if seg >= max_k:
            break

        W = max(1, int(round(cwnd)))
        p0, pa, el, pi_next = _flight_stats(W, pi)
        pp = max(0.0, 1.0 - p0 - pa)

        # Segments delivered: partial loss recovers all W via SACK;
        # all-loss delivers 0 (RTO + retransmit in next epoch).
        E_del   = (p0 + pp) * W
        del_int = max(1, int(round(E_del)))

        # Epoch duration
        E_dt = (p0 * RTT
              + pp * (2 * RTT + RTT * RACK_FRAC)
              + pa * RTO_MIN)

        for i in range(del_int):
            k = seg + i + 1
            if k <= max_k:
                times[k] = t + O + i * SER
                flts[k]  = flt
        seg += del_int
        pi   = pi_next

        # ── Window dynamics ──
        t_since += E_dt

        # No-loss: CUBIC growth with Reno friendliness
        w_no = max(_cubic_w(t_since, w_max), cwnd + 1.0)
        # Partial loss: CUBIC multiplicative decrease (fast recovery)
        w_fr = max(cwnd * CUBIC_B, 2.0)
        # All loss: RTO resets cwnd to 1
        w_to = 1.0

        cwnd_next = p0 * w_no + pp * w_fr + pa * w_to

        # Update CUBIC state on loss events
        p_le = pp + pa
        if p_le > 1e-15:
            w_max   = p0 * w_max + p_le * cwnd   # blend W_max
            t_since = p0 * t_since                # proportional clock reset

        cwnd = max(1.0, cwnd_next)
        t   += E_dt
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
