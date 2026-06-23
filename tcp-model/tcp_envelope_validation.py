import numpy as np
import subprocess
import time
import socket
import sys
import os
import matplotlib.pyplot as plt
import concurrent.futures
import warnings

# Ensure stdout is unbuffered so main process prints interleave correctly with subprocesses
sys.stdout.reconfigure(line_buffering=True)

try:
    from scapy.all import rdpcap, TCP, IP
except ImportError:
    print("Scapy is required. Please install it using: pip install scapy")
    sys.exit(1)

from tcp_analytical_model import P_base, L_base, O, expected_time_k, get_tc_netem_params

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
    
    p13, p31, p32, p23, p14 = get_tc_netem_params(P_base, L_base)
    
    # Apply delay to both sides for RTT. Apply the exact same 4-state Markov loss model to BOTH sides.
    # This simulates independent, symmetric Gilbert-Elliott drop rates for both directions (DATA segments and ACKs).
    # Apply Netem emulation: 20ms one-way delay, 10 Mbps bandwidth, and bursty loss
    # The 10Mbit rate enforces the exact serialization delay (1.211 ms per 1514B packet) modeled mathematically!
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
    if len(sys.argv) > 1:
        if sys.argv[1] == "server":
            run_server(int(sys.argv[2]))
            sys.exit(0)
        elif sys.argv[1] == "client":
            run_client(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]))
            sys.exit(0)
            
    pcap_file = "capture.pcap"
    client_pcap_file = "client_capture.pcap"
    M_bytes = 300 * 1448
    num_segments = M_bytes // 1448
    
    num_groups = 30
    trials_per_group = 100
    total_trials = num_groups * trials_per_group
    
    global_arrival_matrix = np.full((total_trials, num_segments), np.nan)
    group_means = []
    
    try:
        setup_environment()
        
        def run_trial(global_idx, group_idx, trial_idx):
            print(f"=== Starting Group {group_idx + 1}/{num_groups} | Trial {trial_idx + 1}/{trials_per_group} (Global {global_idx + 1}/{total_trials}) ===")
            pcap_file = f"capture_{global_idx}.pcap"
            client_pcap_file = f"client_capture_{global_idx}.pcap"
            port = 8888 + global_idx
            
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
                print(f"Failed to read server pcap file for global trial {global_idx}: {e}")
                return global_idx, None
                
            try:
                client_packets = rdpcap(client_pcap_file)
            except Exception as e:
                print(f"Failed to read client pcap file for global trial {global_idx}: {e}")
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
                                            segment_arrival_times[k_val] = (float(pkt.time) - t0) * 1000.0 # ms

            if os.path.exists(pcap_file):
                try: os.remove(pcap_file)
                except Exception: pass
            if os.path.exists(client_pcap_file):
                try: os.remove(client_pcap_file)
                except Exception: pass

            valid_count = sum(1 for t in segment_arrival_times[1:] if t is not None)
            if valid_count > 0:
                return global_idx, segment_arrival_times[1:]
            else:
                print(f"No payload segments captured in global trial {global_idx}.")
                return global_idx, None

        # Execute macro groupings sequentially
        global_counter = 0
        for g_idx in range(num_groups):
            current_group_data = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(run_trial, global_counter + t_idx, g_idx, t_idx) for t_idx in range(trials_per_group)]
                global_counter += trials_per_group
                
                for future in concurrent.futures.as_completed(futures):
                    g_idx_res, res = future.result()
                    if res is not None:
                        global_arrival_matrix[g_idx_res, :] = res
                        current_group_data.append(res)
            
            if len(current_group_data) > 0:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", category=RuntimeWarning)
                    group_array = np.array(current_group_data, dtype=float)
                    group_means.append(np.nanmean(group_array, axis=0))

        if len(group_means) == 0:
            print("No valid data collected across any trials. Exiting.")
            sys.exit(1)
            
        print("=== Generating Grand Envelope Plot ===")
        
        # 1. Process Global Matrix Statistics
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            grand_mean = np.nanmean(global_arrival_matrix, axis=0)
            grand_std = np.nanstd(global_arrival_matrix, axis=0)

        # 2. Process Macro-Group Boundaries (Variance of Group Sampling Runs)
        meta_means_matrix = np.array(group_means, dtype=float)
        min_group_mean = np.nanmin(meta_means_matrix, axis=0)
        max_group_mean = np.nanmax(meta_means_matrix, axis=0)

        N = num_segments
        theoretical_times = []
        flights = {}
        for k in range(1, N + 1):
            t_k, f_k = expected_time_k(k)
            theoretical_times.append(t_k * 1000.0)
            if f_k not in flights:
                flights[f_k] = []
            flights[f_k].append(k)

        plt.figure(figsize=(13, 8))
        k_vals = list(range(1, N + 1))
        
        # Plot structural flight segment zones under the curves
        colors = ['#f4f8fc', '#eaf1f8']
        for f_k, k_list in flights.items():
            min_k, max_k = min(k_list), max(k_list)
            color = colors[f_k % len(colors)]
            plt.axvspan(min_k - 0.5, max_k + 0.5, facecolor=color, alpha=0.6)
            plt.axvline(max_k + 0.5, color='gainsboro', linestyle='dotted', alpha=0.4)

        # Envelope A: Total individual trial jitter (Outer Wide Shaded Area, clipped safely at 0ms)
        plt.fill_between(k_vals, 
                         np.maximum(0, grand_mean - grand_std), 
                         grand_mean + grand_std, 
                         color='lightcoral', alpha=0.12, label='Total Trial Jitter (±1 STD)')

        # Envelope B: Macro-Group Mean Boundaries (Inner Solid Shaded Ribbon showing mean variance)
        plt.fill_between(k_vals, 
                         min_group_mean, 
                         max_group_mean, 
                         color='red', alpha=0.35, label='Group Sampling Variance (Min/Max Means)')
            
        # Central Anchor Lines
        plt.plot(k_vals, grand_mean, color='darkred', linewidth=2.5, label='Grand Empirical Mean (3,000 runs total)')
        plt.plot(k_vals, theoretical_times, label='Theoretical Model ($E[T_k]$)', color='blue', linewidth=2.5)

        plt.xlabel('Segment Index ($k$)', fontsize=12)
        plt.ylabel('Relative Arrival Time (ms)', fontsize=12)
        plt.title(f'TCP Segment Delivery Times ({num_groups} Groups × {trials_per_group} Trials Grand Envelope)', fontsize=14)
        
        handles, labels = plt.gca().get_legend_handles_labels()
        by_label = dict(zip(labels, handles))
        plt.legend(by_label.values(), by_label.keys(), loc='upper left', frameon=True, facecolor='white', framealpha=0.9)
        
        plt.grid(True, linestyle=':', alpha=0.6)
        plt.xlim(0.5, N + 0.5)
        plt.tight_layout()
        
        plot_file = 'tcp_grand_envelope_validation_plot.png'
        plt.savefig(plot_file, dpi=300)
        print(f"Plot successfully saved to {plot_file}")

    except KeyboardInterrupt:
        print("Interrupted by user.")
    finally:
        teardown_environment()
