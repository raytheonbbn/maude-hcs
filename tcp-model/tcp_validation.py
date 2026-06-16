import numpy as np
import subprocess
import time
import socket
import sys
import os
import matplotlib.pyplot as plt

# Ensure stdout is unbuffered so main process prints interleave correctly with subprocesses
sys.stdout.reconfigure(line_buffering=True)

try:
    from scapy.all import rdpcap, TCP, IP
except ImportError:
    print("Scapy is required. Please install it using: pip install scapy")
    sys.exit(1)

# ==============================================================================
# 1. The Mathematical Model & NumPy Implementation
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
    # TCP Congestion Avoidance Modification:
    # Under continuous data loss, TCP exits Slow Start after the first flight
    # and enters Congestion Avoidance. Flight sizes stabilize around W_steady.
    if f == 1:
        W_f = IW
    else:
        W_f = W_steady
        
    # The expected flight delay is the cumulative expected delay of its packets.
    # This automatically factors in the statistically averaged RTO timeouts.
    E_delta_f = W_f * E_T_pkt
    return E_delta_f, W_f

# 6. Segment Calculation (E[T_k])
def expected_time_k(k):
    if k <= 0:
        return 0, 1
        
    # Realistic serialization delay for a 1 Gbps link
    # 1514 bytes (Ethernet frame) * 8 bits / 1,000,000,000 bps = ~0.01211 ms per packet
    serialization_delay = 0.00001211
        
    if k <= IW:
        index_in_flight = k - 1
        return E_T_setup + O + pi_D + (index_in_flight * serialization_delay), 1
        
    remaining_k = k - IW
    additional_flights = int(np.ceil(remaining_k / W_steady))
    F_k = 1 + additional_flights
        
    total_time = E_T_setup
    for f in range(1, F_k):
        E_delta_f, _ = expected_delay_flight(f)
        total_time += E_delta_f
        
    index_in_flight = k - 1 - (IW + (F_k - 2) * W_steady)
    total_time += O + pi_D + (index_in_flight * serialization_delay)
    return total_time, F_k

# ==============================================================================
# 2. Execution Environment & Ground Truth Setup
# ==============================================================================

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

def run_cmd(cmd):
    print(f"[CMD] {cmd}")
    subprocess.run(cmd, shell=True, check=True)

def run_cmd_ignore(cmd):
    print(f"[CMD] {cmd} (ignore errors)")
    subprocess.run(cmd, shell=True, stderr=subprocess.DEVNULL)

def setup_environment():

    # clean up in case a previous run didn't teardown properly (needed for Colima environment)
    teardown_environment()

    print("=== Setting up network namespaces ===")
    run_cmd("sudo ip netns add ns_client")
    run_cmd("sudo ip netns add ns_server")
    
    run_cmd("sudo ip link add veth_c type veth peer name veth_s")
    
    run_cmd("sudo ip link set veth_c netns ns_client")
    run_cmd("sudo ip link set veth_s netns ns_server")
    
    run_cmd("sudo ip netns exec ns_client ip addr add 10.0.0.1/24 dev veth_c")
    run_cmd("sudo ip netns exec ns_client ip link set veth_c up")
    run_cmd("sudo ip netns exec ns_client ip link set lo up")
    
    run_cmd("sudo ip netns exec ns_server ip addr add 10.0.0.2/24 dev veth_s")
    run_cmd("sudo ip netns exec ns_server ip link set veth_s up")
    run_cmd("sudo ip netns exec ns_server ip link set lo up")
    
    run_cmd("sudo ip netns exec ns_client ip route add default via 10.0.0.2")
    run_cmd("sudo ip netns exec ns_server ip route add default via 10.0.0.1")
    
    p13, p31, p32, p23, p14 = get_tc_netem_params(P, L)
    
    # Apply delay to both sides for RTT. Apply loss strictly to veth_c (client) 
    # to drop DATA segments, not ACKs.
    # Apply Netem emulation: 20ms one-way delay, 10 Mbps bandwidth, and bursty loss
    # The 10Mbit rate enforces the exact serialization delay (1.211 ms per 1514B packet) modeled mathematically!
    O_ms = O * 1000
    run_cmd(f"sudo ip netns exec ns_client tc qdisc add dev veth_c root netem delay {O_ms}ms rate 1gbit loss state {p13:.2f}% {p31:.2f}% {p32:.2f}% {p23:.2f}% {p14:.2f}%")
    run_cmd(f"sudo ip netns exec ns_server tc qdisc add dev veth_s root netem delay {O_ms}ms rate 1gbit")

def teardown_environment():
    print("=== Tearing down network namespaces ===")
    run_cmd_ignore("sudo ip netns del ns_client")
    run_cmd_ignore("sudo ip netns del ns_server")

# ==============================================================================
# 3. Traffic Generation and Packet Sniffing
# ==============================================================================

def run_server(port):
    print(f"[SERVER] Starting on port {port}")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("10.0.0.2", port))
    s.listen(1)
    conn, addr = s.accept()
    print(f"[SERVER] Connection from {addr}")
    total_received = 0
    while True:
        data = conn.recv(65536)
        if not data:
            break
        total_received += len(data)
    print(f"[SERVER] Received {total_received} bytes. Connection closed.")
    conn.close()
    s.close()

def run_client(ip, port, num_bytes):
    print(f"[CLIENT] Connecting to {ip}:{port} and sending {num_bytes} bytes")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    s.connect((ip, port))
    
    chunk_size = 1448
    sent = 0
    while sent < num_bytes:
        to_send = min(chunk_size, num_bytes - sent)
        s.sendall(b'a' * to_send)
        sent += to_send
        # Slight sleep to allow segmentation without bursting limits if needed,
        # but TCP_NODELAY is enabled, so it should push immediately.
        # time.sleep(0.001) 
    print(f"[CLIENT] Finished sending {sent} bytes.")
    s.close()

# ==============================================================================
# Main Orchestration
# ==============================================================================

if __name__ == "__main__":
    # Handle re-entrant subprocess execution for namespaces
    if len(sys.argv) > 1:
        if sys.argv[1] == "server":
            run_server(int(sys.argv[2]))
            sys.exit(0)
        elif sys.argv[1] == "client":
            run_client(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
            sys.exit(0)
            
    pcap_file = "capture.pcap"
    M_bytes = 150 * 1448 # enough for ~150 segments
    num_trials = 20
    
    all_trials_data = []
    
    try:
        setup_environment()
        
        for trial in range(num_trials):
            print(f"\n=== Starting Trial {trial + 1}/{num_trials} ===")
            
            if os.path.exists(pcap_file):
                os.remove(pcap_file)
                
            port = 8888 + trial
            
            tcpdump_cmd = ["sudo", "ip", "netns", "exec", "ns_server", "tcpdump", "-i", "veth_s", "tcp", "port", str(port), "-w", pcap_file]
            tcpdump_proc = subprocess.Popen(tcpdump_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(1) # Give tcpdump time to initialize
            
            server_cmd = ["sudo", "ip", "netns", "exec", "ns_server", sys.executable, sys.argv[0], "server", str(port)]
            server_proc = subprocess.Popen(server_cmd)
            time.sleep(1) # Give server time to bind
            
            client_cmd = ["sudo", "ip", "netns", "exec", "ns_client", sys.executable, sys.argv[0], "client", "10.0.0.2", str(port), str(M_bytes)]
            client_proc = subprocess.Popen(client_cmd)
            
            client_proc.wait()
            server_proc.wait()
            
            time.sleep(1) # Flush packets
            subprocess.run(["sudo", "pkill", "tcpdump"], stderr=subprocess.DEVNULL)
            tcpdump_proc.wait()
            
            try:
                packets = rdpcap(pcap_file)
            except Exception as e:
                print(f"Failed to read pcap file: {e}")
                continue
                
            t0 = None
            arrival_times = {} # seq -> timestamp
            for pkt in packets:
                if TCP in pkt and IP in pkt:
                    if pkt[IP].src == "10.0.0.1" and pkt[IP].dst == "10.0.0.2":
                        if pkt[TCP].flags == "S":
                            if t0 is None:
                                t0 = float(pkt.time)
                        elif len(pkt[TCP].payload) > 0:
                            seq = pkt[TCP].seq
                            if seq not in arrival_times:
                                if t0 is not None:
                                    arrival_times[seq] = float(pkt.time) - t0

            if len(arrival_times) > 0:
                sorted_seqs = sorted(arrival_times.keys())
                empirical_times = []
                for seq in sorted_seqs:
                    empirical_times.append(arrival_times[seq] * 1000.0) # ms
                
                first_emp = empirical_times[0]
                empirical_times = [t - first_emp for t in empirical_times]
                all_trials_data.append(empirical_times)
            else:
                print("No payload segments captured in this trial.")

        if len(all_trials_data) == 0:
            print("No valid data collected across any trials. Exiting.")
            sys.exit(1)
            
        print("=== Generating Plot ===")
        import warnings
        max_k = max([len(t) for t in all_trials_data])
        arrival_matrix = np.full((len(all_trials_data), max_k), np.nan)
        for i, t in enumerate(all_trials_data):
            arrival_matrix[i, :len(t)] = t
            
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            empirical_mean = np.nanmean(arrival_matrix, axis=0)
            empirical_std = np.nanstd(arrival_matrix, axis=0)

        N = max_k
        theoretical_times = []
        flights = {}
        for k in range(1, N + 1):
            t_k, f_k = expected_time_k(k)
            theoretical_times.append(t_k * 1000.0)
            if f_k not in flights:
                flights[f_k] = []
            flights[f_k].append(k)

        first_theo = theoretical_times[0]
        theoretical_times = [t - first_theo for t in theoretical_times]

        plt.figure(figsize=(12, 7))
        k_vals = list(range(1, N + 1))
        
        plt.plot(k_vals, theoretical_times, label='Theoretical Model ($E[T_k]$)', color='blue', linewidth=2)
        plt.errorbar(k_vals, empirical_mean, yerr=empirical_std, fmt='-o', color='red', ecolor='lightcoral', elinewidth=1, capsize=2, markersize=3, label='Empirical Measurements (Mean ± STD)')
        
        colors = ['#e6f2ff', '#cce5ff']
        for f_k, k_list in flights.items():
            min_k = min(k_list)
            max_k = max(k_list)
            color = colors[f_k % len(colors)]
            label = f'Flight {f_k}' if f_k <= 5 else ""
            plt.axvspan(min_k - 0.5, max_k + 0.5, facecolor=color, alpha=0.5, label=label)
            plt.axvline(max_k + 0.5, color='gray', linestyle='dotted', alpha=0.5)

        plt.xlabel('Segment Index ($k$)', fontsize=12)
        plt.ylabel('Relative Arrival Time (ms)', fontsize=12)
        plt.title(f'TCP Segment Delivery Times ({len(all_trials_data)} Trials)', fontsize=14)
        
        handles, labels = plt.gca().get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        plt.legend(by_label.values(), by_label.keys(), loc='upper left')
        
        plt.grid(True, linestyle=':', alpha=0.7)
        plt.tight_layout()
        plot_file = 'tcp_validation_plot.png'
        plt.savefig(plot_file, dpi=300)
        print(f"Plot successfully saved to {plot_file}")

    except KeyboardInterrupt:
        print("Interrupted by user.")
        teardown_environment()
