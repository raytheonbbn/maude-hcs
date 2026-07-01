import numpy as np
import subprocess
import time
import socket
import sys
import os
import matplotlib.pyplot as plt
import concurrent.futures
import argparse

# Ensure stdout is unbuffered so main process prints interleave correctly with subprocesses
sys.stdout.reconfigure(line_buffering=True)

try:
    from scapy.all import rdpcap, TCP, IP
except ImportError:
    print("Scapy is required. Please install it using: pip install scapy")
    sys.exit(1)

import tcp_analytical_model
from tcp_analytical_model import O, expected_time_k, get_tc_netem_params

# ==============================================================================
# 2. Execution Environment & Ground Truth Setup
# ==============================================================================

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
    
    p13, p31, p32, p23, p14 = get_tc_netem_params(tcp_analytical_model.P_base, tcp_analytical_model.L_base)
    
    # Apply delay to both sides for RTT. Apply the exact same 4-state Markov loss model to BOTH sides.
    # This simulates independent, symmetric Gilbert-Elliott drop rates for both directions (DATA segments and ACKs).
    # Apply Netem emulation: 20ms one-way delay, 1 Gbps bandwidth, and bursty loss
    O_ms = O * 1000
    run_cmd(f"sudo ip netns exec ns_client tc qdisc add dev veth_c root netem delay {O_ms}ms rate 1gbit loss state {p13:.2f}% {p31:.2f}% {p32:.2f}% {p23:.2f}% {p14:.2f}%")
    run_cmd(f"sudo ip netns exec ns_server tc qdisc add dev veth_s root netem delay {O_ms}ms rate 1gbit loss state {p13:.2f}% {p31:.2f}% {p32:.2f}% {p23:.2f}% {p14:.2f}%")

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
    print(f"[CLIENT] Finished sending {sent} bytes.")
    s.close()

# ==============================================================================
# Main Orchestration
# ==============================================================================

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ["server", "client"]:
        if sys.argv[1] == "server":
            run_server(int(sys.argv[2]))
            sys.exit(0)
        elif sys.argv[1] == "client":
            run_client(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
            sys.exit(0)
            
    # ── Parse profile arguments inside the validation orchestrator ──
    parser = argparse.ArgumentParser(description="Orchestrate TCP network validation profiles.")
    parser.add_argument("--cached", action="store_true", default=False, help="Load cached array instead of running network testbed trials.")
    parser.add_argument("--tc_profile", type=str, default="none", help="Specify loss profile name.")
    args, unknown = parser.parse_known_args()

    # Pass specified profile flag to dynamically update analytical baseline matrices
    tcp_analytical_model.set_active_profile(args.tc_profile)

    cache_file = f"empirical_data_{args.tc_profile}.npy"
    pcap_file = "capture.pcap"
    client_pcap_file = "client_capture.pcap"
    M_bytes = 300 * 1448
    num_segments = M_bytes // 1448
    
    num_trials = 100
    all_trials_data = []

    # Check execution pathway based on caching availability and user parameters
    should_run_empirical = not args.cached or not os.path.exists(cache_file)

    if not should_run_empirical:
        print(f"=== Loading Cached Empirical Measurements: {cache_file} ===")
        all_trials_data = np.load(cache_file).tolist()
    else:
        try:
            setup_environment()
            
            def run_trial(trial_idx):
                print(f"=== Starting Trial {trial_idx + 1}/{num_trials} ===")
                pcap_file = f"capture_{trial_idx}.pcap"
                client_pcap_file = f"client_capture_{trial_idx}.pcap"
                port = 8888 + trial_idx
                
                if os.path.exists(pcap_file):
                    os.remove(pcap_file)
                if os.path.exists(client_pcap_file):
                    os.remove(client_pcap_file)
                    
                client_tcpdump_cmd = ["sudo", "ip", "netns", "exec", "ns_client", "tcpdump", "-i", "veth_c", "tcp", "port", str(port), "-w", client_pcap_file]
                client_tcpdump_proc = subprocess.Popen(client_tcpdump_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                tcpdump_cmd = ["sudo", "ip", "netns", "exec", "ns_server", "tcpdump", "-i", "veth_s", "tcp", "port", str(port), "-w", pcap_file]
                tcpdump_proc = subprocess.Popen(tcpdump_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                time.sleep(1) 
                
                server_cmd = ["sudo", "ip", "netns", "exec", "ns_server", sys.executable, sys.argv[0], "server", str(port)]
                server_proc = subprocess.Popen(server_cmd)
                time.sleep(1) 
                
                client_cmd = ["sudo", "ip", "netns", "exec", "ns_client", sys.executable, sys.argv[0], "client", "10.0.0.2", str(port), str(M_bytes)]
                client_proc = subprocess.Popen(client_cmd)
                
                client_proc.wait()
                server_proc.wait()

                time.sleep(1) 

                try:
                    subprocess.run(["sudo", "kill", "-15", str(tcpdump_proc.pid)], stderr=subprocess.DEVNULL)
                    subprocess.run(["sudo", "kill", "-15", str(client_tcpdump_proc.pid)], stderr=subprocess.DEVNULL)
                except Exception:
                    pass

                try:
                    tcpdump_proc.wait(timeout=5)
                    client_tcpdump_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    subprocess.run(["sudo", "kill", "-9", str(tcpdump_proc.pid)], stderr=subprocess.DEVNULL)
                    subprocess.run(["sudo", "kill", "-9", str(client_tcpdump_proc.pid)], stderr=subprocess.DEVNULL)
                
                try:
                    packets = rdpcap(pcap_file)
                except Exception as e:
                    print(f"Failed to read server pcap file for trial {trial_idx}: {e}")
                    return None
                    
                try:
                    client_packets = rdpcap(client_pcap_file)
                except Exception as e:
                    print(f"Failed to read client pcap file for trial {trial_idx}: {e}")
                    client_packets = []
                    
                t0 = None
                for pkt in client_packets:
                    if TCP in pkt and IP in pkt:
                        if pkt[IP].src == "10.0.0.1" and pkt[IP].dst == "10.0.0.2":
                            if pkt[TCP].flags == "S":
                                t0 = float(pkt.time)
                                break
                                
                if t0 is None:
                    for pkt in packets:
                        if TCP in pkt and IP in pkt:
                            if pkt[IP].src == "10.0.0.1" and pkt[IP].dst == "10.0.0.2":
                                if pkt[TCP].flags == "S":
                                    t0 = float(pkt.time) - O
                                    break

                isn = None
                for pkt in client_packets:
                    if TCP in pkt and IP in pkt:
                        if pkt[IP].src == "10.0.0.1" and pkt[IP].dst == "10.0.0.2":
                            if pkt[TCP].flags == "S":
                                isn = pkt[TCP].seq
                                break
                if isn is None:
                    for pkt in packets:
                        if TCP in pkt and IP in pkt:
                            if pkt[IP].src == "10.0.0.1" and pkt[IP].dst == "10.0.0.2":
                                if pkt[TCP].flags == "S":
                                    isn = pkt[TCP].seq
                                    break

                segment_arrival_times = [None] * (num_segments + 1)

                if isn is not None and t0 is not None:
                    for pkt in packets:
                        if TCP in pkt and IP in pkt:
                            if pkt[IP].src == "10.0.0.1" and pkt[IP].dst == "10.0.0.2":
                                payload_len = len(pkt[TCP].payload)
                                if payload_len > 0:
                                    seq = pkt[TCP].seq
                                    relative_seq = (seq - (isn + 1)) % 4294967296
                                    start_k = relative_seq // 1448 + 1
                                    num_segs = int(np.ceil(payload_len / 1448))
                                    
                                    for offset in range(num_segs):
                                        k_val = start_k + offset
                                        if 1 <= k_val <= num_segments:
                                            if segment_arrival_times[k_val] is None:
                                                segment_arrival_times[k_val] = (float(pkt.time) - t0) * 1000.0 

                if os.path.exists(pcap_file):
                    try: os.remove(pcap_file)
                    except Exception: pass
                if os.path.exists(client_pcap_file):
                    try: os.remove(client_pcap_file)
                    except Exception: pass

                valid_count = sum(1 for t in segment_arrival_times[1:] if t is not None)
                if valid_count > 0:
                    return segment_arrival_times[1:]
                else:
                    print(f"No payload segments captured in trial {trial_idx}.")
                    return None

            # parallelize here by increasing max_workers (but there might be race conditions that cause things to hang)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                results = executor.map(run_trial, range(num_trials))
                for res in results:
                    if res is not None:
                        all_trials_data.append(res)

            if len(all_trials_data) == 0:
                print("No valid data collected across any trials. Exiting.")
                sys.exit(1)
                
            print(f"=== Saving Empirical Array to disk storage profile: {cache_file} ===")
            np.save(cache_file, np.array(all_trials_data, dtype=float))

        except KeyboardInterrupt:
            print("Interrupted by user.")
            sys.exit(1)
        finally:
            teardown_environment()

    print("=== Generating Plot ===")
    
    trials_matrix = np.array(all_trials_data, dtype=float)
    empirical_mean = np.nanmean(trials_matrix, axis=0)
    empirical_median = np.nanmedian(trials_matrix, axis=0)
    empirical_std = np.nanstd(trials_matrix, axis=0)

    N = num_segments
    theoretical_times = []
    flights = {}
    for k in range(1, N + 1):
        t_k, f_k = expected_time_k(k)
        theoretical_times.append(t_k * 1000.0)
        if f_k not in flights:
            flights[f_k] = []
        flights[f_k].append(k)

    plt.figure(figsize=(12, 7))
    k_vals = list(range(1, N + 1))

    # HACK: Adjust by 20ms, because the segment timestamps are from the transmission side instead of reception side 
    O_ms = O * 1000.0  # 20.0 ms

    plt.plot(k_vals, theoretical_times, label='Theoretical Model ($E[T_k]$)', color='blue', linewidth=2)
    plt.plot(k_vals, empirical_mean + O_ms, label='Empirical Measurements (Mean)', color='red', linewidth=2)
    plt.plot(k_vals, empirical_median + O_ms, color='darkred', linestyle='--', linewidth=1.5, label='Empirical Measurements (Median)')
    
    # Clip the lower standard deviation bound at 0 ms
    plt.fill_between(k_vals, 
             np.maximum(0, (empirical_mean - empirical_std) + O_ms),
             (empirical_mean + empirical_std) + O_ms,
             color='lightcoral', alpha=0.3, label='Empirical Measurements (± STD)')
    
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
    plt.title(f'TCP Segment Delivery Times ({len(all_trials_data)} Trials - Profile: {args.tc_profile})', fontsize=14)
    
    handles, labels = plt.gca().get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    plt.legend(by_label.values(), by_label.keys(), loc='upper left')
    
    plt.grid(True, linestyle=':', alpha=0.7)
    plt.tight_layout()
    plot_file = 'tcp_validation_plot.png'
    plt.savefig(plot_file, dpi=300)
    print(f"Plot successfully saved to {plot_file}")
