import subprocess
import os
import sys
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
        t_k, _ = tcp_analytical_model.expected_time_k(k)
        times.append(t_k)
    return times

def get_maude_times(profile, num_bytes):
    if profile == 'none':
        p13, p31, p32, p23, p14 = 0.0, 1.0, 0.0, 0.0, 0.0
    elif profile == 'fair':
        p13, p31, p32, p23, p14 = 0.005, 0.20, 0.40, 0.30, 0.002
    else:
        raise ValueError(f"Unknown profile {profile}")
        
    O = 0.02
    
    # Resolve the path to tcp.maude based on script location
    project_root = os.path.dirname(script_dir)
    tcp_maude_path = os.path.join(project_root, 'maude_hcs', 'lib', 'tcp', 'tcp.maude')
    
    maude_cmd = f"""
load {tcp_maude_path}
red tcpDeliveryTimes({num_bytes}, {p13}, {p31}, {p32}, {p23}, {p14}, {O}) .
quit
"""
    # Assuming maude is in PATH or we can find it
    # First try `maude` directly
    maude_bin = 'maude'
    
    # Fallback to absolute path we know worked in earlier tests if `maude` isn't in PATH
    try:
        subprocess.run([maude_bin, '-no-banner', '-batch'], input=maude_cmd, text=True, capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        maude_bin = '/Users/dcirimel/pwnd2/maude/maude'

    print(f"Using Maude binary: {maude_bin}")
    result = subprocess.run([maude_bin, '-no-banner'], 
                            input=maude_cmd, text=True, capture_output=True)
    
    output = result.stdout
    times = []
    
    # Find the LAST result FloatList since loading tcp.maude outputs hardcoded test results first
    last_idx = output.rfind('result FloatList:')
    if last_idx != -1:
        list_str = output[last_idx + len('result FloatList:'):]
        end_idx = list_str.find('nilFL')
        if end_idx != -1:
            list_str = list_str[:end_idx]
            
        elements = [e.strip() for e in list_str.replace('\n', ' ').split('::') if e.strip()]
        for e in elements:
            try:
                times.append(float(e))
            except ValueError:
                pass
            
    return times

def main():
    num_bytes = 72400 * 5 # 50 segments
    
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
