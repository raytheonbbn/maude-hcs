import os
import argparse
import json
import math
import glob
import re
import matplotlib.pyplot as plt

def bernoulli_kl(q, p):
    if not (0 <= p <= 1 and 0 <= q <= 1):
        raise ValueError("p and q must be in [0,1]")

    if q == p:
        return 0.0

    if p == 0:
        return math.inf if q > 0 else 0.0

    if p == 1:
        return math.inf if q < 1 else 0.0

    if q == 0:
        return math.log(1 / (1 - p))

    if q == 1:
        return math.log(1 / p)

    return (
        q * math.log(q / p) +
        (1 - q) * math.log((1 - q) / (1 - p))
    )

def certified_kl_lower_bound(tpr_mean, tpr_radius, fpr_mean, fpr_radius):
    if tpr_radius == 0.0:
        tpr_radius = 0.0122
    if fpr_radius == 0.0:
        fpr_radius = 0.0122

    q_low  = tpr_mean - tpr_radius
    q_high = tpr_mean + tpr_radius

    p_low  = fpr_mean - fpr_radius
    p_high = fpr_mean + fpr_radius

    q_low  = max(0.0, min(1.0, q_low))
    q_high = max(0.0, min(1.0, q_high))

    p_low  = max(0.0, min(1.0, p_low))
    p_high = max(0.0, min(1.0, p_high))

    if q_low <= p_high and p_low <= q_high:
        return 0.0
    elif q_low > p_high:
        return bernoulli_kl(q_low, p_high)
    else:
        return bernoulli_kl(q_high, p_low)

def check_intervals_overlap(tpr_mean, tpr_radius, fpr_mean, fpr_radius):
    """Checks if the TPR and FPR mean intervals overlap."""
    tpr_low = tpr_mean - tpr_radius
    tpr_high = tpr_mean + tpr_radius
    fpr_low = fpr_mean - fpr_radius
    fpr_high = fpr_mean + fpr_radius

    return tpr_low <= fpr_high and fpr_low <= tpr_high

def safe_kl(tpr_mean, tpr_radius, fpr_mean, fpr_radius):
    """Wrapper to handle ValueErrors when means are <= 0 by returning NaN."""
    try:
        return certified_kl_lower_bound(tpr_mean, tpr_radius, fpr_mean, fpr_radius)
    except ValueError as e:
        print(f"    [!] Skipping a KL bound computation: {e}")
        return float('nan')


# Query mapping
QUERY_NAMES = [
    "latency", "goodput", "FilesC2", "FilesC8", "FilesMA1",
    "OpDurC2", "OpDurC8", "OpDurMA1", "AlarmC2", "AlarmC8", "AlarmMA1"
]
Q_IDX = {name: i for i, name in enumerate(QUERY_NAMES)}


def process_directory(input_dir):
    # Set parameters for large fonts and readability
    plt.rcParams.update({
        'font.size': 20,
        'axes.titlesize': 22,
        'axes.labelsize': 20,
        'legend.fontsize': 18,
        'figure.autolayout': True  # Equivalent to tight_layout
    })

    # Create an output directory for plots
    out_dir = os.path.join(input_dir, "plotsv2")
    os.makedirs(out_dir, exist_ok=True)

    # Find all ordinary (tgenonly) files
    ord_files = glob.glob(os.path.join(input_dir, "*_tgenonly.json"))

    if not ord_files:
        print(f"No '*_tgenonly.json' files found in '{input_dir}'.")
        return

    for ord_file in ord_files:
        hcs_file = ord_file.replace("_tgenonly.json", ".json")
        if not os.path.exists(hcs_file):
            print(f"Warning: HCS file missing for {os.path.basename(ord_file)}. Skipping.")
            continue

        # Extract clean scenario name (e.g., 'Scenario 7')
        base_name = os.path.basename(hcs_file).replace(".json", "")
        m = re.search(r'scenario_(\d+)', base_name)
        scenario_title = f"Scenario {m.group(1)}" if m else base_name

        print(f"Processing {scenario_title}...")

        with open(ord_file, 'r') as f:
            ord_data = json.load(f)
        with open(hcs_file, 'r') as f:
            hcs_data = json.load(f)

        # Merge and sort data based on wait time descending
        data_points = []
        for key, hcs_val in hcs_data.items():
            if key not in ord_data:
                continue

            data_points.append({
                'wait_time': hcs_val['cli_wait_time'],
                'hcs': hcs_val['scheck']['queries'],
                'ord': ord_data[key]['scheck']['queries']
            })

        # Sort decreasing
        data_points.sort(key=lambda x: x['wait_time'], reverse=True)
        wait_times = [dp['wait_time'] for dp in data_points]

        # ==========================================
        # Plot 1: Mean and Radius vs Wait Times
        # ==========================================
        plot1_queries = ["goodput", "OpDurC2", "OpDurC8", "OpDurMA1", "AlarmC2", "AlarmC8", "AlarmMA1"]
        fig1, axs1 = plt.subplots(3, 3, figsize=(18, 15))
        axs1 = axs1.flatten()

        for i, q in enumerate(plot1_queries):
            ax = axs1[i]
            q_idx = Q_IDX[q]
            means = [dp['hcs'][q_idx]['mean'] for dp in data_points]
            radii = [dp['hcs'][q_idx]['radius'] for dp in data_points]

            ax.errorbar(wait_times, means, yerr=radii, fmt='-o', capsize=6, markersize=8, linewidth=2)
            ax.set_xlabel("Client Wait Time")
            ax.set_ylabel("Mean Value")
            ax.set_title(f"{scenario_title} - {q}")
            ax.invert_xaxis()  # Ensure decreasing order from left to right
            ax.grid(True, linestyle='--', alpha=0.6)

        # Hide unused subplots
        for j in range(len(plot1_queries), len(axs1)):
            fig1.delaxes(axs1[j])

        fig1.tight_layout()
        fig1.savefig(os.path.join(out_dir, f"{base_name}_plot1_means.png"))
        plt.close(fig1)

        # ==========================================
        # Plot 2: Certified KL Bounds vs Wait Times
        # ==========================================
        plot2_queries = ["AlarmC2", "AlarmC8", "AlarmMA1"]
        fig2, axs2 = plt.subplots(1, 3, figsize=(18, 6))

        kl_data_cache = {q: [] for q in plot2_queries}

        for i, q in enumerate(plot2_queries):
            ax = axs2[i]
            q_idx = Q_IDX[q]

            kl_vals = []
            for dp in data_points:
                tpr_m, tpr_r = dp['hcs'][q_idx]['mean'], dp['hcs'][q_idx]['radius']
                fpr_m, fpr_r = dp['ord'][q_idx]['mean'], dp['ord'][q_idx]['radius']
                kl_vals.append(safe_kl(tpr_m, tpr_r, fpr_m, fpr_r))

            kl_data_cache[q] = kl_vals

            ax.plot(wait_times, kl_vals, '-o', markersize=8, linewidth=2, color='darkorange')
            ax.set_xlabel("Client Wait Time")
            ax.set_ylabel("Certified KL Lower Bound")
            ax.set_title(f"{scenario_title} - {q}")
            ax.invert_xaxis()  # Ensure decreasing order from left to right
            ax.grid(True, linestyle='--', alpha=0.6)

        fig2.tight_layout()
        fig2.savefig(os.path.join(out_dir, f"{base_name}_plot2_kl.png"))
        plt.close(fig2)

        # ==========================================
        # Plot 3: Privacy-Performance Tradeoff
        # ==========================================
        fig3, ax3 = plt.subplots(figsize=(10, 8))

        goodput_idx = Q_IDX["goodput"]
        goodputs = [dp['hcs'][goodput_idx]['mean'] for dp in data_points]
        AlarmC8_kls = kl_data_cache["AlarmC8"]

        ax3.plot(goodputs, AlarmC8_kls, '-o', markersize=10, linewidth=2, color='purple')
        ax3.set_xlabel("Goodput")
        ax3.set_ylabel("Certified KL Lower Bound (AlarmC8)")
        ax3.set_title(f"Privacy-Performance Tradeoff ({scenario_title})")
        ax3.grid(True, linestyle='--', alpha=0.6)

        # Annotate nodes with corresponding Wait Time values for clarity
        for wt, gp, kl in zip(wait_times, goodputs, AlarmC8_kls):
            if not math.isnan(kl):
                ax3.annotate(f"wt={wt}", (gp, kl), textcoords="offset points", xytext=(0, 10), ha='center', fontsize=12)

        fig3.tight_layout()
        fig3.savefig(os.path.join(out_dir, f"{base_name}_plot3_tradeoff.png"))
        plt.close(fig3)

        print(f"    ✓ Saved 3 plots in {out_dir}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate plots for Scenario evaluation data.")
    parser.add_argument("input_dir", type=str, help="Path to the directory containing JSON pairs")
    args = parser.parse_args()

    process_directory(args.input_dir)