import numpy as np
import subprocess
import time
import socket
import sys
import os
import matplotlib.pyplot as plt
import concurrent.futures
import argparse
import warnings

# Ensure stdout is unbuffered so main process prints interleave correctly with subprocesses
sys.stdout.reconfigure(line_buffering=True)

try:
    from scapy.all import rdpcap, TCP, IP
except ImportError:
    print("Scapy is required. Please install it using: pip install scapy")
    sys.exit(1)

import tcp_analytical_model
from tcp_analytical_model import OWD, expected_time_k, get_total_retransmissions

# ==============================================================================
# 2. Execution Environment & Ground Truth Setup (2-Hop Topology)
# ==============================================================================

def run_cmd(cmd):
    print(f"[CMD] {cmd}")
    subprocess.run(cmd, shell=True, check=True)

def run_cmd_ignore(cmd):
    print(f"[CMD] {cmd} (ignore errors)")
    subprocess.run(cmd, shell=True, stderr=subprocess.DEVNULL)

def setup_environment():
    # Teardown any leftover namespaces
    teardown_environment()

    print("=== Setting up 2-hop network namespaces ===")
    # Create 3 namespaces: Client, Router, and Server
    run_cmd("sudo ip netns add ns_client")
    run_cmd("sudo ip netns add ns_router")
    run_cmd("sudo ip netns add ns_server")
    
    # Enable IP forwarding inside the router namespace
    run_cmd("sudo ip netns exec ns_router sysctl -w net.ipv4.ip_forward=1")

    # Link 1: Client <---> Router (10.0.1.0/24)
    run_cmd("sudo ip link add veth_c type veth peer name veth_r1")
    run_cmd("sudo ip link set veth_c netns ns_client")
    run_cmd("sudo ip link set veth_r1 netns ns_router")

    # Link 2: Router <---> Server (10.0.2.0/24)
    run_cmd("sudo ip link add veth_r2 type veth peer name veth_s")
    run_cmd("sudo ip link set veth_r2 netns ns_router")
    run_cmd("sudo ip link set veth_s netns ns_server")

    # Assign IP Addresses & bring interfaces up
    run_cmd("sudo ip netns exec ns_client ip addr add 10.0.1.1/24 dev veth_c")
    run_cmd("sudo ip netns exec ns_client ip link set veth_c up")
    run_cmd("sudo ip netns exec ns_client ip link set lo up")

    run_cmd("sudo ip netns exec ns_router ip addr add 10.0.1.2/24 dev veth_r1")
    run_cmd("sudo ip netns exec ns_router ip addr add 10.0.2.1/24 dev veth_r2")
    run_cmd("sudo ip netns exec ns_router ip link set veth_r1 up")
    run_cmd("sudo ip netns exec ns_router ip link set veth_r2 up")
    run_cmd("sudo ip netns exec ns_router ip link set lo up")

    run_cmd("sudo ip netns exec ns_server ip addr add 10.0.2.2/24 dev veth_s")
    run_cmd("sudo ip netns exec ns_server ip link set veth_s up")
    run_cmd("sudo ip netns exec ns_server ip link set lo up")

    # Routing Tables
    run_cmd("sudo ip netns exec ns_client ip route add default via 10.0.1.2")
    run_cmd("sudo ip netns exec ns_server ip route add default via 10.0.2.1")

    # Configure traffic control (tc netem) on both links
    # Split delay across two hops (OWD_ms / 2 per hop) to maintain total path OWD delay
    OWD_ms_per_hop = (OWD * 1000.0) / 2.0  # 10ms per hop -> total 20ms OWD / 40ms RTT

    def get_tc_params(link_obj):
        p = link_obj.P_base
        return (
            np.clip(p[0, 2] * 100, 0.0, 100.0),
            np.clip(p[2, 0] * 100, 0.0, 100.0),
            np.clip(p[2, 1] * 100, 0.0, 100.0),
            np.clip(p[1, 2] * 100, 0.0, 100.0),
            np.clip(p[0, 3] * 100, 0.0, 100.0)
        )

    p13_1, p31_1, p32_1, p23_1, p14_1 = get_tc_params(tcp_analytical_model._link1)
    p13_2, p31_2, p32_2, p23_2, p14_2 = get_tc_params(tcp_analytical_model._link2)

    # Link 1 (veth_c & veth_r1)
    run_cmd(f"sudo ip netns exec ns_client tc qdisc add dev veth_c root netem delay {OWD_ms_per_hop:.1f}ms rate 1gbit loss state {p13_1:.2f}% {p31_1:.2f}% {p32_1:.2f}% {p23_1:.2f}% {p14_1:.2f}%")
    run_cmd(f"sudo ip netns exec ns_router tc qdisc add dev veth_r1 root netem delay {OWD_ms_per_hop:.1f}ms rate 1gbit loss state {p13_1:.2f}% {p31_1:.2f}% {p32_1:.2f}% {p23_1:.2f}% {p14_1:.2f}%")

    # Link 2 (veth_r2 & veth_s)
    run_cmd(f"sudo ip netns exec ns_router tc qdisc add dev veth_r2 root netem delay {OWD_ms_per_hop:.1f}ms rate 1gbit loss state {p13_2:.2f}% {p31_2:.2f}% {p32_2:.2f}% {p23_2:.2f}% {p14_2:.2f}%")
    run_cmd(f"sudo ip netns exec ns_server tc qdisc add dev veth_s root netem delay {OWD_ms_per_hop:.1f}ms rate 1gbit loss state {p13_2:.2f}% {p31_2:.2f}% {p32_2:.2f}% {p23_2:.2f}% {p14_2:.2f}%")


def teardown_environment():
    print("=== Tearing down network namespaces ===")
    run_cmd_ignore("sudo ip netns del ns_client")
    run_cmd_ignore("sudo ip netns del ns_router")
    run_cmd_ignore("sudo ip netns del ns_server")

# ==============================================================================
# 3. Traffic Generation and Packet Sniffing
# ==============================================================================

import ssl

def generate_ssl_certs():
    cert_file = "server.crt"
    key_file = "server.key"
    if not (os.path.exists(cert_file) and os.path.exists(key_file)):
        subprocess.run(
            f"openssl req -x509 -newkey rsa:2048 -keyout {key_file} -out {cert_file} -days 365 -nodes -subj '/CN=10.0.2.2'",
            shell=True, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

def run_server(port):
    print(f"[SERVER] Starting plain TCP server on port {port}")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("10.0.2.2", port))
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
    print(f"[CLIENT] Connecting via plain TCP to {ip}:{port} and sending {num_bytes} bytes")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    s.connect((ip, port))
    
    chunk_size = 1448
    sent = 0
    while sent < num_bytes:
        to_send = min(chunk_size, num_bytes - sent)
        s.sendall(b'a' * to_send)
        sent += to_send
    print(f"[CLIENT] Finished sending {sent} bytes via plain TCP.")
    s.close()

def process_pcap_arrivals(packets, isn, t0, num_segments):
    arrival_times = [None] * (num_segments + 1)
    if isn is not None and t0 is not None:
        for pkt in packets:
            if TCP in pkt and IP in pkt:
                if pkt[IP].src == "10.0.1.1" and pkt[IP].dst == "10.0.2.2":
                    payload_len = len(pkt[TCP].payload)
                    if payload_len > 0:
                        seq = pkt[TCP].seq
                        relative_seq = (seq - (isn + 1)) % 4294967296
                        start_k = relative_seq // 1448 + 1
                        num_segs = max(1, int(np.ceil(payload_len / 1448)))
                        
                        for offset in range(num_segs):
                            k_val = start_k + offset
                            if 1 <= k_val <= num_segments:
                                if arrival_times[k_val] is None:
                                    arrival_times[k_val] = (float(pkt.time) - t0) * 1000.0
    return arrival_times[1:]

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
            
    parser = argparse.ArgumentParser(description="Orchestrate TCP network validation profiles.")
    parser.add_argument("--cached", action="store_true", default=False, help="Load cached array instead of running network testbed trials.")
    parser.add_argument("--tc_profile", type=str, default="none", help="Specify loss profile name for Link 1.")
    parser.add_argument("--tc_profile_l2", type=str, default=None, help="Specify loss profile name for Link 2.")
    args, unknown = parser.parse_known_args()

    # Pass specified profile flags to set distinct profiles for Hop 1 and Hop 2
    l2_prof = args.tc_profile_l2 if args.tc_profile_l2 else args.tc_profile
    tcp_analytical_model.set_active_profile(args.tc_profile, l2_prof)

    cache_file = f"empirical_dual_hop_{args.tc_profile}_{l2_prof}.npy"
    M_bytes = 300 * 1448
    num_segments = M_bytes // 1448
    
    num_trials = 100
    all_trials_data = []

    should_run_empirical = not args.cached or not os.path.exists(cache_file)

    if not should_run_empirical:
        print(f"=== Loading Cached Empirical Measurements: {cache_file} ===")
        all_trials_data = np.load(cache_file).tolist()
    else:
        try:
            setup_environment()
            
            def run_trial(trial_idx):
                print(f"=== Starting Trial {trial_idx + 1}/{num_trials} ===")
                client_pcap = f"client_{trial_idx}.pcap"
                router_pcap = f"router_{trial_idx}.pcap"
                server_pcap = f"server_{trial_idx}.pcap"
                port = 8888 + trial_idx
                
                for f in [client_pcap, router_pcap, server_pcap]:
                    if os.path.exists(f): os.remove(f)
                    
                p_client = subprocess.Popen(["sudo", "ip", "netns", "exec", "ns_client", "tcpdump", "-i", "veth_c", "tcp", "port", str(port), "-w", client_pcap], stderr=subprocess.DEVNULL)
                p_router = subprocess.Popen(["sudo", "ip", "netns", "exec", "ns_router", "tcpdump", "-i", "veth_r1", "tcp", "port", str(port), "-w", router_pcap], stderr=subprocess.DEVNULL)
                p_server = subprocess.Popen(["sudo", "ip", "netns", "exec", "ns_server", "tcpdump", "-i", "veth_s", "tcp", "port", str(port), "-w", server_pcap], stderr=subprocess.DEVNULL)
                
                time.sleep(1) 
                
                server_proc = subprocess.Popen(["sudo", "ip", "netns", "exec", "ns_server", sys.executable, sys.argv[0], "server", str(port)])
                time.sleep(1) 
                
                client_proc = subprocess.Popen(["sudo", "ip", "netns", "exec", "ns_client", sys.executable, sys.argv[0], "client", "10.0.2.2", str(port), str(M_bytes)])
                
                client_proc.wait()
                server_proc.wait()

                time.sleep(1) 

                for p in [p_client, p_router, p_server]:
                    try:
                        subprocess.run(["sudo", "kill", "-15", str(p.pid)], stderr=subprocess.DEVNULL)
                        p.wait(timeout=5)
                    except Exception:
                        pass

                try:
                    c_pkts = rdpcap(client_pcap)
                    r_pkts = rdpcap(router_pcap)
                    s_pkts = rdpcap(server_pcap)
                except Exception as e:
                    print(f"Failed reading pcaps trial {trial_idx}: {e}")
                    return None

                t0, isn = None, None
                for pkt in c_pkts:
                    if TCP in pkt and IP in pkt and pkt[IP].src == "10.0.1.1" and pkt[TCP].flags == "S":
                        t0 = float(pkt.time)
                        isn = pkt[TCP].seq
                        break

                if t0 is None or isn is None:
                    return None

                first_hop_times = process_pcap_arrivals(r_pkts, isn, t0, num_segments)
                dest_times      = process_pcap_arrivals(s_pkts, isn, t0, num_segments)

                for f in [client_pcap, router_pcap, server_pcap]:
                    if os.path.exists(f): os.remove(f)

                valid_first = sum(1 for t in first_hop_times if t is not None)
                valid_dest  = sum(1 for t in dest_times if t is not None)

                if valid_first > 0 and valid_dest > 0:
                    return [first_hop_times, dest_times]
                else:
                    print(f"Missing packets in trial {trial_idx}.")
                    return None

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
    
    # Shape: (num_trials, 2 [hop1, dest], num_segments)
    trials_matrix = np.array(all_trials_data, dtype=float)
    
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        emp_first_mean   = np.nanmean(trials_matrix[:, 0, :], axis=0)
        emp_first_median = np.nanmedian(trials_matrix[:, 0, :], axis=0)
        emp_first_p25    = np.nanpercentile(trials_matrix[:, 0, :], 25, axis=0)
        emp_first_p75    = np.nanpercentile(trials_matrix[:, 0, :], 75, axis=0)
        
        emp_dest_mean    = np.nanmean(trials_matrix[:, 1, :], axis=0)
        emp_dest_median  = np.nanmedian(trials_matrix[:, 1, :], axis=0)
        emp_dest_p25     = np.nanpercentile(trials_matrix[:, 1, :], 25, axis=0)
        emp_dest_p75     = np.nanpercentile(trials_matrix[:, 1, :], 75, axis=0)

    N = num_segments
    model_first, model_dest = [], []
    flights = {}
    
    for k in range(1, N + 1):
        t_first_k, t_dest_k, f_k = expected_time_k(k)
        model_first.append(t_first_k * 1000.0)
        model_dest.append(t_dest_k * 1000.0)
        if f_k not in flights:
            flights[f_k] = []
        flights[f_k].append(k)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), sharex=True)
    k_vals = list(range(1, N + 1))
    OWD_ms = OWD * 1000.0

    def add_flight_spans(ax):
        colors = ['#e6f2ff', '#cce5ff']
        for f_k, k_list in flights.items():
            min_k, max_k = min(k_list), max(k_list)
            color = colors[f_k % len(colors)]
            label = f'Flight {f_k}' if f_k <= 5 else ""
            ax.axvspan(min_k - 0.5, max_k + 0.5, facecolor=color, alpha=0.5, label=label)

    # --------------------------------------------------------------------------
    # Subplot 1: First-Hop Arrivals
    # --------------------------------------------------------------------------
    ax1.plot(k_vals, model_first, label='Model First-Hop ($E[T_{k, first}]$)', color='blue', linewidth=2)
    ax1.plot(k_vals, emp_first_mean + (OWD_ms / 2.0), label='Empirical First-Hop (Mean)', color='red', linewidth=2)
    ax1.plot(k_vals, emp_first_median + (OWD_ms / 2.0), label='Empirical First-Hop (Median)', color='darkred', linestyle='--', linewidth=1.5)
    ax1.fill_between(k_vals, emp_first_p25 + (OWD_ms / 2.0), emp_first_p75 + (OWD_ms / 2.0), color='red', alpha=0.2, label='Empirical 25th-75th %ile')
    
    add_flight_spans(ax1)
    ax1.set_ylabel('Relative Arrival Time (ms)', fontsize=11)
    ax1.set_title('First-Hop Arrival Times (Link 1 Router Ingress)', fontsize=12, fontweight='bold')
    ax1.grid(True, linestyle=':', alpha=0.7)
    
    handles1, labels1 = ax1.get_legend_handles_labels()
    by_label1 = dict(zip(labels1, handles1))
    ax1.legend(by_label1.values(), by_label1.keys(), loc='upper left')

    # --------------------------------------------------------------------------
    # Subplot 2: Final Destination Arrivals
    # --------------------------------------------------------------------------
    ax2.plot(k_vals, model_dest, label='Model Dest Arrival ($E[T_{k, dest}]$)', color='blue', linewidth=2)
    ax2.plot(k_vals, emp_dest_mean + OWD_ms, label='Empirical Dest (Mean)', color='red', linewidth=2)
    ax2.plot(k_vals, emp_dest_median + OWD_ms, label='Empirical Dest (Median)', color='darkred', linestyle='--', linewidth=1.5)
    ax2.fill_between(k_vals, emp_dest_p25 + OWD_ms, emp_dest_p75 + OWD_ms, color='red', alpha=0.2, label='Empirical 25th-75th %ile')
    
    add_flight_spans(ax2)
    ax2.set_xlabel('Segment Index ($k$)', fontsize=12)
    ax2.set_ylabel('Relative Arrival Time (ms)', fontsize=11)
    ax2.set_title('Final Destination Arrival Times (Link 2 Server Ingress)', fontsize=12, fontweight='bold')
    ax2.grid(True, linestyle=':', alpha=0.7)

    handles2, labels2 = ax2.get_legend_handles_labels()
    by_label2 = dict(zip(labels2, handles2))
    ax2.legend(by_label2.values(), by_label2.keys(), loc='upper left')

    fig.suptitle(f'2-Hop Dual-Stage TCP Delivery Validation ({len(all_trials_data)} Trials - L1: {args.tc_profile}, L2: {l2_prof})', fontsize=14, y=0.98)
    
    plt.tight_layout()
    plot_file = 'tcp_validation_plot.png'
    plt.savefig(plot_file, dpi=300)
    print(f"Plot successfully saved to {plot_file}")

    total_retrans = get_total_retransmissions()
    print(f"\n[MODEL OUTPUT] Total Expected Retransmissions (L1: '{args.tc_profile}', L2: '{l2_prof}'): {total_retrans:.2f}")