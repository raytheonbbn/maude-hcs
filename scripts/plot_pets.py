import math
import os
import re
import json
import argparse
import matplotlib.pyplot as plt

# Global query names definition strictly following the specified mapping
QUERY_NAMES = [
    "latency", "goodput", "FilesC2", "FilesC8", "FilesMA1",
    "OpDurC2", "OpDurC8", "OpDurMA1", "AlarmC2", "AlarmC8", "AlarmMA1"
]

def units(s: str):
    if s == "goodput":
        return "bytes/sec"
    if s.startswith("OpDur"):
        return "sec"
    return ""



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

# def bernoulli_kl(q, p):
#     if not (0 < p < 1 and 0 < q < 1):
#         raise ValueError(f"p and q must be in (0,1). Got p={p}, q={q}")
#     return (
#             q * math.log(q / p) +
#             (1 - q) * math.log((1 - q) / (1 - p))
#     )
#
# def certified_kl_lower_bound(tpr_mean, tpr_radius, fpr_mean, fpr_radius):
#     # Note: Removed the `raise ValueError` for means <= 0 because some metrics
#     # (like AlarmC8) inherently have 0.0 mean in the provided JSON data.
#     # The clipping below safely handles 0.0 inputs without math domain errors.
#
#     # Lower/upper CI endpoints
#     q_low = tpr_mean - tpr_radius
#     p_high = fpr_mean + fpr_radius
#
#     # Clip to valid Bernoulli range
#     q_low = max(min(q_low, 1 - 1e-12), 1e-12)
#     p_high = max(min(p_high, 1 - 1e-12), 1e-12)
#
#     return bernoulli_kl(q_low, p_high)




def extract_data_for_query(json_data, target_n, query_name):
    """
    Extracts sorted 'k' values, means, and radii for a given query and n.
    """
    query_idx = QUERY_NAMES.index(query_name)
    k_vals = []
    means = []
    radii = []

    for key, val in json_data.items():
        if val.get('n') == target_n:
            k_vals.append(val['k'])
            q_data = val['scheck']['queries'][query_idx]
            means.append(q_data['mean'])
            radii.append(q_data['radius'])

    # Sort the lists based on k to ensure lines plot correctly
    sorted_indices = sorted(range(len(k_vals)), key=lambda i: k_vals[i])
    k_vals = [k_vals[i] for i in sorted_indices]
    means = [means[i] for i in sorted_indices]
    radii = [radii[i] for i in sorted_indices]

    return k_vals, means, radii


def main():
    parser = argparse.ArgumentParser(description="Process scenario JSONs and generate plots.")
    parser.add_argument("input_dir", type=str, help="Input directory containing JSON files")
    parser.add_argument("N", type=int, choices=[3, 4, 5], help="Integer index N (3, 4, or 5)")
    args = parser.parse_args()

    input_dir = args.input_dir
    N = args.N

    # Ensure output directory exists
    output_dir = os.path.join(input_dir, "plots")
    os.makedirs(output_dir, exist_ok=True)

    # Set matplotlib parameters for large, readable fonts and tight layouts
    plt.rcParams.update({
        'font.size': 20,
        'axes.titlesize': 22,
        'axes.labelsize': 20,
        'legend.fontsize': 18,
        'figure.autolayout': True  # Equivalent to tight_layout
    })

    # Group files by scenario ID
    scenarios = {}
    for filename in os.listdir(input_dir):
        if not filename.endswith(".json"):
            continue

        # Extract the scenario integer ID
        match = re.search(r'cp2_scenario_(\d+)_ma1_baseline', filename)
        if match:
            scen_id = int(match.group(1))
            if scen_id not in scenarios:
                scenarios[scen_id] = {}

            filepath = os.path.join(input_dir, filename)
            if "_tgenonly" in filename:
                scenarios[scen_id]['ordinary'] = filepath
            else:
                scenarios[scen_id]['hcs'] = filepath

    if not scenarios:
        print(f"No valid scenario files found in {input_dir}.")
        return

    set1_queries = ["goodput", "OpDurC2", "OpDurC8", "OpDurMA1", "AlarmC2", "AlarmC8", "AlarmMA1"]
    set2_queries = ["AlarmC2", "AlarmC8", "AlarmMA1"]

    # Pre-load all data to avoid reading files multiple times
    scenario_data = {}
    for scen_id, files in scenarios.items():
        scenario_data[scen_id] = {}
        if files.get('hcs'):
            with open(files['hcs'], 'r') as f:
                scenario_data[scen_id]['hcs'] = json.load(f)
        if files.get('ordinary'):
            with open(files['ordinary'], 'r') as f:
                scenario_data[scen_id]['ordinary'] = json.load(f)

    # ==========================================
    # Plot Set 1: HCS metrics vs k (All scenarios per query)
    # ==========================================
    for q_name in set1_queries:
        plt.figure(figsize=(10, 6))
        plotted = False

        for scen_id in sorted(scenarios.keys()):
            hcs_data = scenario_data[scen_id].get('hcs')
            if not hcs_data:
                continue

            k_vals, means, radii = extract_data_for_query(hcs_data, N, q_name)
            if not k_vals:
                continue

            plt.errorbar(k_vals, means, yerr=radii, marker='o',
                         capsize=5, label=f"Scenario {scen_id}", linewidth=2)
            plotted = True

        if plotted:
            plt.title(f"{q_name} {units(q_name)}")
            plt.xlabel("k parameter")
            plt.ylabel(f"Mean {q_name}")
            plt.grid(True, linestyle='--', alpha=0.7)
            plt.legend()

            out_filename = os.path.join(output_dir, f"set1_{q_name}.png")
            plt.savefig(out_filename)
        plt.close()

    # # ==========================================
    # # Plot Set 2: Certified KL Lower Bound vs k (All scenarios per query)
    # # ==========================================
    # for q_name in set2_queries:
    #     plt.figure(figsize=(10, 6))
    #     plotted = False
    #
    #     for scen_id in sorted(scenarios.keys()):
    #         hcs_data = scenario_data[scen_id].get('hcs')
    #         ord_data = scenario_data[scen_id].get('ordinary')
    #         if not hcs_data or not ord_data:
    #             continue
    #
    #         k_tpr, mean_tpr, rad_tpr = extract_data_for_query(hcs_data, N, q_name)
    #         k_fpr, mean_fpr, rad_fpr = extract_data_for_query(ord_data, N, q_name)
    #
    #         tpr_dict = {k: (m, r) for k, m, r in zip(k_tpr, mean_tpr, rad_tpr)}
    #         fpr_dict = {k: (m, r) for k, m, r in zip(k_fpr, mean_fpr, rad_fpr)}
    #
    #         kl_k_vals = []
    #         kl_bounds = []
    #
    #         # Only compute for 'k' values present in both datasets
    #         common_ks = sorted(set(k_tpr) & set(k_fpr))
    #         for k in common_ks:
    #             t_m, t_r = tpr_dict[k]
    #             f_m, f_r = fpr_dict[k]
    #
    #             kl_val = certified_kl_lower_bound(t_m, t_r, f_m, f_r)
    #             if check_intervals_overlap(t_m, t_r, f_m, f_r):
    #                 print(f'{scen_id}:{q_name}:k={k} overlap  {t_m} +/- {t_r} <-> {f_m} +/- {f_r} ==> {kl_val}')
    #             else:
    #                 print(f'{scen_id}:{q_name}:k={k} -------  {t_m} +/- {t_r} <-> {f_m} +/- {f_r} ==> {kl_val}')
    #             kl_k_vals.append(k)
    #             kl_bounds.append(kl_val)
    #         print(f'{scen_id} {q_name}  {kl_k_vals}')
    #         print(f'{scen_id} {q_name}  {kl_bounds}')
    #         if kl_k_vals:
    #             plt.plot(kl_k_vals, kl_bounds, marker='s',
    #                      label=f"Scenario {scen_id}", linewidth=2, markersize=8)
    #             plotted = True
    #
    #     if plotted:
    #         plt.title(f"Certified KL Lower Bound: {q_name}")
    #         plt.xlabel("k parameter (threshold)")
    #         plt.ylabel("Certified KL Lower Bound")
    #         plt.grid(True, linestyle='--', alpha=0.7)
    #         plt.legend()
    #
    #         out_filename = os.path.join(output_dir, f"set2_{q_name}_kl.png")
    #         plt.savefig(out_filename)
    #     plt.close()
        # ==========================================
        # Plot Set 2: Certified KL Lower Bound vs k (All scenarios per query)
        # ==========================================
        for q_name in set2_queries:
            all_plot_data = []
            has_inf = False
            max_finite = -float('inf')

            for scen_id in sorted(scenarios.keys()):
                hcs_data = scenario_data[scen_id].get('hcs')
                ord_data = scenario_data[scen_id].get('ordinary')
                if not hcs_data or not ord_data:
                    continue

                k_tpr, mean_tpr, rad_tpr = extract_data_for_query(hcs_data, N, q_name)
                k_fpr, mean_fpr, rad_fpr = extract_data_for_query(ord_data, N, q_name)

                tpr_dict = {k: (m, r) for k, m, r in zip(k_tpr, mean_tpr, rad_tpr)}
                fpr_dict = {k: (m, r) for k, m, r in zip(k_fpr, mean_fpr, rad_fpr)}

                kl_k_vals = []
                kl_bounds = []

                common_ks = sorted(set(k_tpr) & set(k_fpr))
                for k in common_ks:
                    t_m, t_r = tpr_dict[k]
                    f_m, f_r = fpr_dict[k]

                    kl_val = certified_kl_lower_bound(t_m, t_r, f_m, f_r)
                    kl_k_vals.append(k)
                    kl_bounds.append(kl_val)

                if kl_k_vals:
                    all_plot_data.append((scen_id, kl_k_vals, kl_bounds))
                    # Track max finite value and infinity presence
                    for v in kl_bounds:
                        if math.isinf(v):
                            has_inf = True
                        elif v > max_finite:
                            max_finite = v

            if not all_plot_data:
                continue

            if has_inf:
                # --- SPLIT AXIS PLOT (BROKEN AXIS) ---
                if max_finite == -float('inf'):
                    max_finite = 10.0  # Fallback if all values are inf

                # Determine appropriate gaps and proxy values for the infinity plotting
                gap = max(1.0, max_finite * 0.15)
                inf_val = max_finite + gap * 3

                fig, (ax1, ax2) = plt.subplots(2, 1, sharex=True, figsize=(10, 6),
                                               gridspec_kw={'height_ratios': [1, 4], 'hspace': 0.08})

                for scen_id, kl_k_vals, kl_bounds in all_plot_data:
                    # Replace inf with the synthetic inf_val for plotting purposes
                    plot_bounds = [inf_val if math.isinf(v) else v for v in kl_bounds]

                    # Plot the exact same line on both axes. Matplotlib clips what falls outside bounds.
                    ax1.plot(kl_k_vals, plot_bounds, marker='s', label=f"Scenario {scen_id}", linewidth=2, markersize=8)
                    ax2.plot(kl_k_vals, plot_bounds, marker='s', label=f"Scenario {scen_id}", linewidth=2, markersize=8)

                # Limit ranges to create the break
                ax1.set_ylim(inf_val - gap, inf_val + gap)
                ax2.set_ylim(0, max_finite + gap)

                # Hide spines to make it look broken
                ax1.spines['bottom'].set_visible(False)
                ax2.spines['top'].set_visible(False)
                ax1.xaxis.tick_top()
                ax1.tick_params(labeltop=False)  # Don't place actual ticks on the top spine
                ax2.xaxis.tick_bottom()

                # Create diagonal cut marks across the broken axis
                d = .015
                kwargs = dict(transform=ax1.transAxes, color='k', clip_on=False)
                ax1.plot((-d, +d), (-d * 4, +d * 4), **kwargs)  # Top-left diagonal
                ax1.plot((1 - d, 1 + d), (-d * 4, +d * 4), **kwargs)  # Top-right diagonal
                kwargs.update(transform=ax2.transAxes)
                ax2.plot((-d, +d), (1 - d, 1 + d), **kwargs)  # Bottom-left diagonal
                ax2.plot((1 - d, 1 + d), (1 - d, 1 + d), **kwargs)  # Bottom-right diagonal

                # Set Infinity tick label on top axis
                ax1.set_yticks([inf_val])
                ax1.set_yticklabels([r'$\infty$'])

                ax1.grid(True, linestyle='--', alpha=0.7)
                ax2.grid(True, linestyle='--', alpha=0.7)

                ax2.set_xlabel("k parameter")
                fig.supylabel("Certified KL Lower Bound", fontsize=16)
                ax1.set_title(f"Certified KL Lower Bound: {q_name}")
                ax2.legend()

                out_filename = os.path.join(output_dir, f"set2_{q_name}_kl.png")
                plt.savefig(out_filename, bbox_inches='tight')
                plt.close(fig)

            else:
                # --- STANDARD PLOT (NO INFINITIES) ---
                plt.figure(figsize=(10, 6))
                for scen_id, kl_k_vals, kl_bounds in all_plot_data:
                    plt.plot(kl_k_vals, kl_bounds, marker='s', label=f"Scenario {scen_id}", linewidth=2, markersize=8)

                plt.title(f"Certified KL Lower Bound: {q_name}")
                plt.xlabel("k parameter")
                plt.ylabel("Certified KL Lower Bound")
                plt.grid(True, linestyle='--', alpha=0.7)
                plt.legend()

                out_filename = os.path.join(output_dir, f"set2_{q_name}_kl.png")
                plt.savefig(out_filename)
                plt.close()

    print(f"\nDone! All plots have been saved to the '{output_dir}' directory.")


if __name__ == "__main__":
    main()