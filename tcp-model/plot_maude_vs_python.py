import subprocess
import os
import sys
import shutil
import matplotlib.pyplot as plt

# Add the tcp-model directory to path to import tcp_analytical_model
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)
import tcp_analytical_model

def get_python_times(profile, num_bytes):
    tcp_analytical_model.set_active_profile(profile)
    num_segments = num_bytes // 1448
    times = []
    for k in range(1, num_segments + 1):
        _, t_k, _ = tcp_analytical_model.expected_time_k(k)
        times.append(t_k)
    return times

def get_maude_times(profile, num_bytes):
    if profile in tcp_analytical_model.PROFILES:
        drop_p = tcp_analytical_model.PROFILES[profile]
    elif isinstance(profile, (int, float)):
        drop_p = float(profile)
    else:
        raise ValueError(f"Unknown profile {profile}")
        
    O = 0.01
    
    # Resolve the path to tcp.maude based on script location
    project_root = os.path.dirname(script_dir)
    tcp_maude_path = os.path.join(project_root, 'maude_hcs', 'lib', 'network', 'tcp.maude')
    
    maude_cmd = f"""load {tcp_maude_path}
red tcpFinalDestTimes({num_bytes}, (dropP: {drop_p}, oneWayDelay: {O})) .
quit
"""
    # Locate maude binary or use conda environment
    maude_bin = shutil.which('maude')
    output = ""
    
    if maude_bin:
        result = subprocess.run([maude_bin, '-no-banner', '-batch'], 
                                input=maude_cmd, text=True, capture_output=True)
        output = result.stdout
    else:
        # Fallback: run via conda maude-hcs environment using python-maude bridge
        py_runner = f"""import maude
maude.init()
maude.load('{tcp_maude_path}')
m = maude.getCurrentModule()
term = m.parseTerm('tcpFinalDestTimes({num_bytes}, (dropP: {drop_p}, oneWayDelay: {O}))')
term.reduce()
print('result FloatList:', term)
"""
        result = subprocess.run(['conda', 'run', '-n', 'maude-hcs', 'python3', '-c', py_runner],
                                text=True, capture_output=True)
        output = result.stdout

    times = []
    
    # Find the LAST result FloatList since loading tcp.maude outputs hardcoded test results first
    last_idx = output.rfind('result FloatList:')
    if last_idx != -1:
        res_text = output[last_idx:]
        res_text = res_text.split('result FloatList:')[1].split('\nBye.')[0]
        # Clean up string
        res_text = res_text.replace('\n', ' ').replace('::', ' ').replace('nilFL', ' ')
        tokens = res_text.split()
        all_times = []
        for t in tokens:
            t = t.strip()
            if t:
                try:
                    all_times.append(float(t))
                except ValueError:
                    pass
        # Skip the 5 prepended handshake timestamps for new connections
        times = all_times[5:] if len(all_times) > 5 else all_times
            
    return times

def main():
    num_bytes = 72400 * 5  # 250 segments
    
    print("Running Python 'none'...")
    py_none = get_python_times('none', num_bytes)
    print("Running Python 'fair'...")
    py_fair = get_python_times('fair', num_bytes)
    
    print("Running Maude 'none'...")
    md_none = get_maude_times('none', num_bytes)
    print("Running Maude 'fair'...")
    md_fair = get_maude_times('fair', num_bytes)
    
    print(f"Lengths - Py None: {len(py_none)}, Md None: {len(md_none)}")
    print(f"Lengths - Py Fair: {len(py_fair)}, Md Fair: {len(md_fair)}")
    
    if len(py_none) == len(md_none) and len(py_none) > 0:
        max_diff_none = max(abs(p - m) for p, m in zip(py_none, md_none))
        print(f"Max absolute difference ('none'): {max_diff_none:.6e} s")
    if len(py_fair) == len(md_fair) and len(py_fair) > 0:
        max_diff_fair = max(abs(p - m) for p, m in zip(py_fair, md_fair))
        print(f"Max absolute difference ('fair'): {max_diff_fair:.6e} s")
    
    plt.figure(figsize=(12, 6))
    
    # Plot None Profile
    plt.subplot(1, 2, 1)
    if py_none: plt.plot(py_none, label='Python Analytical', linewidth=4, color='blue', alpha=0.5)
    if md_none: plt.plot(md_none, label='Maude Model', linewidth=2, color='red', linestyle='--')
    plt.title('None Profile (Buffer Capacity Path)')
    plt.xlabel('Segment Index (k)')
    plt.ylabel('Expected Arrival Time (s)')
    plt.legend()
    plt.grid(True)
    
    # Plot Fair Profile
    plt.subplot(1, 2, 2)
    if py_fair: plt.plot(py_fair, label='Python Analytical', linewidth=4, color='blue', alpha=0.5)
    if md_fair: plt.plot(md_fair, label='Maude Model', linewidth=2, color='red', linestyle='--')
    plt.title('Fair Profile (No-Buffer Path)')
    plt.xlabel('Segment Index (k)')
    plt.ylabel('Expected Arrival Time (s)')
    plt.legend()
    plt.grid(True)
    
    plt.tight_layout()
    out_path = os.path.join(script_dir, 'maude_vs_python_comparison.png')
    plt.savefig(out_path, dpi=300)
    print(f"Plot saved to {out_path}")

if __name__ == '__main__':
    main()
