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

    # Disable TSO, GSO, and GRO on all veth interfaces so packets are segmented
    # to standard 1500B MTU frames and not coalesced across virtual links
    run_cmd("sudo ip netns exec ns_client ethtool -K veth_c tso off gso off gro off")
    run_cmd("sudo ip netns exec ns_router ethtool -K veth_r1 tso off gso off gro off")
    run_cmd("sudo ip netns exec ns_router ethtool -K veth_r2 tso off gso off gro off")
    run_cmd("sudo ip netns exec ns_server ethtool -K veth_s tso off gso off gro off")

    # Routing Tables
    run_cmd("sudo ip netns exec ns_client ip route add default via 10.0.1.2")
    run_cmd("sudo ip netns exec ns_server ip route add default via 10.0.2.1")

    # Configure traffic control (tc netem) on both links
    # Split delay across two hops (OWD_ms / 2 per hop) to maintain total path OWD delay
    OWD_ms_per_hop = (OWD * 1000.0) / 2.0  # 10ms per hop -> total 20ms OWD / 40ms RTT

    drop_p1 = tcp_analytical_model._link1.drop_prob
    drop_p2 = tcp_analytical_model._link2.drop_prob

    loss_cmd1 = f" loss {drop_p1 * 100.0:.3f}%" if drop_p1 > 1e-10 else ""
    loss_cmd2 = f" loss {drop_p2 * 100.0:.3f}%" if drop_p2 > 1e-10 else ""

    # Link 1 (veth_c & veth_r1)
    run_cmd(f"sudo ip netns exec ns_client tc qdisc add dev veth_c root netem delay {OWD_ms_per_hop:.1f}ms rate 1gbit{loss_cmd1}")
    run_cmd(f"sudo ip netns exec ns_router tc qdisc add dev veth_r1 root netem delay {OWD_ms_per_hop:.1f}ms rate 1gbit{loss_cmd1}")

    # Link 2 (veth_r2 & veth_s)
    run_cmd(f"sudo ip netns exec ns_router tc qdisc add dev veth_r2 root netem delay {OWD_ms_per_hop:.1f}ms rate 1gbit{loss_cmd2}")
    run_cmd(f"sudo ip netns exec ns_server tc qdisc add dev veth_s root netem delay {OWD_ms_per_hop:.1f}ms rate 1gbit{loss_cmd2}")


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


def process_pcap_acks(packets, isn, t0, num_segments):
    """
    Extracts emitted ACK packet arrival times (in ms relative to t0), indexed by
    the exact segment k in 1..num_segments that each cumulative ACK packet
    newly acknowledges (leaving segments that did not emit their own ACK as None).
    """
    ack_times = [None] * (num_segments + 1)
    highest_acked = 0
    if isn is not None and t0 is not None:
        for pkt in packets:
            if TCP in pkt and IP in pkt:
                if pkt[IP].src == "10.0.2.2" and pkt[IP].dst == "10.0.1.1":
                    flags = int(pkt[TCP].flags)
                    # Must carry ACK flag (0x10) and not be SYN (0x02)
                    if (flags & 0x10) and not (flags & 0x02):
                        ack_seq = pkt[TCP].ack
                        relative_ack = (ack_seq - (isn + 1)) % 4294967296
                        if 0 < relative_ack <= (num_segments + 10) * 1448:
                            acked_k = min(num_segments, relative_ack // 1448)
                            if acked_k > highest_acked:
                                pkt_ms = (float(pkt.time) - t0) * 1000.0
                                ack_times[acked_k] = pkt_ms
                                highest_acked = acked_k
    return ack_times[1:]


def _extract_emitted_ack_matrix(ack_matrix):
    """
    Normalizes an empirical ACK matrix of shape (num_trials, num_segments) so that
    only the segment index k that actually emitted each cumulative ACK is finite
    (converting any legacy back-filled consecutive duplicate timestamps to NaN),
    and computes a second matrix of shape (num_trials, num_segments) holding the
    number of segments newly acknowledged (delta_k) by each emitted ACK packet.
    """
    emitted = np.array(ack_matrix, dtype=float, copy=True)
    delta_k = np.full_like(emitted, np.nan)
    num_trials, num_segs = emitted.shape
    for t_idx in range(num_trials):
        row = emitted[t_idx]
        # Convert legacy back-filled runs (row[k] == row[k+1]) to NaN except at the run's end
        for k in range(num_segs - 1):
            if np.isfinite(row[k]) and np.isfinite(row[k + 1]) and abs(row[k] - row[k + 1]) < 1e-9:
                row[k] = np.nan
        prev_k = 0
        for k in range(num_segs):
            if np.isfinite(row[k]):
                seg_num = k + 1
                delta_k[t_idx, k] = float(seg_num - prev_k)
                prev_k = seg_num
    return emitted, delta_k

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
                p_router = subprocess.Popen(["sudo", "ip", "netns", "exec", "ns_router", "tcpdump", "-i", "any", "tcp", "port", str(port), "-w", router_pcap], stderr=subprocess.DEVNULL)
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

                ixp_times        = process_pcap_arrivals(r_pkts, isn, t0, num_segments)
                dest_times       = process_pcap_arrivals(s_pkts, isn, t0, num_segments)
                ack_ixp_times    = process_pcap_acks(r_pkts, isn, t0, num_segments)
                ack_sender_times = process_pcap_acks(c_pkts, isn, t0, num_segments)

                for f in [client_pcap, router_pcap, server_pcap]:
                    if os.path.exists(f): os.remove(f)

                valid_ixp        = sum(1 for t in ixp_times if t is not None)
                valid_dest       = sum(1 for t in dest_times if t is not None)
                valid_ack_ixp    = sum(1 for t in ack_ixp_times if t is not None)
                valid_ack_sender = sum(1 for t in ack_sender_times if t is not None)

                if valid_ixp > 0 and valid_dest > 0 and valid_ack_ixp > 0 and valid_ack_sender > 0:
                    return [ixp_times, dest_times, ack_ixp_times, ack_sender_times]
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
    
    # Shape: (num_trials, 4 [ixp, dest, ack_ixp, ack_sender], num_segments)
    # Also supports legacy cached arrays of shape (num_trials, 2, num_segments).
    trials_matrix = np.array(all_trials_data, dtype=float)
    has_empirical_acks = trials_matrix.ndim == 3 and trials_matrix.shape[1] >= 4
    
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        emp_ixp_mean   = np.nanmean(trials_matrix[:, 0, :], axis=0)
        emp_ixp_median = np.nanmedian(trials_matrix[:, 0, :], axis=0)
        emp_ixp_p25    = np.nanpercentile(trials_matrix[:, 0, :], 25, axis=0)
        emp_ixp_p75    = np.nanpercentile(trials_matrix[:, 0, :], 75, axis=0)
        
        emp_dest_mean    = np.nanmean(trials_matrix[:, 1, :], axis=0)
        emp_dest_median  = np.nanmedian(trials_matrix[:, 1, :], axis=0)
        emp_dest_p25     = np.nanpercentile(trials_matrix[:, 1, :], 25, axis=0)
        emp_dest_p75     = np.nanpercentile(trials_matrix[:, 1, :], 75, axis=0)

        if has_empirical_acks:
            emitted_ack_ixp, _ = _extract_emitted_ack_matrix(trials_matrix[:, 2, :])
            emitted_ack_snd, emp_ack_delta_k = _extract_emitted_ack_matrix(trials_matrix[:, 3, :])

            emp_ack_ixp_mean   = np.nanmean(emitted_ack_ixp, axis=0)
            emp_ack_ixp_median = np.nanmedian(emitted_ack_ixp, axis=0)
            emp_ack_ixp_p25    = np.nanpercentile(emitted_ack_ixp, 25, axis=0)
            emp_ack_ixp_p75    = np.nanpercentile(emitted_ack_ixp, 75, axis=0)

            emp_ack_snd_mean   = np.nanmean(emitted_ack_snd, axis=0)
            emp_ack_snd_median = np.nanmedian(emitted_ack_snd, axis=0)
            emp_ack_snd_p25    = np.nanpercentile(emitted_ack_snd, 25, axis=0)
            emp_ack_snd_p75    = np.nanpercentile(emitted_ack_snd, 75, axis=0)

            emp_delta_mean     = np.nanmean(emp_ack_delta_k, axis=0)
            emp_delta_median   = np.nanmedian(emp_ack_delta_k, axis=0)
            emp_delta_p25      = np.nanpercentile(emp_ack_delta_k, 25, axis=0)
            emp_delta_p75      = np.nanpercentile(emp_ack_delta_k, 75, axis=0)

    N = num_segments
    model_ixp, model_dest, model_ack_ixp, model_ack_sender = [], [], [], []
    flights = {}
    
    for k in range(1, N + 1):
        t_ixp_k, t_dest_k, t_ack_ixp_k, t_ack_sender_k, f_k = expected_time_k(k, max_k=N)
        model_ixp.append(t_ixp_k * 1000.0)
        model_dest.append(t_dest_k * 1000.0)
        model_ack_ixp.append(t_ack_ixp_k * 1000.0)
        model_ack_sender.append(t_ack_sender_k * 1000.0)
        if f_k not in flights:
            flights[f_k] = []
        flights[f_k].append(k)

    fig, (ax1, ax2, ax3, ax4, ax5) = plt.subplots(5, 1, figsize=(12, 22), sharex=True)
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
    # Subplot 1: IXP Data Arrivals
    # --------------------------------------------------------------------------
    # The pcaps already include physical network delays. We apply a uniform 
    # alignment offset (50ms) to both hops to account for the model's TLS handshake 
    # start time (80ms) vs the empirical start time (30ms).
    alignment_offset = 50.0

    ax1.plot(k_vals, model_ixp, label='Model IXP ($E[T_{k, ixp}]$)', color='blue', linewidth=2)
    ax1.plot(k_vals, emp_ixp_mean + alignment_offset, label='Empirical IXP (Mean)', color='red', linewidth=2)
    ax1.plot(k_vals, emp_ixp_median + alignment_offset, label='Empirical IXP (Median)', color='darkred', linestyle='--', linewidth=1.5)
    ax1.fill_between(k_vals, emp_ixp_p25 + alignment_offset, emp_ixp_p75 + alignment_offset, color='red', alpha=0.2, label='Empirical 25th-75th %ile')
    
    add_flight_spans(ax1)
    ax1.set_ylabel('Relative Arrival Time (ms)', fontsize=11)
    ax1.set_title('IXP Data Arrival Times (Link 1 Router Ingress)', fontsize=12, fontweight='bold')
    ax1.grid(True, linestyle=':', alpha=0.7)
    
    handles1, labels1 = ax1.get_legend_handles_labels()
    by_label1 = dict(zip(labels1, handles1))
    ax1.legend(by_label1.values(), by_label1.keys(), loc='upper left')

    # --------------------------------------------------------------------------
    # Subplot 2: Final Destination Data Arrivals
    # --------------------------------------------------------------------------
    ax2.plot(k_vals, model_dest, label='Model Dest Arrival ($E[T_{k, dest}]$)', color='blue', linewidth=2)
    ax2.plot(k_vals, emp_dest_mean + alignment_offset, label='Empirical Dest (Mean)', color='red', linewidth=2)
    ax2.plot(k_vals, emp_dest_median + alignment_offset, label='Empirical Dest (Median)', color='darkred', linestyle='--', linewidth=1.5)
    ax2.fill_between(k_vals, emp_dest_p25 + alignment_offset, emp_dest_p75 + alignment_offset, color='red', alpha=0.2, label='Empirical 25th-75th %ile')
    
    add_flight_spans(ax2)
    ax2.set_ylabel('Relative Arrival Time (ms)', fontsize=11)
    ax2.set_title('Final Destination Data Arrival Times (Link 2 Server Ingress)', fontsize=12, fontweight='bold')
    ax2.grid(True, linestyle=':', alpha=0.7)

    handles2, labels2 = ax2.get_legend_handles_labels()
    by_label2 = dict(zip(labels2, handles2))
    ax2.legend(by_label2.values(), by_label2.keys(), loc='upper left')

    # --------------------------------------------------------------------------
    # Subplot 3: IXP ACK Arrivals (Discrete ACK Packets)
    # --------------------------------------------------------------------------
    ack_ixp_k_vals = [k for k, v in zip(k_vals, model_ack_ixp) if np.isfinite(v)]
    ack_ixp_y_vals = [v for v in model_ack_ixp if np.isfinite(v)]
    ax3.plot(ack_ixp_k_vals, ack_ixp_y_vals, label='Model IXP ACK Packets ($E[T_{ack, k, ixp}]$)',
             color='blue', linewidth=1.5, marker='o', markersize=3.5)
    if has_empirical_acks:
        emp_ixp_ack_mask = np.isfinite(emp_ack_ixp_mean)
        emp_ixp_k = np.array(k_vals)[emp_ixp_ack_mask]
        ax3.plot(emp_ixp_k, emp_ack_ixp_mean[emp_ixp_ack_mask] + alignment_offset,
                 label='Empirical IXP ACK Packets (Mean)', color='red', linewidth=1.5, marker='x', markersize=3.5)
        ax3.plot(emp_ixp_k, emp_ack_ixp_median[emp_ixp_ack_mask] + alignment_offset,
                 label='Empirical IXP ACK Packets (Median)', color='darkred', linestyle='--', linewidth=1.2)
        ax3.fill_between(emp_ixp_k,
                         emp_ack_ixp_p25[emp_ixp_ack_mask] + alignment_offset,
                         emp_ack_ixp_p75[emp_ixp_ack_mask] + alignment_offset,
                         color='red', alpha=0.2, label='Empirical 25th-75th %ile')

    add_flight_spans(ax3)
    ax3.set_ylabel('Relative Arrival Time (ms)', fontsize=11)
    ax3.set_title('IXP ACK Arrival Times (Discrete Emitted ACK Packets)', fontsize=12, fontweight='bold')
    ax3.grid(True, linestyle=':', alpha=0.7)

    handles3, labels3 = ax3.get_legend_handles_labels()
    by_label3 = dict(zip(labels3, handles3))
    ax3.legend(by_label3.values(), by_label3.keys(), loc='upper left')

    # --------------------------------------------------------------------------
    # Subplot 4: Sender ACK Arrivals (Discrete ACK Packets)
    # --------------------------------------------------------------------------
    ack_snd_k_vals = [k for k, v in zip(k_vals, model_ack_sender) if np.isfinite(v)]
    ack_snd_y_vals = [v for v in model_ack_sender if np.isfinite(v)]
    ax4.plot(ack_snd_k_vals, ack_snd_y_vals, label='Model Sender ACK Packets ($E[T_{ack, k, sender}]$)',
             color='blue', linewidth=1.5, marker='o', markersize=3.5)
    if has_empirical_acks:
        emp_snd_ack_mask = np.isfinite(emp_ack_snd_mean)
        emp_snd_k = np.array(k_vals)[emp_snd_ack_mask]
        ax4.plot(emp_snd_k, emp_ack_snd_mean[emp_snd_ack_mask] + alignment_offset,
                 label='Empirical Sender ACK Packets (Mean)', color='red', linewidth=1.5, marker='x', markersize=3.5)
        ax4.plot(emp_snd_k, emp_ack_snd_median[emp_snd_ack_mask] + alignment_offset,
                 label='Empirical Sender ACK Packets (Median)', color='darkred', linestyle='--', linewidth=1.2)
        ax4.fill_between(emp_snd_k,
                         emp_ack_snd_p25[emp_snd_ack_mask] + alignment_offset,
                         emp_ack_snd_p75[emp_snd_ack_mask] + alignment_offset,
                         color='red', alpha=0.2, label='Empirical 25th-75th %ile')

    add_flight_spans(ax4)
    ax4.set_ylabel('Relative Arrival Time (ms)', fontsize=11)
    ax4.set_title('Sender ACK Arrival Times (Discrete Emitted ACK Packets)', fontsize=12, fontweight='bold')
    ax4.grid(True, linestyle=':', alpha=0.7)

    handles4, labels4 = ax4.get_legend_handles_labels()
    by_label4 = dict(zip(labels4, handles4))
    ax4.legend(by_label4.values(), by_label4.keys(), loc='upper left')

    # --------------------------------------------------------------------------
    # Subplot 5: Segments Newly Acknowledged per Emitted ACK Packet (Delta k)
    # --------------------------------------------------------------------------
    model_ack_deltas = np.diff([0] + ack_snd_k_vals)
    ax5.step(ack_snd_k_vals, model_ack_deltas, where='post',
             label='Model Segments per ACK ($\\Delta k$: 1=QuickACK, 2=Delayed ACK)',
             color='blue', linewidth=2, marker='o', markersize=4)
    if has_empirical_acks:
        emp_delta_mask = np.isfinite(emp_delta_mean)
        emp_delta_k_vals = np.array(k_vals)[emp_delta_mask]
        ax5.plot(emp_delta_k_vals, emp_delta_mean[emp_delta_mask],
                 label='Empirical Segments per ACK (Mean $\\Delta k$)',
                 color='red', linewidth=1.5, marker='x', markersize=4)
        ax5.plot(emp_delta_k_vals, emp_delta_median[emp_delta_mask],
                 label='Empirical Segments per ACK (Median $\\Delta k$)',
                 color='darkred', linestyle='--', linewidth=1.5)
        ax5.fill_between(emp_delta_k_vals,
                         emp_delta_p25[emp_delta_mask],
                         emp_delta_p75[emp_delta_mask],
                         color='red', alpha=0.2, label='Empirical 25th-75th %ile')

    add_flight_spans(ax5)
    ax5.set_xlabel('Acknowledged Segment Index ($k$)', fontsize=12)
    ax5.set_ylabel('Segments / ACK ($\\Delta k$)', fontsize=11)
    ax5.set_title('ACK Granularity: Newly Acknowledged Segments per ACK Packet ($\\Delta k = 1$ Single, $\\Delta k = 2$ Every Other, $\\Delta k > 2$ Stretch)',
                  fontsize=12, fontweight='bold')
    ax5.set_yticks(range(1, max(4, int(np.nanmax(emp_delta_mean)) + 2 if has_empirical_acks and np.any(np.isfinite(emp_delta_mean)) else 4)))
    ax5.grid(True, linestyle=':', alpha=0.7)

    handles5, labels5 = ax5.get_legend_handles_labels()
    by_label5 = dict(zip(labels5, handles5))
    ax5.legend(by_label5.values(), by_label5.keys(), loc='upper left')

    fig.suptitle(f'2-Hop TCP Data & ACK Delivery Validation ({len(all_trials_data)} Trials - L1: {args.tc_profile}, L2: {l2_prof})', fontsize=14, y=0.995)
    
    plt.tight_layout()
    plot_file = 'tcp_validation_plot.png'
    plt.savefig(plot_file, dpi=300)
    print(f"Plot successfully saved to {plot_file}")

    total_retrans = get_total_retransmissions()
    model_unique_acks = len(ack_snd_y_vals)
    print(f"\n[MODEL OUTPUT] Total Expected Retransmissions (L1: '{args.tc_profile}', L2: '{l2_prof}'): {total_retrans:.2f}")
    print(f"[MODEL OUTPUT] Expected Cumulative ACKs for {N} segments: {model_unique_acks}")
    if has_empirical_acks:
        emp_unique_acks_per_trial = [
            int(np.sum(np.isfinite(row)))
            for row in emitted_ack_snd
        ]
        print(f"[EMPIRICAL]    Mean Cumulative ACKs across {len(all_trials_data)} trials: {np.mean(emp_unique_acks_per_trial):.2f} (median: {np.median(emp_unique_acks_per_trial):.1f})")
    else:
        print("[NOTE] Cached .npy array only contains 2 channels (data arrivals); run without --cached to capture empirical ACK arrival times.")