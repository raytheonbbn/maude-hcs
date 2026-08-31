#!/usr/bin/env python3
"""
plot_scenario1_comparison.py

Generates publication-quality comparison plots for CP3 Scenario 1:
1. Performance Superplot: Compares SMC (7,271s duration) and Testbed (11,700s duration)
   on Latency (p0, p25, p50, p75, p100), Goodput, Integrity, and Availability.
2. Adversary Metrics Multi-Panel Plot: Plots the cumulative CUSUM Z(t) scores at time 1811
   for all 5 features across all vantage points from conf_formatted and conf_combo2_formatted.
"""

import json
import glob
import os
from pathlib import Path
from typing import Dict, Any, List, Tuple

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import matplotlib.ticker as ticker

# Styling Constants
plt.rcParams.update({
    "font.sans-serif": ["DejaVu Sans", "Helvetica", "Arial"],
    "axes.edgecolor": "#333333",
    "axes.linewidth": 0.8,
    "grid.color": "#e0e0e0",
    "grid.linestyle": "--",
    "grid.alpha": 0.7,
})

SMC_COLOR = "#1f77b4"        # Blue
TB_COLOR = "#ff7f0e"         # Orange / Testbed
SMC_BAR_KWARGS = {"color": SMC_COLOR, "edgecolor": "#111111", "linewidth": 0.7, "alpha": 0.88}
TB_BAR_KWARGS = {"color": TB_COLOR, "edgecolor": "#000000", "linewidth": 0.9, "alpha": 0.82, "hatch": "//"}

FEATURE_LABELS = {
    "dns_query_rate": "DNS Query Rate",
    "tcp_outgoing_packet_rate": "TCP Out Rate",
    "tcp_incoming_packet_rate": "TCP In Rate",
    "packet_size_mean": "Packet Size Mean",
    "packet_interarrival_mean": "Inter-arrival Mean",
}

VP_DISPLAY_NAMES = {
    "ixp-router": "IXP Router (ixp-router)",
    "client_net_sky": "Skyhook Client Net (client_net_sky)",
    "server_net": "Server Net (server_net)",
    "client_net_mastodon": "Mastodon Client Net (client_net_mastodon)",
    "client_net_racetunnel": "RaceTunnel Client Net (client_net_racetunnel)",
}


def load_smc_performance_data(perf_dir: Path) -> Dict[str, Any]:
    """Load and aggregate all SMC performance runs at duration 7271 (t10_t7210)."""
    files = sorted(perf_dir.glob("*.json"))
    if not files:
        raise FileNotFoundError(f"No JSON files found in {perf_dir}")

    records = {
        "latency0": [],
        "latency25": [],
        "latency50": [],
        "latency75": [],
        "latency100": [],
        "goodput": [],
        "availability": [],
        "global_integrity": [],
        "client_integrity": {f"alice_{i}": [] for i in range(1, 10)}
    }

    for fpath in files:
        with open(fpath, "r") as f:
            d = json.load(f)
        for lat_k in ["latency0", "latency25", "latency50", "latency75", "latency100"]:
            val = d[lat_k]["cumulative"].get("t10_t7210", 0.0)
            records[lat_k].append(val)

        records["goodput"].append(d["goodput"]["cumulative"].get("t10_t7210", 0.0))
        records["availability"].append(d["availability"]["cumulative"].get("t10_t7210", 0.0))
        records["global_integrity"].append(d["integrity"]["global_integrity"]["cumulative"].get("t10_t7210", 0.0))

        for i in range(1, 10):
            k = f"alice_{i}_integrity"
            val = d["integrity"].get(k, {}).get("cumulative", {}).get("t10_t7210", 0.0)
            records["client_integrity"][f"alice_{i}"].append(val)

    def stats(arr):
        a = np.array(arr)
        n = len(a)
        m = np.mean(a)
        s = np.std(a, ddof=1) if n > 1 else 0.0
        ci = 1.96 * s / np.sqrt(n) if n > 0 else 0.0
        return {"mean": float(m), "std": float(s), "ci95": float(ci), "n": n, "values": a}

    summary = {
        "n_runs": len(files),
        "latency0": stats(records["latency0"]),
        "latency25": stats(records["latency25"]),
        "latency50": stats(records["latency50"]),
        "latency75": stats(records["latency75"]),
        "latency100": stats(records["latency100"]),
        "goodput": stats(records["goodput"]),
        "availability": stats(records["availability"]),
        "global_integrity": stats(records["global_integrity"]),
        "client_integrity": {k: stats(v) for k, v in records["client_integrity"].items()}
    }
    return summary


def load_testbed_performance_data(cpm_path: Path, latencies_dir: Path) -> Dict[str, Any]:
    """Load and aggregate Testbed performance results (window t0_t11700 / full duration)."""
    with open(cpm_path, "r") as f:
        tb_json = json.load(f)["compiled_performance_metrics"]

    # Window key for full duration (11,700s)
    win = "t0_t11700" if "t0_t11700" in tb_json["goodput"]["cumulative"] else "t0_t12600"

    def stats_from_list(arr):
        a = np.array(arr)
        n = len(a)
        m = np.mean(a)
        s = np.std(a, ddof=1) if n > 1 else 0.0
        ci = 1.96 * s / np.sqrt(n) if n > 0 else 0.0
        return {"mean": float(m), "std": float(s), "ci95": float(ci), "n": n, "values": a}

    goodput_stats = stats_from_list(tb_json["goodput"]["cumulative"][win])
    availability_stats = stats_from_list(tb_json["availability"]["cumulative"][win])
    global_integrity_stats = stats_from_list(tb_json["integrity"]["global_integrity"]["cumulative"][win])

    client_integrity = {}
    for i in range(1, 10):
        k = f"alice_{i}_integrity"
        if k in tb_json["integrity"]:
            client_integrity[f"alice_{i}"] = stats_from_list(tb_json["integrity"][k]["cumulative"][win])

    # Latency percentiles across all latency files
    lat_files = sorted(latencies_dir.glob("*.json"))
    p0_list, p25_list, p50_list, p75_list, p100_list = [], [], [], [], []

    for fpath in lat_files:
        with open(fpath, "r") as f:
            d = json.load(f)
        cum = d.get("cumulative", {})
        target_win = win if win in cum else ("t0_t11700" if "t0_t11700" in cum else list(cum.keys())[-1])
        if target_win in cum and len(cum[target_win]) > 0:
            arr = np.array(cum[target_win])
            p0_list.append(np.percentile(arr, 0))
            p25_list.append(np.percentile(arr, 25))
            p50_list.append(np.percentile(arr, 50))
            p75_list.append(np.percentile(arr, 75))
            p100_list.append(np.percentile(arr, 100))

    summary = {
        "n_runs": len(goodput_stats["values"]),
        "win": win,
        "latency0": stats_from_list(p0_list),
        "latency25": stats_from_list(p25_list),
        "latency50": stats_from_list(p50_list),
        "latency75": stats_from_list(p75_list),
        "latency100": stats_from_list(p100_list),
        "goodput": goodput_stats,
        "availability": availability_stats,
        "global_integrity": global_integrity_stats,
        "client_integrity": client_integrity
    }
    return summary


def plot_performance_superplot(smc_perf: Dict[str, Any], tb_perf: Dict[str, Any], out_path: Path):
    """
    Generate Superplot comparing SMC (7,271s) vs Testbed (11,700s) on:
    - Latencies (p0, p25, p50, p75, p100) [Log Scale]
    - Goodput (bps)
    - System Integrity (Global & Per-client)
    - Availability (MTBF)
    """
    fig, axes = plt.subplots(2, 2, figsize=(16, 10.5))

    # =========================================================================
    # Panel 1 (Top-Left): Latency Percentiles (p0, p25, p50, p75, p100)
    # =========================================================================
    ax1 = axes[0, 0]
    lat_keys = ["latency0", "latency25", "latency50", "latency75", "latency100"]
    lat_labels = ["p0 (min)", "p25", "p50 (median)", "p75", "p100 (max)"]
    x1 = np.arange(len(lat_keys))
    w1 = 0.36

    smc_lat_means = [smc_perf[k]["mean"] for k in lat_keys]
    smc_lat_ci = [smc_perf[k]["ci95"] for k in lat_keys]

    tb_lat_means = [tb_perf[k]["mean"] for k in lat_keys]
    tb_lat_ci = [tb_perf[k]["ci95"] for k in lat_keys]

    rects_smc1 = ax1.bar(x1 - w1/2, smc_lat_means, w1, yerr=smc_lat_ci, capsize=3.5,
                         label=f"SMC Simulation (7,271s, N={smc_perf['n_runs']})", **SMC_BAR_KWARGS)
    rects_tb1 = ax1.bar(x1 + w1/2, tb_lat_means, w1, yerr=tb_lat_ci, capsize=3.5,
                        label=f"Real Testbed (11,700s, N={tb_perf['n_runs']})", **TB_BAR_KWARGS)

    # Annotations placed cleanly above error bars
    for rect, err in zip(rects_smc1, smc_lat_ci):
        h = rect.get_height()
        top_y = h + err
        ax1.annotate(f"{h:.3f}" if h < 1.0 else (f"{h:.1f}" if h < 100 else f"{h:.0f}"),
                     xy=(rect.get_x() + rect.get_width() / 2, top_y),
                     xytext=(0, 4), textcoords="offset points",
                     ha="center", va="bottom", fontsize=8.0, fontweight="medium")

    for rect, err in zip(rects_tb1, tb_lat_ci):
        h = rect.get_height()
        top_y = h + err
        ax1.annotate(f"{h:.3f}" if h < 1.0 else (f"{h:.1f}" if h < 100 else f"{h:.0f}"),
                     xy=(rect.get_x() + rect.get_width() / 2, top_y),
                     xytext=(0, 4), textcoords="offset points",
                     ha="center", va="bottom", fontsize=8.0, fontweight="medium")

    ax1.set_yscale("log")
    ax1.set_title("Mean Latencies across Percentiles [Log Scale]", fontsize=12, fontweight="bold", pad=8)
    ax1.set_xlabel("Latency Metric", fontsize=10, fontweight="bold")
    ax1.set_ylabel("Latency (seconds)", fontsize=10, fontweight="bold")
    ax1.set_xticks(x1)
    ax1.set_xticklabels(lat_labels, fontsize=9.5)
    ax1.set_ylim(0.02, 10000)
    ax1.grid(True, axis="y")
    ax1.legend(frameon=True, facecolor="#fefefe", fontsize=8.5, loc="upper left")

    # =========================================================================
    # Panel 2 (Top-Right): Goodput
    # =========================================================================
    ax2 = axes[0, 1]
    x2 = np.array([0])
    w2 = 0.32

    smc_gp = smc_perf["goodput"]
    tb_gp = tb_perf["goodput"]

    r_smc2 = ax2.bar(x2 - w2/2 - 0.05, [smc_gp["mean"]], w2, yerr=[smc_gp["ci95"]], capsize=4,
                     label="SMC Simulation", **SMC_BAR_KWARGS)
    r_tb2 = ax2.bar(x2 + w2/2 + 0.05, [tb_gp["mean"]], w2, yerr=[tb_gp["ci95"]], capsize=4,
                    label="Real Testbed", **TB_BAR_KWARGS)

    for r in r_smc2:
        h = r.get_height()
        top_y = h + smc_gp["ci95"]
        ax2.annotate(f"{h:.1f} bps\n(±{smc_gp['ci95']:.1f})",
                     xy=(r.get_x() + r.get_width() / 2, top_y),
                     xytext=(0, 5), textcoords="offset points",
                     ha="center", va="bottom", fontsize=9.5, fontweight="bold")

    for r in r_tb2:
        h = r.get_height()
        top_y = h + tb_gp["ci95"]
        ax2.annotate(f"{h:.1f} bps\n(±{tb_gp['ci95']:.1f})",
                     xy=(r.get_x() + r.get_width() / 2, top_y),
                     xytext=(0, 5), textcoords="offset points",
                     ha="center", va="bottom", fontsize=9.5, fontweight="bold")

    ax2.set_title("System Goodput (Bits/s)", fontsize=12, fontweight="bold", pad=8)
    ax2.set_ylabel("Goodput (Bits/s)", fontsize=10, fontweight="bold")
    ax2.set_xticks(x2)
    ax2.set_xticklabels(["Overall System Goodput"], fontsize=10)
    ax2.set_xlim(-0.8, 0.8)
    ax2.set_ylim(0, max(smc_gp["mean"] + smc_gp["ci95"], tb_gp["mean"] + tb_gp["ci95"]) * 1.25)
    ax2.grid(True, axis="y")
    ax2.legend(frameon=True, facecolor="#fefefe", fontsize=9, loc="upper right")

    # =========================================================================
    # Panel 3 (Bottom-Left): System & Client Integrity
    # =========================================================================
    ax3 = axes[1, 0]
    integ_labels = ["Global", "Alice 1\n(WT1)", "Alice 2\n(WT2)", "Alice 3\n(Sky1)", "Alice 4\n(Sky2)",
                    "Alice 5\n(OBFS1)", "Alice 6\n(OBFS2)", "Alice 7\n(Iod1)", "Alice 8\n(Iod2)", "Alice 9\n(Mas)"]
    x3 = np.arange(len(integ_labels))
    w3 = 0.38

    smc_integ_means = [smc_perf["global_integrity"]["mean"]] + [smc_perf["client_integrity"][f"alice_{i}"]["mean"] for i in range(1, 10)]
    smc_integ_ci = [smc_perf["global_integrity"]["ci95"]] + [smc_perf["client_integrity"][f"alice_{i}"]["ci95"] for i in range(1, 10)]

    tb_integ_means = [tb_perf["global_integrity"]["mean"]] + [tb_perf["client_integrity"].get(f"alice_{i}", {"mean": 0.0})["mean"] for i in range(1, 10)]
    tb_integ_ci = [tb_perf["global_integrity"]["ci95"]] + [tb_perf["client_integrity"].get(f"alice_{i}", {"ci95": 0.0})["ci95"] for i in range(1, 10)]

    r_smc3 = ax3.bar(x3 - w3/2, smc_integ_means, w3, yerr=smc_integ_ci, capsize=2.5,
                     label="SMC Simulation", **SMC_BAR_KWARGS)
    r_tb3 = ax3.bar(x3 + w3/2, tb_integ_means, w3, yerr=tb_integ_ci, capsize=2.5,
                    label="Real Testbed", **TB_BAR_KWARGS)

    for r, err in zip(r_smc3, smc_integ_ci):
        h = r.get_height()
        top_y = h + err
        ax3.annotate(f"{h:.2f}",
                     xy=(r.get_x() + r.get_width() / 2, top_y),
                     xytext=(0, 3), textcoords="offset points",
                     ha="center", va="bottom", fontsize=7.2)

    for r, err in zip(r_tb3, tb_integ_ci):
        h = r.get_height()
        top_y = h + err
        ax3.annotate(f"{h:.2f}",
                     xy=(r.get_x() + r.get_width() / 2, top_y),
                     xytext=(0, 3), textcoords="offset points",
                     ha="center", va="bottom", fontsize=7.2)

    ax3.set_title("System & Client Integrity", fontsize=12, fontweight="bold", pad=8)
    ax3.set_ylabel("Integrity Ratio [0-1]", fontsize=10, fontweight="bold")
    ax3.set_xticks(x3)
    ax3.set_xticklabels(integ_labels, fontsize=8.2)
    ax3.set_ylim(0, 1.15)
    ax3.grid(True, axis="y")
    ax3.legend(frameon=True, facecolor="#fefefe", fontsize=8.5, loc="lower right")

    # =========================================================================
    # Panel 4 (Bottom-Right): Availability (MTBF)
    # =========================================================================
    ax4 = axes[1, 1]
    x4 = np.array([0])
    w4 = 0.32

    smc_av = smc_perf["availability"]
    tb_av = tb_perf["availability"]

    r_smc4 = ax4.bar(x4 - w4/2 - 0.05, [smc_av["mean"]], w4, yerr=[smc_av["ci95"]], capsize=4,
                     label="SMC Simulation", **SMC_BAR_KWARGS)
    r_tb4 = ax4.bar(x4 + w4/2 + 0.05, [tb_av["mean"]], w4, yerr=[tb_av["ci95"]], capsize=4,
                    label="Real Testbed", **TB_BAR_KWARGS)

    for r in r_smc4:
        h = r.get_height()
        top_y = h + smc_av["ci95"]
        ax4.annotate(f"{h:.1f} s\n(±{smc_av['ci95']:.1f})",
                     xy=(r.get_x() + r.get_width() / 2, top_y),
                     xytext=(0, 5), textcoords="offset points",
                     ha="center", va="bottom", fontsize=9.5, fontweight="bold")

    for r in r_tb4:
        h = r.get_height()
        top_y = h + tb_av["ci95"]
        ax4.annotate(f"{h:.2f} s\n(±{tb_av['ci95']:.2f})",
                     xy=(r.get_x() + r.get_width() / 2, top_y),
                     xytext=(0, 5), textcoords="offset points",
                     ha="center", va="bottom", fontsize=9.5, fontweight="bold")

    ax4.set_title("Availability (MTBF)", fontsize=12, fontweight="bold", pad=8)
    ax4.set_ylabel("Mean Time Between Failures (seconds)", fontsize=10, fontweight="bold")
    ax4.set_xticks(x4)
    ax4.set_xticklabels(["System Availability (MTBF)"], fontsize=10)
    ax4.set_xlim(-0.8, 0.8)
    ax4.set_ylim(0, max(smc_av["mean"] + smc_av["ci95"], tb_av["mean"] + tb_av["ci95"]) * 1.25)
    ax4.grid(True, axis="y")
    ax4.legend(frameon=True, facecolor="#fefefe", fontsize=9, loc="upper right")

    # Main Figure Title
    fig.suptitle("Superplot: CP3 Scenario 1 Performance Comparison (SMC vs Testbed)",
                 fontsize=15, fontweight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0.02, 1, 0.95])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300)
    print(f"Saved performance superplot to {out_path}")
    plt.close(fig)


def load_smc_adversary_data(conf_dir: Path, combo2_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Load SMC adversary runs for both combo1 (conf) and combo2 vantage points."""
    vps_data = {}

    def parse_dir(dpath: Path, source_label: str):
        files = sorted(dpath.glob("*.json"))
        if not files:
            raise FileNotFoundError(f"No JSON files found in {dpath}")
        for fpath in files:
            with open(fpath, "r") as f:
                d = json.load(f)
            for vp, vp_d in d["vantage_points"].items():
                if vp not in vps_data:
                    vps_data[vp] = {"source": source_label, "n_runs": len(files), "features": {}}
                for feat, feat_d in vp_d.items():
                    if feat not in vps_data[vp]["features"]:
                        vps_data[vp]["features"][feat] = []
                    val = feat_d["cumulative"].get("t10_t1810", 0.0)
                    vps_data[vp]["features"][feat].append(val)

    parse_dir(conf_dir, "conf_formatted")
    parse_dir(combo2_dir, "conf_combo2_formatted")

    # Aggregate stats
    aggregated = {}
    for vp, info in vps_data.items():
        aggregated[vp] = {"source": info["source"], "n_runs": info["n_runs"], "features": {}}
        for feat, vals in info["features"].items():
            a = np.array(vals)
            n = len(a)
            m = np.mean(a)
            s = np.std(a, ddof=1) if n > 1 else 0.0
            ci = 1.96 * s / np.sqrt(n) if n > 0 else 0.0
            aggregated[vp]["features"][feat] = {
                "mean": float(m),
                "std": float(s),
                "ci95": float(ci),
                "n": n,
                "values": a
            }
    return aggregated


def load_testbed_adversary_data(cam_path: Path) -> Dict[str, Dict[str, float]]:
    """Load Testbed adversary metrics at time window t0_t1800 (time 1800/1811)."""
    with open(cam_path, "r") as f:
        tb_cam = json.load(f)["compiled_adversary_metrics"]["vantage_points"]

    tb_data = {}
    for vp, vp_d in tb_cam.items():
        tb_data[vp] = {}
        for feat, feat_d in vp_d.items():
            cum = feat_d.get("cumulative", {})
            if "t0_t1800" in cum:
                val = cum["t0_t1800"]
                tb_data[vp][feat] = float(val[0] if isinstance(val, list) else val)
            else:
                tb_data[vp][feat] = 0.0
    return tb_data


def plot_adversary_superplot(smc_adv: Dict[str, Any], tb_adv: Dict[str, Any], out_path: Path):
    """
    Generate Adversary Multi-Panel plot:
    One subplot per vantage point used in conf_formatted and conf_combo2_formatted:
    - ixp-router
    - client_net_sky
    - server_net
    - client_net_mastodon
    - client_net_racetunnel
    Y-axis is cumulative CUSUM Z(t) score at time 1811 across all 5 features.
    """
    vps_order = [
        "ixp-router",
        "client_net_sky",
        "server_net",
        "client_net_mastodon",
        "client_net_racetunnel",
    ]
    features = [
        "dns_query_rate",
        "tcp_outgoing_packet_rate",
        "tcp_incoming_packet_rate",
        "packet_size_mean",
        "packet_interarrival_mean",
    ]

    fig, axes = plt.subplots(2, 3, figsize=(18, 11))
    axes_flat = axes.flatten()

    for idx, vp in enumerate(vps_order):
        ax = axes_flat[idx]
        vp_smc = smc_adv.get(vp, {"features": {}, "n_runs": 0})
        vp_tb = tb_adv.get(vp, {})
        n_runs = vp_smc.get("n_runs", 0)

        x = np.arange(len(features))
        w = 0.38

        smc_means = [vp_smc["features"].get(f, {"mean": 0.0})["mean"] for f in features]
        smc_cis = [vp_smc["features"].get(f, {"ci95": 0.0})["ci95"] for f in features]
        tb_vals = [vp_tb.get(f, 0.0) for f in features]

        r_smc = ax.bar(x - w/2, smc_means, w, yerr=smc_cis, capsize=3,
                       label=f"SMC Simulation (N={n_runs})", **SMC_BAR_KWARGS)
        r_tb = ax.bar(x + w/2, tb_vals, w,
                      label="Real Testbed", **TB_BAR_KWARGS)

        # Annotations cleanly placed above error bars
        for r, err in zip(r_smc, smc_cis):
            h = r.get_height()
            if h > 0.01:
                top_y = h + err
                ax.annotate(f"{h:.1f}",
                            xy=(r.get_x() + r.get_width() / 2, top_y),
                            xytext=(0, 4), textcoords="offset points",
                            ha="center", va="bottom", fontsize=7.5, fontweight="medium")

        for r in r_tb:
            h = r.get_height()
            if h > 0.01:
                ax.annotate(f"{h:.1f}",
                            xy=(r.get_x() + r.get_width() / 2, h),
                            xytext=(0, 4), textcoords="offset points",
                            ha="center", va="bottom", fontsize=7.5, fontweight="medium")

        vp_name = VP_DISPLAY_NAMES.get(vp, vp)
        ax.set_title(f"Vantage Point: {vp_name}", fontsize=11, fontweight="bold", pad=6)
        ax.set_ylabel("Cumulative CUSUM Z(t)", fontsize=9.5, fontweight="bold")
        ax.set_xticks(x)
        feat_display = [FEATURE_LABELS.get(f, f) for f in features]
        ax.set_xticklabels(feat_display, rotation=20, ha="right", fontsize=8.5)
        ax.grid(True, axis="y")

        # Upper limit with breathing room
        max_val = max(
            max([m + e for m, e in zip(smc_means, smc_cis)] + [0]),
            max(tb_vals + [0]),
            4.0
        )
        ax.set_ylim(0, max_val * 1.30)
        ax.legend(frameon=True, facecolor="#fefefe", fontsize=8.5, loc="upper right")

    # Panel 6 (Summary Overview across all VPs for DNS Query Rate)
    ax6 = axes_flat[5]
    vp_short_labels = ["IXP", "Skyhook Cl", "Server Net", "Mastodon Cl", "RaceTunnel Cl"]
    x6 = np.arange(len(vps_order))
    w6 = 0.38

    dns_smc_means = [smc_adv.get(vp, {}).get("features", {}).get("dns_query_rate", {"mean": 0.0})["mean"] for vp in vps_order]
    dns_smc_cis = [smc_adv.get(vp, {}).get("features", {}).get("dns_query_rate", {"ci95": 0.0})["ci95"] for vp in vps_order]
    dns_tb_vals = [tb_adv.get(vp, {}).get("dns_query_rate", 0.0) for vp in vps_order]

    r_smc6 = ax6.bar(x6 - w6/2, dns_smc_means, w6, yerr=dns_smc_cis, capsize=3,
                     label="SMC Simulation", **SMC_BAR_KWARGS)
    r_tb6 = ax6.bar(x6 + w6/2, dns_tb_vals, w6,
                    label="Real Testbed", **TB_BAR_KWARGS)

    for r, err in zip(r_smc6, dns_smc_cis):
        h = r.get_height()
        if h > 0.01:
            top_y = h + err
            ax6.annotate(f"{h:.1f}",
                         xy=(r.get_x() + r.get_width() / 2, top_y),
                         xytext=(0, 4), textcoords="offset points",
                         ha="center", va="bottom", fontsize=7.5, fontweight="medium")

    for r in r_tb6:
        h = r.get_height()
        if h > 0.01:
            ax6.annotate(f"{h:.1f}",
                         xy=(r.get_x() + r.get_width() / 2, h),
                         xytext=(0, 4), textcoords="offset points",
                         ha="center", va="bottom", fontsize=7.5, fontweight="medium")

    ax6.set_title("Cross-VP Comparison: DNS Query Rate at t=1811", fontsize=11, fontweight="bold", pad=6)
    ax6.set_ylabel("Cumulative CUSUM Z(t)", fontsize=9.5, fontweight="bold")
    ax6.set_xticks(x6)
    ax6.set_xticklabels(vp_short_labels, rotation=20, ha="right", fontsize=8.5)
    ax6.grid(True, axis="y")
    max_dns = max(
        max([m + e for m, e in zip(dns_smc_means, dns_smc_cis)]),
        max(dns_tb_vals)
    )
    ax6.set_ylim(0, max_dns * 1.30)
    ax6.legend(frameon=True, facecolor="#fefefe", fontsize=8.5, loc="upper right")

    fig.suptitle("Superplot: CP3 Scenario 1 Adversary Metrics CUSUM Scores at t=1811 (SMC vs Testbed)",
                 fontsize=15, fontweight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0.02, 1, 0.95])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300)
    print(f"Saved adversary superplot to {out_path}")
    plt.close(fig)


def main():
    repo_root = Path(__file__).resolve().parent.parent

    # Input paths
    tb_perf_json = repo_root / "scenario1_te/scenario_1_507/compiled_performance_metrics.json"
    tb_lat_dir = repo_root / "scenario1_te/scenario_1_507/latencies"
    tb_adv_json = repo_root / "scenario1_te/scenario_1_507/compiled_adversary_metrics.json"

    smc_perf_dir = repo_root / "scenario1_smc_results/scenario1_7271_perf_formatted"
    smc_conf_dir = repo_root / "scenario1_smc_results/scenario1_1811_conf_formatted"
    smc_combo2_dir = repo_root / "scenario1_smc_results/scenario1_1811_conf_combo2_formatted"

    # Output directories
    out_dirs = [
        repo_root / "scenario1_smc_results/analysis",
        repo_root / "scenario1_te/scenario_1_507/analysis",
    ]

    print(">>> Loading Performance Data...")
    smc_perf = load_smc_performance_data(smc_perf_dir)
    tb_perf = load_testbed_performance_data(tb_perf_json, tb_lat_dir)

    print(">>> Loading Adversary Data...")
    smc_adv = load_smc_adversary_data(smc_conf_dir, smc_combo2_dir)
    tb_adv = load_testbed_adversary_data(tb_adv_json)

    for od in out_dirs:
        print(f"\n>>> Generating Figures in {od}...")
        perf_out = od / "superplot_scenario1_performance.png"
        plot_performance_superplot(smc_perf, tb_perf, perf_out)

        adv_out = od / "superplot_scenario1_adversary_cusum.png"
        plot_adversary_superplot(smc_adv, tb_adv, adv_out)

    print("\n>>> All Scenario 1 comparison plots generated successfully!")


if __name__ == "__main__":
    main()
