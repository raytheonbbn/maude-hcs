#!/usr/bin/env python3
"""
Compare Isolated Channel Testbed CUSUM Results vs Maude SMC Results.

This script:
1. Loads testbed baseline ECDFs and empirical k values for isolated protocol runs.
2. Parses testbed feature time series and computes cumulative KS+CUSUM scores S_t
   at cumulative time windows 900s (bin 90), 1800s (bin 180), 2700s (bin 270), and 3600s (bin 360).
3. Loads Maude SMC simulation cumulative CUSUM results from scenario2_isolated_plus_tgen.
4. Generates side-by-side comparison bar plots (Testbed vs SMC) across time windows for
   Skyhook, WebTunnel, and OBFS4.
5. Marks detection thresholds h with red dashed lines and displays empirical k values in the legends.
6. Saves generated comparison figures and summary CSV.
"""

import os
import re
import csv
import json
import argparse
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from scipy.stats import ks_1samp

# -----------------------------------------------------------------------------
# Configuration & Metadata
# -----------------------------------------------------------------------------
FEATURE_THRESHOLDS = {
    "dns_query_rate": 2.5,
    "dns_query_size_mean": 2.5,
    "dns_response_size_mean": 2.5,
    "tcp_upload_rate": 3.5,
    "tcp_download_rate": 3.5,
    "tcp_upload_download_ratio": 5.0,
    "tcp_outgoing_packet_rate": 3.5,
    "tcp_incoming_packet_rate": 3.5,
    "tcp_packet_upload_download_ratio": 5.0,
    "packet_size_std_dev": 4.0,
    "packet_size_mean": 3.0,
    "packet_interarrival_mean": 3.0,
    "direction_change_count": 4.0,
    "active_flow_count": 2.5,
    "tcp_new_conn_count": 3.5,
}

FEATURE_TITLES = {
    "dns_query_rate": "DNS Query Rate",
    "dns_query_size_mean": "Mean DNS Query Size",
    "dns_response_size_mean": "Mean DNS Response Size",
    "tcp_upload_rate": "TCP Upload Rate",
    "tcp_download_rate": "TCP Download Rate",
    "tcp_upload_download_ratio": "TCP Upload/Download Ratio",
    "tcp_outgoing_packet_rate": "TCP Outgoing Packet Rate",
    "tcp_incoming_packet_rate": "TCP Incoming Packet Rate",
    "tcp_packet_upload_download_ratio": "TCP Packet Upload/Download Ratio",
    "packet_size_std_dev": "Packet Size Std Dev",
    "packet_size_mean": "Mean Packet Size",
    "packet_interarrival_mean": "Mean Packet Inter-arrival",
    "direction_change_count": "Direction Change Count",
    "active_flow_count": "Active Flow Count",
    "tcp_new_conn_count": "TCP New Connection Count",
}

PROTOCOL_DISPLAY_NAMES = {
    "only_obfs": "OBFS4",
    "only_skyhook": "Skyhook",
    "only_webtunnel": "WebTunnel",
}

PROTOCOL_COLORS = {
    "only_obfs": "#E69F00",       # Orange
    "only_skyhook": "#D55E00",    # Red-Orange / Vermillion
    "only_webtunnel": "#009E73",  # Bluish Green
}

TESTBED_RUN_DIRS = {
    "only_obfs": ("pwnd_cp3_only_obfs", "pwnd_cp3_only_obfs_20260822_232248"),
    "only_skyhook": ("pwnd_cp3_only_skyhook", "pwnd_cp3_only_skyhook_20260825_153253"),
    "only_webtunnel": ("pwnd_cp3_only_webtunnel", "pwnd_cp3_only_webtunnel_20260823_061642"),
}

CUM_WINDOWS = [
    {"seconds": 900, "label": "900s\n[10-910]s", "bin": 90, "smc_window": "[10-910]s"},
    {"seconds": 1800, "label": "1800s\n[10-1810]s", "bin": 180, "smc_window": "[10-1810]s"},
    {"seconds": 2700, "label": "2700s\n[10-2710]s", "bin": 270, "smc_window": "[10-2710]s"},
    {"seconds": 3600, "label": "3600s\n[10-3610]s", "bin": 360, "smc_window": "[10-3610]s"},
]

# -----------------------------------------------------------------------------
# Testbed CUSUM Computation
# -----------------------------------------------------------------------------
def load_csv_by_bin(csv_path: Path) -> Dict[int, List[float]]:
    """Parse a feature CSV and return {bin_id: [values]}."""
    by_bin = defaultdict(list)
    with open(csv_path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        bin_cols = {}
        for i, col in enumerate(header):
            try:
                bin_cols[i] = int(col)
            except ValueError:
                pass
        for row in reader:
            for col_idx, bin_id in bin_cols.items():
                if col_idx < len(row) and row[col_idx] != "":
                    try:
                        by_bin[bin_id].append(float(row[col_idx]))
                    except ValueError:
                        pass
    return dict(by_bin)


def compute_testbed_cusum(testbed_data_dir: Path, window_size: int = 6) -> Dict[str, Dict[str, Any]]:
    """
    Compute cumulative CUSUM S_t at bins 90, 180, 270, 360 for all protocols and features at ixp-router_eth0.
    """
    results = {}
    target_bins = {w["bin"]: w["seconds"] for w in CUM_WINDOWS}

    for proto_key, (proto_base, proto_run) in TESTBED_RUN_DIRS.items():
        results[proto_key] = {}
        base_dir = testbed_data_dir / "baselines" / proto_base / "ixp-router_eth0"
        
        run_dir = testbed_data_dir / proto_run
        vantage_dirs = list(run_dir.glob("*ixp-router_eth0"))
        if not vantage_dirs:
            continue
        features_dir = vantage_dirs[0] / "features"
        if not features_dir.exists():
            continue

        for feat_name, threshold in FEATURE_THRESHOLDS.items():
            base_json_path = base_dir / f"{feat_name}.json"
            if not base_json_path.exists():
                continue

            with open(base_json_path) as f:
                base_info = json.load(f)

            k_val = base_info.get("k")
            if k_val is None:
                continue

            ecdf_sorted = np.sort(np.array(base_info.get("ecdf_values", [])))
            n_base = len(ecdf_sorted)
            if n_base == 0:
                continue

            csv_candidates = list(features_dir.glob(f"{feat_name}_bin*.csv"))
            if not csv_candidates:
                continue

            by_bin = load_csv_by_bin(csv_candidates[0])
            if not by_bin:
                continue

            def cdf_fn(x, ecdf=ecdf_sorted, n=n_base):
                return np.searchsorted(ecdf, x, side="right") / n

            min_bin = min(by_bin.keys())
            max_bin = max(by_bin.keys())

            cusum = 0.0
            window_cusum = {}

            for t in range(min_bin, max_bin + 1):
                window_values = []
                for b in range(t - window_size + 1, t + 1):
                    window_values.extend(by_bin.get(b, []))

                d_t = ks_1samp(window_values, cdf_fn).statistic if window_values else 0.0
                z_t = d_t - k_val
                cusum = max(0.0, cusum + z_t)

                if t in target_bins:
                    sec = target_bins[t]
                    window_cusum[sec] = float(cusum)

            results[proto_key][feat_name] = {
                "k": float(k_val),
                "threshold": float(threshold),
                "cusum_scores": window_cusum,
                "final_cusum": float(cusum),
            }

    return results


# -----------------------------------------------------------------------------
# Maude SMC Result Loading
# -----------------------------------------------------------------------------
def load_smc_cusum_results(repo_root: Path) -> Dict[str, Dict[str, Any]]:
    """
    Parse SMC cumulative CUSUM results and baseline K values.
    """
    import sys
    sys.path.insert(0, str(repo_root / "scripts"))
    from parse_and_plot_cp3_results import parse_quatex_file, parse_json_result

    sc2_dir = repo_root / "use-cases/challenge-problem-3/cp3_scenarios/scenario2_isolated_plus_tgen"
    results = {}

    for proto in ["only_obfs", "only_skyhook", "only_webtunnel"]:
        results[proto] = {}
        qpath = sc2_dir / f"{proto}-quatex.maude"
        jpath = sc2_dir / "results" / proto / f"{proto}.json"
        bfile = sc2_dir / f"{proto}-baseline-eq-combo1.maude"

        # Baseline K values from baseline maude file
        k_values = {}
        if bfile.exists():
            text = bfile.read_text()
            matches = re.findall(r"bl\s*\(\s*(\w+)\s*,\s*(\w+)\s*,\s*([0-9\.\-eE]+)", text)
            maude_feat_map = {
                "dnsQueryRate": "dns_query_rate",
                "tcpOutPktRate": "tcp_outgoing_packet_rate",
                "tcpInPktRate": "tcp_incoming_packet_rate",
                "tcpPktSize": "packet_size_mean",
                "tcpPktInterarrival": "packet_interarrival_mean",
            }
            for vp, feat, k in matches:
                if vp == "ixpN" and feat in maude_feat_map:
                    k_values[maude_feat_map[feat]] = float(k)

        if not qpath.exists() or not jpath.exists():
            continue

        meta = parse_quatex_file(qpath)
        jdata = parse_json_result(jpath, meta)

        for q in jdata["queries"]:
            if q.get("is_cusum") and q.get("scope") == "cumulative" and q.get("target") in ["ixpN", "system"]:
                metric = q.get("metric")
                win = q.get("window_label")
                if metric not in results[proto]:
                    results[proto][metric] = {
                        "k": k_values.get(metric, 0.0),
                        "scores": {},
                        "radii": {}
                    }
                results[proto][metric]["scores"][win] = float(q.get("mean", 0.0))
                results[proto][metric]["radii"][win] = float(q.get("radius", 0.0))

    return results


# -----------------------------------------------------------------------------
# Plotting Helpers & Styling
# -----------------------------------------------------------------------------
def set_plot_style():
    """Configure publication matplotlib aesthetic settings."""
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.size": 10.5,
        "axes.titlesize": 11.5,
        "axes.titleweight": "bold",
        "axes.labelsize": 10.5,
        "axes.labelweight": "semibold",
        "xtick.labelsize": 9.5,
        "ytick.labelsize": 9.5,
        "legend.fontsize": 8.5,
        "figure.titlesize": 14,
        "figure.titleweight": "bold",
        "grid.alpha": 0.35,
        "grid.linestyle": "--",
        "axes.edgecolor": "#cccccc",
        "axes.linewidth": 0.8,
    })


# -----------------------------------------------------------------------------
# Main Plot: 2x3 Grid (Core 5 Features + Summary Panel)
# -----------------------------------------------------------------------------
def plot_testbed_vs_smc_superplot(testbed_res: Dict[str, Dict[str, Any]],
                                  smc_res: Dict[str, Dict[str, Any]],
                                  out_dir: Path):
    """
    Generate 2x3 Multi-panel figure comparing Testbed vs SMC cumulative CUSUM scores
    across time windows (900s, 1800s, 2700s, 3600s) for core shared traffic features.
    """
    core_features = [
        "dns_query_rate",
        "tcp_outgoing_packet_rate",
        "tcp_incoming_packet_rate",
        "packet_size_mean",
        "packet_interarrival_mean",
    ]

    protocols = ["only_obfs", "only_skyhook", "only_webtunnel"]
    n_protos = len(protocols)
    x = np.arange(len(CUM_WINDOWS))
    group_spacing = 0.85 / max(n_protos, 1)
    bar_w = group_spacing * 0.42

    fig, axes = plt.subplots(2, 3, figsize=(16.5, 10))
    axes_flat = axes.flatten()

    for idx, feat in enumerate(core_features):
        ax = axes_flat[idx]
        threshold = FEATURE_THRESHOLDS.get(feat, 3.0)
        max_val_in_panel = threshold

        legend_handles = []

        for i, proto in enumerate(protocols):
            p_display = PROTOCOL_DISPLAY_NAMES.get(proto, proto)
            color = PROTOCOL_COLORS.get(proto, plt.cm.tab10(i))
            proto_center = (i - (n_protos - 1) / 2) * group_spacing

            # Testbed values
            tb_feat_data = testbed_res.get(proto, {}).get(feat, {})
            tb_k = tb_feat_data.get("k", 0.0)
            tb_scores = [tb_feat_data.get("cusum_scores", {}).get(w["seconds"], 0.0) for w in CUM_WINDOWS]

            # SMC values
            smc_feat_data = smc_res.get(proto, {}).get(feat, {})
            smc_k = smc_feat_data.get("k", 0.0)
            smc_scores = [smc_feat_data.get("scores", {}).get(w["smc_window"], 0.0) for w in CUM_WINDOWS]
            smc_radii = [smc_feat_data.get("radii", {}).get(w["smc_window"], 0.0) for w in CUM_WINDOWS]

            max_val_in_panel = max(max_val_in_panel, max(tb_scores + smc_scores))

            # Bar 1: Testbed (solid)
            rects1 = ax.bar(x + proto_center - bar_w / 2, tb_scores, bar_w,
                            color=color, alpha=0.9, edgecolor="#222222", linewidth=0.6)

            # Bar 2: SMC (hatched)
            rects2 = ax.bar(x + proto_center + bar_w / 2, smc_scores, bar_w, yerr=smc_radii, capsize=2,
                            color=color, alpha=0.55, hatch="//", edgecolor="#222222", linewidth=0.6)

            # Text annotations on bars
            for rect in rects1:
                h = rect.get_height()
                if h > 0.01:
                    ax.annotate(f"{h:.1f}", xy=(rect.get_x() + rect.get_width() / 2, h),
                                xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=7)
            for rect in rects2:
                h = rect.get_height()
                if h > 0.01:
                    ax.annotate(f"{h:.1f}", xy=(rect.get_x() + rect.get_width() / 2, h),
                                xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=7)

            # Legend handles with k values
            h_tb = Patch(facecolor=color, edgecolor="#222222",
                         label=f"{p_display} Testbed (k={tb_k:.3f})")
            h_smc = Patch(facecolor=color, alpha=0.55, hatch="//", edgecolor="#222222",
                          label=f"{p_display} SMC (k={smc_k:.3f})")
            legend_handles.extend([h_tb, h_smc])

        # Red dashed line for threshold h
        thresh_line = ax.axhline(y=threshold, color="#d9534f", linestyle="--", linewidth=1.5,
                                 label=f"Threshold h = {threshold:.1f}")
        legend_handles.append(thresh_line)

        title = FEATURE_TITLES.get(feat, feat)
        ax.set_title(f"{title} (h = {threshold:.1f})", fontsize=11.5, fontweight="bold")
        ax.set_xlabel("Time Window (s)", fontsize=10)
        ax.set_ylabel("CUSUM Score $S_t$", fontsize=10)
        ax.set_xticks(x)
        ax.set_xticklabels([w["label"] for w in CUM_WINDOWS], fontsize=9)
        ax.set_ylim(0, max_val_in_panel * 1.22 + 0.5)
        ax.grid(True, axis="y")

        ax.legend(handles=legend_handles, loc="upper left", frameon=True,
                  facecolor="#fdfdfd", edgecolor="#cccccc", fontsize=7.2, ncol=2)

    # Panel 6: Final Window Summary at 3600s across all 5 features
    ax6 = axes_flat[5]
    fx = np.arange(len(core_features))
    short_feat_labels = ["DNS Rate", "TCP Out", "TCP In", "Pkt Size", "Inter-arr"]
    f_group_spacing = 0.85 / max(n_protos, 1)
    f_bar_w = f_group_spacing * 0.42

    summary_legend = []

    for i, proto in enumerate(protocols):
        p_display = PROTOCOL_DISPLAY_NAMES.get(proto, proto)
        color = PROTOCOL_COLORS.get(proto, plt.cm.tab10(i))
        p_center = (i - (n_protos - 1) / 2) * f_group_spacing

        tb_3600_scores = []
        smc_3600_scores = []
        smc_3600_radii = []

        for feat in core_features:
            tb_feat_data = testbed_res.get(proto, {}).get(feat, {})
            tb_3600_scores.append(tb_feat_data.get("cusum_scores", {}).get(3600, 0.0))

            smc_feat_data = smc_res.get(proto, {}).get(feat, {})
            smc_3600_scores.append(smc_feat_data.get("scores", {}).get("[10-3610]s", 0.0))
            smc_3600_radii.append(smc_feat_data.get("radii", {}).get("[10-3610]s", 0.0))

        # Testbed bar
        rects1 = ax6.bar(fx + p_center - f_bar_w / 2, tb_3600_scores, f_bar_w,
                         color=color, alpha=0.9, edgecolor="#222222", linewidth=0.6)
        # SMC bar
        rects2 = ax6.bar(fx + p_center + f_bar_w / 2, smc_3600_scores, f_bar_w, yerr=smc_3600_radii, capsize=2,
                         color=color, alpha=0.55, hatch="//", edgecolor="#222222", linewidth=0.6)

        h_tb = Patch(facecolor=color, edgecolor="#222222", label=f"{p_display} Testbed")
        h_smc = Patch(facecolor=color, alpha=0.55, hatch="//", edgecolor="#222222", label=f"{p_display} SMC")
        summary_legend.extend([h_tb, h_smc])

    ax6.set_title("Overview: All Core Features at 3600s", fontsize=11.5, fontweight="bold")
    ax6.set_xlabel("Traffic Feature", fontsize=10)
    ax6.set_ylabel("CUSUM Score $S_t$", fontsize=10)
    ax6.set_xticks(fx)
    ax6.set_xticklabels(short_feat_labels, rotation=15, ha="right", fontsize=9)
    ax6.grid(True, axis="y")
    ax6.legend(handles=summary_legend, loc="upper right", frameon=True,
               facecolor="#fdfdfd", edgecolor="#cccccc", fontsize=7.5, ncol=2)

    fig.suptitle("Comparison of Cumulative CUSUM Scores: Testbed Isolated Channel vs Maude SMC",
                 fontsize=14.5, weight="bold", y=0.985)
    plt.tight_layout(rect=[0, 0.02, 1, 0.96])

    out_file = out_dir / "testbed_vs_smc_cusum_comparison.png"
    fig.savefig(out_file, dpi=300)
    plt.close(fig)
    print(f"✓ Saved core superplot comparison to {out_file}")


def plot_single_protocol_cusum_comparison(testbed_res: Dict[str, Dict[str, Any]],
                                          smc_res: Dict[str, Dict[str, Any]],
                                          proto: str,
                                          out_dir: Path):
    """
    Generate dedicated 2x3 figure for a specific protocol comparing Testbed vs SMC
    cumulative CUSUM scores across time windows for each of the core 5 features.
    """
    core_features = [
        "dns_query_rate",
        "tcp_outgoing_packet_rate",
        "tcp_incoming_packet_rate",
        "packet_size_mean",
        "packet_interarrival_mean",
    ]
    p_display = PROTOCOL_DISPLAY_NAMES.get(proto, proto)
    color = PROTOCOL_COLORS.get(proto, "#3498db")

    fig, axes = plt.subplots(2, 3, figsize=(16, 9.5))
    axes_flat = axes.flatten()
    x = np.arange(len(CUM_WINDOWS))
    bar_w = 0.35

    for idx, feat in enumerate(core_features):
        ax = axes_flat[idx]
        tb_feat = testbed_res.get(proto, {}).get(feat, {})
        smc_feat = smc_res.get(proto, {}).get(feat, {})

        tb_k = tb_feat.get("k", np.nan)
        smc_k = smc_feat.get("k", np.nan)
        threshold = FEATURE_THRESHOLDS.get(feat, np.nan)

        tb_scores = [tb_feat.get("cusum_scores", {}).get(w["seconds"], 0.0) for w in CUM_WINDOWS]
        smc_scores = [smc_feat.get("scores", {}).get(w["smc_window"], 0.0) for w in CUM_WINDOWS]
        smc_radii = [smc_feat.get("radii", {}).get(w["smc_window"], 0.0) for w in CUM_WINDOWS]

        # Plot threshold line
        if not np.isnan(threshold):
            ax.axhline(threshold, color="#d9534f", linestyle="--", linewidth=1.5,
                       label=f"Threshold h={threshold:.1f}", zorder=1)

        # Testbed bars
        tb_label = f"Testbed (k={tb_k:.3f})" if not np.isnan(tb_k) else "Testbed"
        rects_tb = ax.bar(x - bar_w/2, tb_scores, bar_w, color=color, alpha=0.9,
                          edgecolor="#222222", linewidth=0.8, label=tb_label, zorder=2)

        # SMC bars
        smc_label = f"Maude SMC (k={smc_k:.3f})" if not np.isnan(smc_k) else "Maude SMC"
        rects_smc = ax.bar(x + bar_w/2, smc_scores, bar_w, yerr=smc_radii, capsize=3,
                           color=color, alpha=0.55, hatch="//", edgecolor="#222222",
                           linewidth=0.8, label=smc_label, zorder=2)

        # Value annotations above error bars
        for r in rects_tb:
            h = r.get_height()
            if h > 0.01:
                ax.annotate(f"{h:.2f}", xy=(r.get_x() + r.get_width()/2, h),
                            xytext=(0, 4), textcoords="offset points",
                            ha="center", va="bottom", fontsize=8.5, fontweight="bold")

        for r, rad in zip(rects_smc, smc_radii):
            h = r.get_height()
            if h > 0.01:
                top_y = h + rad
                ax.annotate(f"{h:.2f}", xy=(r.get_x() + r.get_width()/2, top_y),
                            xytext=(0, 4), textcoords="offset points",
                            ha="center", va="bottom", fontsize=8.5, fontweight="bold")

        feat_title = FEATURE_TITLES.get(feat, feat)
        thresh_str = f" (h = {threshold:.1f})" if not np.isnan(threshold) else ""
        ax.set_title(f"{feat_title}{thresh_str}", fontsize=11.5, fontweight="bold")
        ax.set_xlabel("Time Window", fontsize=10)
        ax.set_ylabel("CUSUM Score $S_t$", fontsize=10)
        ax.set_xticks(x)
        ax.set_xticklabels([w["label"] for w in CUM_WINDOWS], fontsize=9)
        ax.grid(True, axis="y")

        max_val = max(
            max(tb_scores + [0.0]),
            max([s + r for s, r in zip(smc_scores, smc_radii)] + [0.0]),
            threshold if not np.isnan(threshold) else 0.0
        )
        ax.set_ylim(0, max(max_val * 1.25, 4.0))
        ax.legend(loc="upper left", frameon=True, facecolor="#fdfdfd", edgecolor="#cccccc", fontsize=8.5)

    # Panel 6 (Summary at 3600s)
    ax6 = axes_flat[5]
    fx = np.arange(len(core_features))
    short_feat_labels = ["DNS Rate", "TCP Out", "TCP In", "Pkt Size", "Inter-arr"]

    tb_3600 = [testbed_res.get(proto, {}).get(f, {}).get("cusum_scores", {}).get(3600, 0.0) for f in core_features]
    smc_3600 = [smc_res.get(proto, {}).get(f, {}).get("scores", {}).get("[10-3610]s", 0.0) for f in core_features]
    smc_rad_3600 = [smc_res.get(proto, {}).get(f, {}).get("radii", {}).get("[10-3610]s", 0.0) for f in core_features]

    r1 = ax6.bar(fx - bar_w/2, tb_3600, bar_w, color=color, alpha=0.9,
                 edgecolor="#222222", linewidth=0.8, label="Testbed (3600s)")
    r2 = ax6.bar(fx + bar_w/2, smc_3600, bar_w, yerr=smc_rad_3600, capsize=3,
                 color=color, alpha=0.55, hatch="//", edgecolor="#222222",
                 linewidth=0.8, label="Maude SMC ([10-3610]s)")

    for r in r1:
        h = r.get_height()
        if h > 0.01:
            ax6.annotate(f"{h:.2f}", xy=(r.get_x() + r.get_width()/2, h),
                         xytext=(0, 4), textcoords="offset points",
                         ha="center", va="bottom", fontsize=8.5, fontweight="bold")

    for r, rad in zip(r2, smc_rad_3600):
        h = r.get_height()
        if h > 0.01:
            top_y = h + rad
            ax6.annotate(f"{h:.2f}", xy=(r.get_x() + r.get_width()/2, top_y),
                         xytext=(0, 4), textcoords="offset points",
                         ha="center", va="bottom", fontsize=8.5, fontweight="bold")

    ax6.set_title("All Core Features at 3600s", fontsize=11.5, fontweight="bold")
    ax6.set_xlabel("Traffic Feature", fontsize=10)
    ax6.set_ylabel("CUSUM Score $S_t$", fontsize=10)
    ax6.set_xticks(fx)
    ax6.set_xticklabels(short_feat_labels, rotation=15, ha="right", fontsize=9)
    ax6.grid(True, axis="y")
    ax6.legend(loc="upper right", frameon=True, facecolor="#fdfdfd", edgecolor="#cccccc", fontsize=8.5)

    fig.suptitle(f"{p_display} - Cumulative CUSUM Z(t) / S_t Scores vs Time Window (Testbed vs SMC)",
                 fontsize=14.5, weight="bold", y=0.985)
    plt.tight_layout(rect=[0, 0.02, 1, 0.96])

    out_file = out_dir / f"cusum_cumulative_features_{proto}_testbed_vs_smc.png"
    fig.savefig(out_file, dpi=300)
    plt.close(fig)
    print(f"✓ Saved {p_display} testbed vs SMC plot to {out_file}")


# -----------------------------------------------------------------------------
# Comprehensive 15-Feature Dashboard
# -----------------------------------------------------------------------------
def plot_testbed_vs_smc_all_15_features(testbed_res: Dict[str, Dict[str, Any]],
                                        smc_res: Dict[str, Dict[str, Any]],
                                        out_dir: Path):
    """
    Generate a 3x5 full dashboard covering all 15 traffic features with threshold markers and k values.
    """
    all_features = list(FEATURE_THRESHOLDS.keys())
    protocols = ["only_obfs", "only_skyhook", "only_webtunnel"]
    n_protos = len(protocols)
    x = np.arange(len(CUM_WINDOWS))
    group_spacing = 0.85 / max(n_protos, 1)
    bar_w = group_spacing * 0.42

    fig, axes = plt.subplots(3, 5, figsize=(22, 13.5))
    axes_flat = axes.flatten()

    for idx, feat in enumerate(all_features):
        ax = axes_flat[idx]
        threshold = FEATURE_THRESHOLDS.get(feat, 3.0)
        max_val = threshold

        legend_handles = []

        for i, proto in enumerate(protocols):
            p_display = PROTOCOL_DISPLAY_NAMES.get(proto, proto)
            color = PROTOCOL_COLORS.get(proto, plt.cm.tab10(i))
            proto_center = (i - (n_protos - 1) / 2) * group_spacing

            # Testbed
            tb_feat_data = testbed_res.get(proto, {}).get(feat, {})
            tb_k = tb_feat_data.get("k", 0.0)
            tb_scores = [tb_feat_data.get("cusum_scores", {}).get(w["seconds"], 0.0) for w in CUM_WINDOWS]

            # SMC (if available)
            smc_feat_data = smc_res.get(proto, {}).get(feat, {})
            has_smc = bool(smc_feat_data)
            smc_k = smc_feat_data.get("k", 0.0)
            smc_scores = [smc_feat_data.get("scores", {}).get(w["smc_window"], 0.0) for w in CUM_WINDOWS] if has_smc else [0.0]*4
            smc_radii = [smc_feat_data.get("radii", {}).get(w["smc_window"], 0.0) for w in CUM_WINDOWS] if has_smc else [0.0]*4

            max_val = max(max_val, max(tb_scores + smc_scores))

            # Testbed Bar
            ax.bar(x + proto_center - bar_w / 2, tb_scores, bar_w,
                   color=color, alpha=0.9, edgecolor="#222222", linewidth=0.5)

            # SMC Bar
            if has_smc:
                ax.bar(x + proto_center + bar_w / 2, smc_scores, bar_w, yerr=smc_radii, capsize=1.5,
                       color=color, alpha=0.55, hatch="//", edgecolor="#222222", linewidth=0.5)

            # Legend
            if tb_feat_data:
                h_tb = Patch(facecolor=color, edgecolor="#222222", label=f"{p_display} TB (k={tb_k:.3f})")
                legend_handles.append(h_tb)
            if has_smc:
                h_smc = Patch(facecolor=color, alpha=0.55, hatch="//", edgecolor="#222222", label=f"{p_display} SMC (k={smc_k:.3f})")
                legend_handles.append(h_smc)

        thresh_line = ax.axhline(y=threshold, color="#d9534f", linestyle="--", linewidth=1.2,
                                 label=f"h = {threshold:.1f}")
        legend_handles.append(thresh_line)

        title = FEATURE_TITLES.get(feat, feat)
        ax.set_title(f"{title}", fontsize=10.5, fontweight="bold")
        ax.set_ylabel("$S_t$", fontsize=9)
        ax.set_xticks(x)
        ax.set_xticklabels([f"{w['seconds']}s" for w in CUM_WINDOWS], fontsize=8.5)
        ax.set_ylim(0, max_val * 1.25 + 0.3)
        ax.grid(True, axis="y")

        ax.legend(handles=legend_handles, loc="upper left", frameon=True,
                  facecolor="#fdfdfd", edgecolor="#cccccc", fontsize=6.2, ncol=2)

    fig.suptitle("Testbed Isolated Channel vs SMC Cumulative CUSUM Comparison (All 15 Features)",
                 fontsize=15, weight="bold", y=0.99)
    plt.tight_layout(rect=[0, 0.02, 1, 0.97])

    out_file = out_dir / "testbed_vs_smc_all_15_features.png"
    fig.savefig(out_file, dpi=300)
    plt.close(fig)
    print(f"✓ Saved full 15-feature dashboard to {out_file}")


# -----------------------------------------------------------------------------
# Summary CSV Generation
# -----------------------------------------------------------------------------
def export_summary_csv(testbed_res: Dict[str, Dict[str, Any]],
                       smc_res: Dict[str, Dict[str, Any]],
                       out_dir: Path):
    """
    Export comprehensive tabular comparison CSV.
    """
    rows = []
    protocols = ["only_obfs", "only_skyhook", "only_webtunnel"]

    for proto in protocols:
        p_display = PROTOCOL_DISPLAY_NAMES.get(proto, proto)
        all_feats = sorted(set(list(testbed_res.get(proto, {}).keys()) + list(smc_res.get(proto, {}).keys())))

        for feat in all_feats:
            threshold = FEATURE_THRESHOLDS.get(feat, np.nan)
            tb_data = testbed_res.get(proto, {}).get(feat, {})
            tb_k = tb_data.get("k", np.nan)

            smc_data = smc_res.get(proto, {}).get(feat, {})
            smc_k = smc_data.get("k", np.nan)

            for w in CUM_WINDOWS:
                sec = w["seconds"]
                smc_win = w["smc_window"]

                tb_score = tb_data.get("cusum_scores", {}).get(sec, np.nan)
                smc_score = smc_data.get("scores", {}).get(smc_win, np.nan)
                smc_radius = smc_data.get("radii", {}).get(smc_win, np.nan)

                tb_alarm = (tb_score >= threshold) if not np.isnan(tb_score) and not np.isnan(threshold) else False
                smc_alarm = (smc_score >= threshold) if not np.isnan(smc_score) and not np.isnan(threshold) else False

                rows.append({
                    "protocol": proto,
                    "protocol_display": p_display,
                    "feature": feat,
                    "feature_title": FEATURE_TITLES.get(feat, feat),
                    "time_window_s": sec,
                    "smc_window_label": smc_win,
                    "threshold_h": threshold,
                    "testbed_k": tb_k,
                    "testbed_cusum_St": tb_score,
                    "testbed_alarm": tb_alarm,
                    "smc_k": smc_k,
                    "smc_cusum_mean": smc_score,
                    "smc_cusum_radius": smc_radius,
                    "smc_alarm": smc_alarm,
                })

    df = pd.DataFrame(rows)
    csv_file = out_dir / "testbed_vs_smc_cusum_summary.csv"
    df.to_csv(csv_file, index=False)
    print(f"✓ Saved summary CSV to {csv_file}")


# -----------------------------------------------------------------------------
# Main Execution
# -----------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Compare isolated channel testbed CUSUM results vs Maude SMC results."
    )
    parser.add_argument(
        "--testbed-dir",
        default="testbed/data",
        help="Path to testbed data directory (default: testbed/data)"
    )
    parser.add_argument(
        "--output-dir",
        default="testbed/analysis",
        help="Output directory for generated comparison plots and CSV"
    )

    args = parser.parse_args()
    set_plot_style()

    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent

    testbed_data_dir = Path(args.testbed_dir)
    if not testbed_data_dir.is_absolute():
        testbed_data_dir = repo_root / testbed_data_dir

    out_dir = Path(args.output_dir)
    if not out_dir.is_absolute():
        out_dir = repo_root / out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 75)
    print(" Comparing Testbed Isolated Channel CUSUM vs Maude SMC Simulation")
    print("=" * 75)
    print(f" Testbed Data Directory: {testbed_data_dir}")
    print(f" Output Directory:       {out_dir}")
    print("=" * 75)

    # 1. Compute Testbed CUSUM
    print("\n[1/3] Computing Testbed Cumulative CUSUM Scores...")
    testbed_results = compute_testbed_cusum(testbed_data_dir)
    for p, feats in testbed_results.items():
        print(f"  ✓ {PROTOCOL_DISPLAY_NAMES.get(p, p)}: {len(feats)} features processed.")

    # 2. Load SMC CUSUM Results
    print("\n[2/3] Loading Maude SMC Cumulative CUSUM Results...")
    smc_results = load_smc_cusum_results(repo_root)
    for p, feats in smc_results.items():
        print(f"  ✓ {PROTOCOL_DISPLAY_NAMES.get(p, p)}: {len(feats)} features loaded.")

    # 3. Generate Plots & Summary CSV
    print("\n[3/3] Generating Comparison Visualizations & Summary CSV...")
    plot_testbed_vs_smc_superplot(testbed_results, smc_results, out_dir)
    plot_testbed_vs_smc_all_15_features(testbed_results, smc_results, out_dir)
    export_summary_csv(testbed_results, smc_results, out_dir)

    # Per-protocol comparison figures
    sc2_analysis_dir = repo_root / "use-cases/challenge-problem-3/cp3_scenarios/scenario2_isolated_plus_tgen/results/analysis"
    for proto in ["only_obfs", "only_skyhook", "only_webtunnel"]:
        plot_single_protocol_cusum_comparison(testbed_results, smc_results, proto, out_dir)
        # Also copy / save to scenario2 analysis folders
        if sc2_analysis_dir.exists():
            plot_single_protocol_cusum_comparison(testbed_results, smc_results, proto, sc2_analysis_dir)
            p_sub = sc2_analysis_dir / proto
            if p_sub.exists():
                plot_single_protocol_cusum_comparison(testbed_results, smc_results, proto, p_sub)

    print("\n" + "=" * 75)
    print(" All Visualizations & Summaries Generated Successfully!")
    print(f" Output Location: {out_dir}")
    print("=" * 75)


if __name__ == "__main__":
    main()
