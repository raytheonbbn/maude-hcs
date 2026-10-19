import numpy as np

# ==============================================================================
# The Mathematical Model & NumPy Implementation
# ==============================================================================

# 4-State Gilbert-Elliott Model Parameters (Realistic Aggressive Internet Loss)
# Models a congested link with ~1.2% overall loss, primarily driven by 2-3 packet tail-drops.
p13 = 0.005  # 0.5% chance to enter a burst loss (State 1 -> 3)
p31 = 0.20   # 20% chance to completely exit burst period (State 3 -> 1)
p32 = 0.40   # 40% chance to enter a successful gap within a burst (State 3 -> 2)
p23 = 0.30   # 30% chance to drop a packet again within a burst (State 2 -> 3)
p14 = 0.002  # 0.2% chance of isolated random drop (State 1 -> 4)

# The Exact Netem Macro-Model Transition Matrix
P = np.array([
    [1 - p13 - p14, 0.0,             p13,             p14], # State 1: Good
    [p31,           1 - p23 - p31,   p23,             0.0], # State 2: Good (Gap in Burst)
    [p31,           p32,             1 - p31 - p32,   0.0], # State 3: Bad (Burst Loss)
    [1.0,           0.0,             0.0,             0.0]  # State 4: Bad (Isolated Loss)
])
L = np.diag([0.0, 0.0, 1.0, 1.0])  # States 1 and 2 are lossless; 3 and 4 are lossy
D = np.array([[0.01], [0.02], [0.01], [0.05]])
O = 0.02  # 20ms one-way static propagation delay
IW = 10
RTO_init = 1.0
RTO = 0.2

# 1. Stationary Distribution (pi)
w, v = np.linalg.eig(P.T)
idx = np.argmin(np.abs(w - 1.0))
eigenvector = np.real(v[:, idx])
pi = (eigenvector / np.sum(eigenvector)).reshape(1, 4)

# 2. Stationary Loss (p_loss)
p_loss = np.dot(pi, np.dot(L, np.ones((4, 1))))[0, 0]

# 3. Success Matrix (P_succ)
P_succ = np.dot(np.eye(4) - L, P)

# 4. Base Setup Time (E[T_setup])
pi_D = np.dot(pi, D)[0, 0]
E_T_setup = 2 * O + pi_D + (p_loss / (1 - p_loss)) * RTO_init

# TCP Macroscopic Steady State (Padhye et al. with Timeout Penalties)
# To match the empirical mean under high loss, we MUST include the severe
# penalty of Retransmission Timeouts (RTO). The Padhye equation calculates
# the expected time between successful packet deliveries.
p_event = pi[0, 0] * (p13 + p14) + pi[0, 1] * p23

if p_event > 0:
    # CUBIC empirically maintains a larger window (approx 13 packets) 
    # before loss events force a recovery/timeout.
    W_aimd_cubic = np.sqrt(3.92 / p_event)
    W_steady = max(1, int(W_aimd_cubic * 1.5))
    
    # Expected time per packet 
    # 1. Base time is dominated by the time to push a window of packets: RTT / W_steady
    term1 = (2 * O + pi_D) / W_steady
    
    # 2. Timeout penalty (Padhye et al.)
    # Modern Linux uses TCP RACK and SACK which convert many traditional RTOs 
    # into timer-based Fast Retransmits. We apply a 50% mitigation factor to the RTO penalty.
    padhye_timeout_prob = min(1.0, 3.0 * np.sqrt((3 * p_event) / 8.0)) * p_event * (1 + 32 * (p_event**2))
    RACK_MITIGATION = 0.5
    term2 = (RTO * RACK_MITIGATION) * padhye_timeout_prob
    
    E_T_pkt = term1 + term2
else:
    W_steady = IW
    E_T_pkt = (2 * O + pi_D) / W_steady

# 5. Flight Functions
def expected_delay_flight(f):
    # Model slow start and congestion avoidance window size.
    # The congestion window starts at IW and doubles each round-trip time (flight)
    # during slow start, up to the steady-state window size (W_steady).
    W_f = min(W_steady, IW * (2 ** (f - 1)))
    
    # The expected flight delay is at least 1 RTT (2 * O + pi_D), plus any timeout delays.
    rtt = 2 * O + pi_D
    E_delta_f = max(rtt, W_f * E_T_pkt)
    return E_delta_f, W_f

# 6. Segment Calculation (E[T_k])
def expected_time_k(k):
    if k <= 0:
        return 0, 1
        
    # Realistic serialization delay for a 1 Gbps link
    # 1514 bytes (Ethernet frame) * 8 bits / 1,000,000,000 bps = ~0.01211 ms per packet
    serialization_delay = 0.00001211
        
    f = 1
    total_packets_sent = 0
    flight_sizes = []
    
    # Track the flights and their sizes until we cover segment k
    while total_packets_sent < k:
        _, W_f = expected_delay_flight(f)
        flight_sizes.append(W_f)
        total_packets_sent += W_f
        f += 1
        
    F_k = len(flight_sizes)
    
    # Sum the expected delays of all flights before the current flight F_k
    total_time = E_T_setup
    for i in range(1, F_k):
        E_delta_i, _ = expected_delay_flight(i)
        total_time += E_delta_i
        
    # Find the offset of segment k within the current flight F_k
    packets_before_F_k = sum(flight_sizes[:F_k-1])
    index_in_flight = k - 1 - packets_before_F_k
    
    # Segment arrival time at the server relative to the client sending the first SYN:
    # (Client flight start time) + one-way propagation & queuing delay + serialization delay
    total_time += O + pi_D + (index_in_flight * serialization_delay)
    return total_time, F_k

def get_tc_netem_params(P, L):
    """
    Approximate the NumPy inputs into tc transition parameters.
    Extracts the 4-state Gilbert-Elliott model transition probabilities from P.
    """
    p13 = P[0, 2] * 100
    p31 = P[2, 0] * 100
    p32 = P[2, 1] * 100
    p23 = P[1, 2] * 100
    p14 = P[0, 3] * 100
    return p13, p31, p32, p23, p14
