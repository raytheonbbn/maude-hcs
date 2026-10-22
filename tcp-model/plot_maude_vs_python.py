import subprocess
import os
import sys
import shutil
import re
import matplotlib
from matplotlib.path import Path
# Workaround for Python 3.14 super() deepcopy recursion in matplotlib
Path.__deepcopy__ = lambda self, memo: Path(self.vertices.copy(), self.codes.copy() if self.codes is not None else None)
import matplotlib.pyplot as plt

# Add the tcp-model directory to path to import tcp_analytical_model
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)
import tcp_analytical_model

def get_python_transfer(profile, num_bytes, is_new=True, state=None, *, start_time):
    tcp_analytical_model.set_active_profile(profile)
    num_segments = num_bytes // 1448
    _, t_dest, final_state = tcp_analytical_model.simulate_transfer(num_segments, is_new=is_new, state=state, start_time=start_time)
    return list(t_dest), final_state

def get_maude_transfer(profile, num_bytes, is_new=True, state=None, *, start_time):
    if profile in tcp_analytical_model.PROFILES:
        drop_p = tcp_analytical_model.PROFILES[profile]
    elif isinstance(profile, (int, float)):
        drop_p = float(profile)
    else:
        raise ValueError(f"Unknown profile {profile}")
        
    O = 0.01
    project_root = os.path.dirname(script_dir)
    tcp_maude_path = os.path.join(project_root, 'maude_hcs', 'lib', 'network', 'tcp.maude')
    
    is_new_str = 'true' if is_new else 'false'
    if state is None:
        state_str = 'initTcpState'
    else:
        in_ss_str = 'true' if getattr(state, 'in_slow_start', False) else 'false'
        last_send = -1.0 if state.last_send_time is None else state.last_send_time
        last_ack = -1.0 if state.last_ack_time is None else state.last_ack_time
        state_str = f'tcpState({state.cwnd}, {state.w_max}, {state.t_since}, {in_ss_str}, {last_send}, {last_ack})'
        
    py_runner = f"""import maude, re
maude.init()
maude.load('{tcp_maude_path}')
m = maude.getCurrentModule()
term = m.parseTerm('tcpFinalDestResult({num_bytes}, (dropP: {drop_p}, oneWayDelay: {O}), (dropP: {drop_p}, oneWayDelay: {O}), {is_new_str}, {state_str}, {start_time})')
term.reduce()
print('RESULT_TAG:', str(term))
"""
    try:
        import maude
        m = maude.getCurrentModule()
        if m is None:
            maude.init()
            maude.load(tcp_maude_path)
            m = maude.getCurrentModule()
        term = m.parseTerm(f'tcpFinalDestResult({num_bytes}, (dropP: {drop_p}, oneWayDelay: {O}), (dropP: {drop_p}, oneWayDelay: {O}), {is_new_str}, {state_str}, {start_time})')
        term.reduce()
        res_str = str(term)
    except Exception:
        result = subprocess.run(['conda', 'run', '-n', 'maude-hcs', 'python3', '-c', py_runner],
                                text=True, capture_output=True)
        out = result.stdout
        idx = out.rfind('RESULT_TAG:')
        res_str = out[idx + len('RESULT_TAG:'):].strip()

    state_match = re.search(r'tcpState\(([^,]+),\s*([^,]+),\s*([^,]+),\s*(true|false),\s*([^,]+),\s*([^)]+)\)', res_str)
    if not state_match:
        raise ValueError(f"Could not parse state from: {res_str}")
    cwnd = float(state_match.group(1))
    w_max = float(state_match.group(2))
    t_since = float(state_match.group(3))
    in_ss = state_match.group(4).strip() == 'true'
    last_send = float(state_match.group(5))
    last_ack = float(state_match.group(6))
    final_state = tcp_analytical_model.TcpState(
        cwnd, w_max, t_since, in_slow_start=in_ss,
        last_send_time=last_send if last_send >= 0.0 else None,
        last_ack_time=last_ack if last_ack >= 0.0 else None)

    times_part = res_str[res_str.find('tlR(') + 4: state_match.start()].rstrip(', ')
    tokens = times_part.replace('\n', ' ').replace('::', ' ').replace('nilFL', ' ').split()
    all_times = [float(t.strip()) for t in tokens if t.strip()]
    times = all_times[5:] if is_new else all_times
    return times, final_state

def main():
    # Transfer 1: New connection (40 segments = 57920 bytes)
    # Transfer 2: Reused connection (80 segments = 115840 bytes)
    bytes_t1 = 57920
    bytes_t2 = 115840
    
    profiles = [('none', 'None Profile (Buffer Capacity Path)'),
                ('fair', 'Fair Profile (No-Buffer Path)')]
    
    plt.figure(figsize=(14, 10))
    subplot_idx = 1
    
    for prof_name, prof_desc in profiles:
        print(f"\n{'='*20} Testing {prof_desc} {'='*20}")
        # --- Transfer 1 (New Connection) ---
        print(f"Running Python Transfer 1 (New Connection, 40 segments)...")
        py_t1, py_s1 = get_python_transfer(prof_name, bytes_t1, is_new=True, start_time=0.0)
        print(f"Running Maude Transfer 1 (New Connection, 40 segments)...")
        md_t1, md_s1 = get_maude_transfer(prof_name, bytes_t1, is_new=True, start_time=0.0)
        
        diff_t1 = max(abs(p - m) for p, m in zip(py_t1, md_t1))
        diff_s1_cwnd = abs(py_s1.cwnd - md_s1.cwnd)
        diff_s1_wmax = abs(py_s1.w_max - md_s1.w_max)
        diff_s1_ts = abs(py_s1.t_since - md_s1.t_since)
        print(f"Transfer 1 -> Max time diff: {diff_t1:.6e} s | cwnd diff: {diff_s1_cwnd:.6e} | w_max diff: {diff_s1_wmax:.6e}")
        print(f"  Python Final State: {py_s1}")
        print(f"  Maude  Final State: {md_s1}")
        
        # --- Transfer 2 (Reused Connection) ---
        print(f"Running Python Transfer 2 (Reused Connection, 80 segments)...")
        py_t2, py_s2 = get_python_transfer(prof_name, bytes_t2, is_new=False, state=py_s1, start_time=py_s1.last_ack_time)
        print(f"Running Maude Transfer 2 (Reused Connection, 80 segments)...")
        md_t2, md_s2 = get_maude_transfer(prof_name, bytes_t2, is_new=False, state=md_s1, start_time=md_s1.last_ack_time)
        
        diff_t2 = max(abs(p - m) for p, m in zip(py_t2, md_t2))
        diff_s2_cwnd = abs(py_s2.cwnd - md_s2.cwnd)
        diff_s2_wmax = abs(py_s2.w_max - md_s2.w_max)
        diff_s2_ts = abs(py_s2.t_since - md_s2.t_since)
        print(f"Transfer 2 -> Max time diff: {diff_t2:.6e} s | cwnd diff: {diff_s2_cwnd:.6e} | w_max diff: {diff_s2_wmax:.6e}")
        print(f"  Python Final State: {py_s2}")
        print(f"  Maude  Final State: {md_s2}")
        
        # Plot Transfer 1
        plt.subplot(2, 2, subplot_idx)
        plt.plot(range(1, len(py_t1) + 1), py_t1, label='Python Analytical', linewidth=4, color='blue', alpha=0.5)
        plt.plot(range(1, len(md_t1) + 1), md_t1, label='Maude Model', linewidth=2, color='red', linestyle='--')
        plt.title(f"{prof_name.capitalize()} - Transfer 1 (New Connection)")
        plt.xlabel('Segment Index (k)')
        plt.ylabel('Expected Arrival Time (s)')
        plt.legend()
        plt.grid(True)
        subplot_idx += 1
        
        # Plot Transfer 2
        plt.subplot(2, 2, subplot_idx)
        plt.plot(range(1, len(py_t2) + 1), py_t2, label='Python Analytical', linewidth=4, color='green', alpha=0.5)
        plt.plot(range(1, len(md_t2) + 1), md_t2, label='Maude Model', linewidth=2, color='purple', linestyle='--')
        plt.title(f"{prof_name.capitalize()} - Transfer 2 (Reused Connection)")
        plt.xlabel('Follow-up Segment Index')
        plt.ylabel('Expected Arrival Time (s)')
        plt.legend()
        plt.grid(True)
        subplot_idx += 1

    plt.tight_layout()
    out_path = os.path.join(script_dir, 'maude_vs_python_comparison.png')
    plt.savefig(out_path, dpi=300)
    print(f"\nPlot successfully saved to {out_path}")

if __name__ == '__main__':
    main()
