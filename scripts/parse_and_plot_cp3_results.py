#!/usr/bin/env python3
"""
Parse and Plot CP3 Scenario Isolated Protocol Results (Supports Comparison Mode).

This script:
1. Parses the QuaTEx query definition file to map each query line number to a human-readable name,
   scope (independent vs cumulative), metric type, time window, and target client/vantage point.
2. Parses JSON result files produced by SMC for one or two protocol experiment sets.
3. If `--compare` is supplied, loads a second set of experiment results and plots side-by-side bar comparisons
   (e.g., HCS+TGen vs TGen Only) for each protocol and time window.
4. Outputs tabular and CSV summaries of all queries with human-readable descriptions.
5. Saves all generated plots and data into the centralized `analysis/` directory.
"""

import os
import re
import json
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import matplotlib.ticker as ticker
import pandas as pd

# -----------------------------------------------------------------------------
# Human-readable Client & Vantage Mappings
# -----------------------------------------------------------------------------
CLIENT_NAMES = {
    "wtCl1IrcAddr": "WebTunnel Cl 1",
    "wtCl2IrcAddr": "WebTunnel Cl 2",
    "skyCl3IrcAddr": "Skyhook Cl 3",
    "skyCl4IrcAddr": "Skyhook Cl 4",
    "obfsCl5IrcAddr": "Obfs4 Cl 5",
    "obfsCl6IrcAddr": "Obfs4 Cl 6",
    "iodCl7IrcAddr": "Iodine Cl 7",
    "iodCl8IrcAddr": "Iodine Cl 8",
    "masCl9IrcAddr": "Mastodon Cl 9",
}

VANTAGE_NAMES = {
    "ixpN": "IXP Network (ixpN)",
    "cl[5]": "Client Net (cl[5])",
}

PROTOCOL_DISPLAY_NAMES = {
    "only_iodine": "Iodine (DNS Tunnel)",
    "only_mastodon": "Mastodon",
    "only_obfs": "OBFS4",
    "only_skyhook": "Skyhook",
    "only_webtunnel": "WebTunnel",
}

PROTOCOL_COLORS = {
    "only_iodine": "#CC79A7",     # Reddish Purple
    "only_mastodon": "#56B4E9",   # Sky Blue
    "only_obfs": "#E69F00",       # Orange
    "only_skyhook": "#D55E00",    # Vermillion / Red-Orange
    "only_webtunnel": "#009E73",  # Bluish Green
}

METRIC_CONFIG = {
    "latency0": {"name": "Min Latency (p0)", "unit": "s", "group": "latency"},
    "latency25": {"name": "25th Percentile Latency (p25)", "unit": "s", "group": "latency"},
    "latency50": {"name": "Median Latency (p50)", "unit": "s", "group": "latency"},
    "latency75": {"name": "75th Percentile Latency (p75)", "unit": "s", "group": "latency"},
    "latency100": {"name": "Max Latency (p100)", "unit": "s", "group": "latency"},
    "goodput": {"name": "Goodput", "unit": "Bits/s", "group": "goodput"},
    "integrity": {"name": "Integrity", "unit": "ratio [0-1]", "group": "integrity"},
    "availability": {"name": "Availability (MTBF)", "unit": "s", "group": "availability"},
    "dns_query_rate": {"name": "DNS Query Rate", "unit": "queries/s", "group": "adversary"},
    "tcp_outgoing_packet_rate": {"name": "TCP Outgoing Packet Rate", "unit": "pkts/s", "group": "adversary"},
    "tcp_incoming_packet_rate": {"name": "TCP Incoming Packet Rate", "unit": "pkts/s", "group": "adversary"},
    "packet_size_mean": {"name": "Mean Packet Size", "unit": "bytes", "group": "adversary"},
    "packet_interarrival_mean": {"name": "Mean Packet Inter-arrival", "unit": "s", "group": "adversary"},
}

# -----------------------------------------------------------------------------
# QuaTEx Parsing
# -----------------------------------------------------------------------------
def parse_quatex_file(quatex_path: Path) -> Dict[int, Dict[str, Any]]:
    """
    Parse a QuaTEx file and extract line-by-line query definitions from comments and expressions.
    Returns a dict mapping line_number (1-based) to query metadata.
    """
    if not quatex_path.exists():
        raise FileNotFoundError(f"QuaTEx file not found: {quatex_path}")

    lines = quatex_path.read_text().splitlines()
    queries = {}

    for idx, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or not line.startswith("eval"):
            continue

        comment = ""
        code = line
        if "//" in line:
            parts = line.split("//", 1)
            code = parts[0].strip()
            comment = parts[1].strip()

        # Parse comment tokens: <scope> <metric> <start_time> <end_time> [<extra>]
        c_parts = comment.split()
        scope = "unknown"
        metric = "unknown"
        start_time = None
        end_time = None
        target = "system"

        if len(c_parts) >= 4:
            scope = c_parts[0].lower()       # "cumulative" or "independent"
            metric = c_parts[1]             # "latency50", "goodput", etc.
            try:
                start_time = float(c_parts[2])
                end_time = float(c_parts[3])
            except ValueError:
                pass
            if len(c_parts) >= 5:
                target = c_parts[4]

        # Generate human-readable label
        window_label = f"[{int(start_time) if start_time is not None else '?'}-{int(end_time) if end_time is not None else '?'}]s"
        metric_info = METRIC_CONFIG.get(metric, {"name": metric, "unit": "", "group": "other"})
        metric_name = metric_info["name"]

        target_display = target
        if target in CLIENT_NAMES:
            target_display = CLIENT_NAMES[target]
        elif target in VANTAGE_NAMES:
            target_display = VANTAGE_NAMES[target]
        elif target == "system":
            target_display = "System"

        # Check if query is CUSUM
        is_cusum = "getCUSUMZt" in code
        if is_cusum:
            metric_group = "cusum"
            human_name = f"CUSUM {scope.capitalize()} {metric_name} ({target_display}) {window_label}" if target != "system" else f"CUSUM {scope.capitalize()} {metric_name} {window_label}"
        else:
            metric_group = metric_info["group"]
            if target != "system":
                human_name = f"{scope.capitalize()} {metric_name} ({target_display}) {window_label}"
            else:
                human_name = f"{scope.capitalize()} {metric_name} {window_label}"

        queries[idx] = {
            "line": idx,
            "raw_code": code,
            "raw_comment": comment,
            "scope": scope,
            "metric": metric,
            "metric_group": metric_group,
            "metric_name": metric_name,
            "is_cusum": is_cusum,
            "unit": metric_info["unit"],
            "start_time": start_time,
            "end_time": end_time,
            "window_label": window_label,
            "target": target,
            "target_display": target_display,
            "human_name": human_name,
        }

    return queries


# -----------------------------------------------------------------------------
# JSON Result Parsing
# -----------------------------------------------------------------------------
def parse_json_result(json_path: Path, quatex_meta: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Parse a single simulation result JSON file and link queries with QuaTEx metadata.
    """
    if not json_path.exists():
        raise FileNotFoundError(f"JSON result file not found: {json_path}")

    raw_text = json_path.read_text()
    idx = raw_text.find("{")
    if idx == -1:
        raise ValueError(f"No JSON object found in {json_path}")

    try:
        data = json.loads(raw_text[idx:])
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to decode JSON in {json_path}: {e}")

    nsims = data.get("nsims", 0)
    raw_queries = data.get("queries", [])

    parsed_queries = []
    for q in raw_queries:
        line_no = q.get("line")
        meta = quatex_meta.get(line_no, {})

        parsed_q = {
            "line": line_no,
            "mean": q.get("mean", 0.0),
            "std": q.get("std", 0.0),
            "radius": q.get("radius", 0.0),
            "nsims": q.get("nsims", nsims),
            "discarded": q.get("discarded", 0),
            **meta
        }
        parsed_queries.append(parsed_q)

    return {
        "file": str(json_path),
        "nsims": nsims,
        "queries": parsed_queries,
    }


def load_all_protocol_results(results_base_dir: Path, quatex_meta: Dict[int, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    Find and load results for all protocol directories in the specified base directory.
    """
    protocol_results = {}
    if not results_base_dir.exists():
        raise FileNotFoundError(f"Results directory not found: {results_base_dir}")

    for entry in sorted(results_base_dir.iterdir()):
        if entry.is_dir() and entry.name != "analysis":
            candidate = entry / f"{entry.name}.json"
            if not candidate.exists():
                json_files = list(entry.glob("*.json"))
                if json_files:
                    candidate = json_files[0]
            if candidate.exists():
                proto_quatex = entry / f"{entry.name}-quatex.maude"
                if proto_quatex.exists():
                    p_meta = parse_quatex_file(proto_quatex)
                else:
                    p_meta = quatex_meta
                protocol_results[entry.name] = parse_json_result(candidate, p_meta)
        elif entry.is_file() and entry.suffix == ".json":
            proto_name = entry.stem
            protocol_results[proto_name] = parse_json_result(entry, quatex_meta)

    return protocol_results


def build_flat_dataframe(protocol_results: Dict[str, Dict[str, Any]], dataset_label: str = "Primary") -> pd.DataFrame:
    """
    Flatten all parsed queries across all protocols into a single Pandas DataFrame.
    """
    rows = []
    for proto, pdata in protocol_results.items():
        proto_display = PROTOCOL_DISPLAY_NAMES.get(proto, proto)
        for q in pdata["queries"]:
            row = {
                "dataset": dataset_label,
                "protocol": proto,
                "protocol_display": proto_display,
                "line": q.get("line"),
                "human_name": q.get("human_name"),
                "scope": q.get("scope"),
                "metric": q.get("metric"),
                "metric_group": q.get("metric_group"),
                "metric_name": q.get("metric_name"),
                "is_cusum": q.get("is_cusum", False),
                "unit": q.get("unit"),
                "start_time": q.get("start_time"),
                "end_time": q.get("end_time"),
                "window_label": q.get("window_label"),
                "target": q.get("target"),
                "target_display": q.get("target_display"),
                "mean": q.get("mean"),
                "std": q.get("std"),
                "radius": q.get("radius"),
                "nsims": q.get("nsims"),
            }
            rows.append(row)
    return pd.DataFrame(rows)


def detect_dataset_label(results_path: Path, default_fallback: str) -> str:
    """
    Intelligently infer dataset display label from directory path.
    """
    path_str = str(results_path.resolve()).lower()
    if "isolated_plus_tgen" in path_str:
        return "HCS+TGen"
    elif "tgenonly" in path_str or "tgen_only" in path_str:
        return "TGen Only"
    elif "isolated_protocols" in path_str:
        return "Isolated Protocols"
    
    parent_name = results_path.resolve().parent.name
    current_name = results_path.resolve().name
    if current_name == "results" and parent_name:
        return parent_name
    return current_name if current_name else default_fallback


# -----------------------------------------------------------------------------
# Plotting Helpers & Styling
# -----------------------------------------------------------------------------
def set_plot_style():
    """Configure aesthetic matplotlib parameters."""
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.size": 11,
        "axes.titlesize": 12,
        "axes.titleweight": "bold",
        "axes.labelsize": 11,
        "axes.labelweight": "semibold",
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 9.5,
        "figure.titlesize": 14,
        "figure.titleweight": "bold",
        "grid.alpha": 0.35,
        "grid.linestyle": "--",
        "axes.edgecolor": "#cccccc",
        "axes.linewidth": 0.8,
    })


def make_comparison_legend(ax, protocols: List[str], label1: str, label2: str, loc: str = "upper right"):
    """Create a 2-column legend matching protocol colors with dataset bar styles."""
    handles = []
    for proto in protocols:
        p_name = PROTOCOL_DISPLAY_NAMES.get(proto, proto)
        p_color = PROTOCOL_COLORS.get(proto, "#333333")
        h1 = Patch(facecolor=p_color, edgecolor="#222222", linewidth=0.6, label=f"{p_name} ({label1})")
        h2 = Patch(facecolor=p_color, alpha=0.55, hatch="//", edgecolor="#222222", linewidth=0.6, label=f"{p_name} ({label2})")
        handles.extend([h1, h2])
    ax.legend(handles=handles, frameon=True, facecolor="#fdfdfd", ncols=2, fontsize=8.5, loc=loc)


# -----------------------------------------------------------------------------
# Per-Protocol Individual Plot Functions
# -----------------------------------------------------------------------------
def plot_percentile_latency(df_proto: pd.DataFrame, proto_name: str, out_dir: Path,
                            compare_mode: bool = False, label1: str = "Primary", label2: str = "Comparison"):
    """
    Generate bar charts for percentile latency across time windows.
    """
    lat_metrics = ["latency0", "latency25", "latency50", "latency75", "latency100"]
    lat_labels = ["Min (p0)", "25th (p25)", "Median (p50)", "75th (p75)", "Max (p100)"]
    palette = ["#3498db", "#2980b9", "#1abc9c", "#e67e22", "#e74c3c"]
    proto_display = PROTOCOL_DISPLAY_NAMES.get(proto_name, proto_name)

    if not compare_mode:
        for scope in ["independent", "cumulative"]:
            subset = df_proto[(df_proto["scope"] == scope) & (df_proto["metric"].isin(lat_metrics))]
            if subset.empty:
                continue

            windows = subset.sort_values(by=["start_time", "end_time"])["window_label"].unique()
            fig, ax = plt.subplots(figsize=(9, 5.5))
            x = np.arange(len(windows))
            width = 0.15

            for i, (m, label, color) in enumerate(zip(lat_metrics, lat_labels, palette)):
                m_data = subset[subset["metric"] == m].sort_values(by=["start_time", "end_time"])
                means = [m_data[m_data["window_label"] == w]["mean"].values[0] if not m_data[m_data["window_label"] == w].empty else 0.0 for w in windows]
                rads = [m_data[m_data["window_label"] == w]["radius"].values[0] if not m_data[m_data["window_label"] == w].empty else 0.0 for w in windows]

                offset = (i - 2) * width
                rects = ax.bar(x + offset, means, width, yerr=rads, capsize=3, label=label, color=color, edgecolor="#222222", linewidth=0.6, alpha=0.9)

                for rect in rects:
                    h = rect.get_height()
                    if h > 0.01:
                        ax.annotate(f"{h:.2f}",
                                    xy=(rect.get_x() + rect.get_width() / 2, h),
                                    xytext=(0, 3), textcoords="offset points",
                                    ha="center", va="bottom", fontsize=8, rotation=45)

            ax.set_title(f"{proto_display} - {scope.capitalize()} Latency Percentiles vs Time Window")
            ax.set_xlabel("Time Window (s)")
            ax.set_ylabel("Latency (seconds)")
            ax.set_xticks(x)
            ax.set_xticklabels(windows)
            ax.legend(title="Percentiles", frameon=True, facecolor="#fdfdfd")
            ax.grid(True, axis="y")
            plt.tight_layout()

            out_file = out_dir / f"latency_{scope}_bar.png"
            fig.savefig(out_file, dpi=300)
            plt.close(fig)
    else:
        for scope in ["independent", "cumulative"]:
            subset = df_proto[(df_proto["scope"] == scope) & (df_proto["metric"] == "latency50")]
            if subset.empty:
                continue

            windows = subset.sort_values(by=["start_time", "end_time"])["window_label"].unique()
            fig, ax = plt.subplots(figsize=(9, 5.5))
            x = np.arange(len(windows))
            width = 0.35

            d1_data = subset[subset["dataset"] == label1]
            d2_data = subset[subset["dataset"] == label2]

            d1_means = [d1_data[d1_data["window_label"] == w]["mean"].values[0] if not d1_data[d1_data["window_label"] == w].empty else 0.0 for w in windows]
            d1_rads = [d1_data[d1_data["window_label"] == w]["radius"].values[0] if not d1_data[d1_data["window_label"] == w].empty else 0.0 for w in windows]

            d2_means = [d2_data[d2_data["window_label"] == w]["mean"].values[0] if not d2_data[d2_data["window_label"] == w].empty else 0.0 for w in windows]
            d2_rads = [d2_data[d2_data["window_label"] == w]["radius"].values[0] if not d2_data[d2_data["window_label"] == w].empty else 0.0 for w in windows]

            ax.bar(x - width/2, d1_means, width, yerr=d1_rads, capsize=3, label=f"{label1} (p50)", color="#3498db", edgecolor="#222222", linewidth=0.6)
            ax.bar(x + width/2, d2_means, width, yerr=d2_rads, capsize=3, label=f"{label2} (p50)", color="#3498db", alpha=0.55, hatch="//", edgecolor="#222222", linewidth=0.6)

            ax.set_title(f"{proto_display} - {scope.capitalize()} Median Latency Comparison ({label1} vs {label2})")
            ax.set_xlabel("Time Window (s)")
            ax.set_ylabel("Latency (seconds)")
            ax.set_xticks(x)
            ax.set_xticklabels(windows)
            ax.legend(frameon=True, facecolor="#fdfdfd")
            ax.grid(True, axis="y")
            plt.tight_layout()

            out_file = out_dir / f"latency_{scope}_bar.png"
            fig.savefig(out_file, dpi=300)
            plt.close(fig)


def plot_goodput_bar(df_proto: pd.DataFrame, proto_name: str, out_dir: Path,
                     compare_mode: bool = False, label1: str = "Primary", label2: str = "Comparison"):
    """
    Generate bar chart for Goodput across time windows comparing Cumulative vs Independent or label1 vs label2.
    """
    subset = df_proto[df_proto["metric"] == "goodput"].sort_values(by=["start_time", "end_time"])
    if subset.empty:
        return

    proto_display = PROTOCOL_DISPLAY_NAMES.get(proto_name, proto_name)

    if not compare_mode:
        cum_data = subset[subset["scope"] == "cumulative"]
        ind_data = subset[subset["scope"] == "independent"]
        all_windows = list(dict.fromkeys(list(cum_data["window_label"]) + list(ind_data["window_label"])))

        fig, ax = plt.subplots(figsize=(8.5, 5))
        x = np.arange(len(all_windows))
        width = 0.35

        cum_means = [cum_data[cum_data["window_label"] == w]["mean"].values[0] if not cum_data[cum_data["window_label"] == w].empty else 0.0 for w in all_windows]
        cum_rads = [cum_data[cum_data["window_label"] == w]["radius"].values[0] if not cum_data[cum_data["window_label"] == w].empty else 0.0 for w in all_windows]
        ind_means = [ind_data[ind_data["window_label"] == w]["mean"].values[0] if not ind_data[ind_data["window_label"] == w].empty else 0.0 for w in all_windows]
        ind_rads = [ind_data[ind_data["window_label"] == w]["radius"].values[0] if not ind_data[ind_data["window_label"] == w].empty else 0.0 for w in all_windows]

        rects1 = ax.bar(x - width/2, cum_means, width, yerr=cum_rads, capsize=3, label="Cumulative", color="#3498db", edgecolor="#222222", linewidth=0.6)
        rects2 = ax.bar(x + width/2, ind_means, width, yerr=ind_rads, capsize=3, label="Independent", color="#2ecc71", edgecolor="#222222", linewidth=0.6)

        for rects in [rects1, rects2]:
            for rect in rects:
                h = rect.get_height()
                if h > 0:
                    ax.annotate(f"{h:.1f}",
                                xy=(rect.get_x() + rect.get_width() / 2, h),
                                xytext=(0, 3), textcoords="offset points",
                                ha="center", va="bottom", fontsize=8)

        ax.set_title(f"{proto_display} - Goodput vs Time Window")
        ax.legend(frameon=True, facecolor="#fdfdfd")
    else:
        ind_data = subset[subset["scope"] == "independent"]
        if ind_data.empty:
            ind_data = subset[subset["scope"] == "cumulative"]
        all_windows = ind_data.sort_values(by=["start_time", "end_time"])["window_label"].unique()

        fig, ax = plt.subplots(figsize=(8.5, 5))
        x = np.arange(len(all_windows))
        width = 0.35

        d1_data = ind_data[ind_data["dataset"] == label1]
        d2_data = ind_data[ind_data["dataset"] == label2]

        d1_means = [d1_data[d1_data["window_label"] == w]["mean"].values[0] if not d1_data[d1_data["window_label"] == w].empty else 0.0 for w in all_windows]
        d1_rads = [d1_data[d1_data["window_label"] == w]["radius"].values[0] if not d1_data[d1_data["window_label"] == w].empty else 0.0 for w in all_windows]
        d2_means = [d2_data[d2_data["window_label"] == w]["mean"].values[0] if not d2_data[d2_data["window_label"] == w].empty else 0.0 for w in all_windows]
        d2_rads = [d2_data[d2_data["window_label"] == w]["radius"].values[0] if not d2_data[d2_data["window_label"] == w].empty else 0.0 for w in all_windows]

        ax.bar(x - width/2, d1_means, width, yerr=d1_rads, capsize=3, label=label1, color="#3498db", edgecolor="#222222", linewidth=0.6)
        ax.bar(x + width/2, d2_means, width, yerr=d2_rads, capsize=3, label=label2, color="#3498db", alpha=0.55, hatch="//", edgecolor="#222222", linewidth=0.6)

        ax.set_title(f"{proto_display} - Goodput Comparison ({label1} vs {label2})")
        ax.legend(frameon=True, facecolor="#fdfdfd")

    ax.set_xlabel("Time Window (s)")
    ax.set_ylabel("Goodput (Bits/s)")
    ax.set_xticks(x)
    ax.set_xticklabels(all_windows)
    ax.grid(True, axis="y")
    plt.tight_layout()

    out_file = out_dir / "goodput_bar.png"
    fig.savefig(out_file, dpi=300)
    plt.close(fig)


def plot_integrity_bar(df_proto: pd.DataFrame, proto_name: str, out_dir: Path,
                       compare_mode: bool = False, label1: str = "Primary", label2: str = "Comparison"):
    """
    Generate bar charts for System Integrity across time windows.
    """
    subset = df_proto[df_proto["metric"] == "integrity"].sort_values(by=["start_time", "end_time"])
    if subset.empty:
        return

    proto_display = PROTOCOL_DISPLAY_NAMES.get(proto_name, proto_name)

    # System Integrity
    sys_subset = subset[subset["target"] == "system"]
    if not sys_subset.empty:
        fig, ax = plt.subplots(figsize=(8, 4.8))
        if not compare_mode:
            cum_data = sys_subset[sys_subset["scope"] == "cumulative"]
            ind_data = sys_subset[sys_subset["scope"] == "independent"]
            windows = list(dict.fromkeys(list(cum_data["window_label"]) + list(ind_data["window_label"])))
            x = np.arange(len(windows))
            width = 0.35

            cum_means = [cum_data[cum_data["window_label"] == w]["mean"].values[0] if not cum_data[cum_data["window_label"] == w].empty else 0.0 for w in windows]
            cum_rads = [cum_data[cum_data["window_label"] == w]["radius"].values[0] if not cum_data[cum_data["window_label"] == w].empty else 0.0 for w in windows]
            ind_means = [ind_data[ind_data["window_label"] == w]["mean"].values[0] if not ind_data[ind_data["window_label"] == w].empty else 0.0 for w in windows]
            ind_rads = [ind_data[ind_data["window_label"] == w]["radius"].values[0] if not ind_data[ind_data["window_label"] == w].empty else 0.0 for w in windows]

            ax.bar(x - width/2, cum_means, width, yerr=cum_rads, capsize=3, label="Cumulative", color="#34495e", edgecolor="#222222", linewidth=0.6)
            ax.bar(x + width/2, ind_means, width, yerr=ind_rads, capsize=3, label="Independent", color="#9b59b6", edgecolor="#222222", linewidth=0.6)
            ax.set_title(f"{proto_display} - System Integrity vs Time Window")
        else:
            ind_data = sys_subset[sys_subset["scope"] == "independent"]
            if ind_data.empty:
                ind_data = sys_subset[sys_subset["scope"] == "cumulative"]
            windows = ind_data.sort_values(by=["start_time", "end_time"])["window_label"].unique()
            x = np.arange(len(windows))
            width = 0.35

            d1_data = ind_data[ind_data["dataset"] == label1]
            d2_data = ind_data[ind_data["dataset"] == label2]

            d1_means = [d1_data[d1_data["window_label"] == w]["mean"].values[0] if not d1_data[d1_data["window_label"] == w].empty else 0.0 for w in windows]
            d1_rads = [d1_data[d1_data["window_label"] == w]["radius"].values[0] if not d1_data[d1_data["window_label"] == w].empty else 0.0 for w in windows]
            d2_means = [d2_data[d2_data["window_label"] == w]["mean"].values[0] if not d2_data[d2_data["window_label"] == w].empty else 0.0 for w in windows]
            d2_rads = [d2_data[d2_data["window_label"] == w]["radius"].values[0] if not d2_data[d2_data["window_label"] == w].empty else 0.0 for w in windows]

            ax.bar(x - width/2, d1_means, width, yerr=d1_rads, capsize=3, label=label1, color="#9b59b6", edgecolor="#222222", linewidth=0.6)
            ax.bar(x + width/2, d2_means, width, yerr=d2_rads, capsize=3, label=label2, color="#9b59b6", alpha=0.55, hatch="//", edgecolor="#222222", linewidth=0.6)
            ax.set_title(f"{proto_display} - System Integrity Comparison ({label1} vs {label2})")

        ax.set_ylim(0, 1.15)
        ax.set_xlabel("Time Window (s)")
        ax.set_ylabel("Integrity Ratio (0.0 - 1.0)")
        ax.set_xticks(x)
        ax.set_xticklabels(windows)
        ax.legend(frameon=True, facecolor="#fdfdfd")
        ax.grid(True, axis="y")
        plt.tight_layout()

        fig.savefig(out_dir / "system_integrity_bar.png", dpi=300)
        plt.close(fig)


def plot_availability_bar(df_proto: pd.DataFrame, proto_name: str, out_dir: Path,
                          compare_mode: bool = False, label1: str = "Primary", label2: str = "Comparison"):
    """
    Generate bar chart for Availability (MTBF) across time windows.
    """
    subset = df_proto[df_proto["metric"] == "availability"].sort_values(by=["start_time", "end_time"])
    if subset.empty:
        return

    proto_display = PROTOCOL_DISPLAY_NAMES.get(proto_name, proto_name)

    fig, ax = plt.subplots(figsize=(8, 4.8))
    if not compare_mode:
        cum_data = subset[subset["scope"] == "cumulative"]
        ind_data = subset[subset["scope"] == "independent"]
        windows = list(dict.fromkeys(list(cum_data["window_label"]) + list(ind_data["window_label"])))
        x = np.arange(len(windows))
        width = 0.35

        cum_means = [cum_data[cum_data["window_label"] == w]["mean"].values[0] if not cum_data[cum_data["window_label"] == w].empty else 0.0 for w in windows]
        cum_rads = [cum_data[cum_data["window_label"] == w]["radius"].values[0] if not cum_data[cum_data["window_label"] == w].empty else 0.0 for w in windows]
        ind_means = [ind_data[ind_data["window_label"] == w]["mean"].values[0] if not ind_data[ind_data["window_label"] == w].empty else 0.0 for w in windows]
        ind_rads = [ind_data[ind_data["window_label"] == w]["radius"].values[0] if not ind_data[ind_data["window_label"] == w].empty else 0.0 for w in windows]

        ax.bar(x - width/2, cum_means, width, yerr=cum_rads, capsize=3, label="Cumulative", color="#e74c3c", edgecolor="#222222", linewidth=0.6)
        ax.bar(x + width/2, ind_means, width, yerr=ind_rads, capsize=3, label="Independent", color="#f39c12", edgecolor="#222222", linewidth=0.6)
        ax.set_title(f"{proto_display} - Availability (MTBF) vs Time Window")
    else:
        cum_data = subset[subset["scope"] == "cumulative"]
        if cum_data.empty:
            cum_data = subset[subset["scope"] == "independent"]
        windows = cum_data.sort_values(by=["start_time", "end_time"])["window_label"].unique()
        x = np.arange(len(windows))
        width = 0.35

        d1_data = cum_data[cum_data["dataset"] == label1]
        d2_data = cum_data[cum_data["dataset"] == label2]

        d1_means = [d1_data[d1_data["window_label"] == w]["mean"].values[0] if not d1_data[d1_data["window_label"] == w].empty else 0.0 for w in windows]
        d1_rads = [d1_data[d1_data["window_label"] == w]["radius"].values[0] if not d1_data[d1_data["window_label"] == w].empty else 0.0 for w in windows]
        d2_means = [d2_data[d2_data["window_label"] == w]["mean"].values[0] if not d2_data[d2_data["window_label"] == w].empty else 0.0 for w in windows]
        d2_rads = [d2_data[d2_data["window_label"] == w]["radius"].values[0] if not d2_data[d2_data["window_label"] == w].empty else 0.0 for w in windows]

        ax.bar(x - width/2, d1_means, width, yerr=d1_rads, capsize=3, label=label1, color="#e74c3c", edgecolor="#222222", linewidth=0.6)
        ax.bar(x + width/2, d2_means, width, yerr=d2_rads, capsize=3, label=label2, color="#e74c3c", alpha=0.55, hatch="//", edgecolor="#222222", linewidth=0.6)
        ax.set_title(f"{proto_display} - Availability (MTBF) Comparison ({label1} vs {label2})")

    ax.set_xlabel("Time Window (s)")
    ax.set_ylabel("MTBF (seconds)")
    ax.set_xticks(x)
    ax.set_xticklabels(windows)
    ax.legend(frameon=True, facecolor="#fdfdfd")
    ax.grid(True, axis="y")
    plt.tight_layout()

    fig.savefig(out_dir / "availability_bar.png", dpi=300)
    plt.close(fig)


def plot_individual_adversary_feature(df_proto: pd.DataFrame, proto_name: str, metric_key: str, out_dir: Path,
                                       compare_mode: bool = False, label1: str = "Primary", label2: str = "Comparison"):
    """
    Generate dedicated bar plot for a single adversary feature (e.g. incoming packet rate, outgoing packet rate, dns rate)
    comparing vantages across time windows for both independent and cumulative scopes.
    """
    sub = df_proto[(df_proto["metric"] == metric_key) & (df_proto["is_cusum"] == False)].sort_values(by=["start_time", "end_time"])
    if sub.empty:
        return

    m_info = METRIC_CONFIG.get(metric_key, {"name": metric_key, "unit": ""})
    m_name = m_info["name"]
    m_unit = m_info["unit"]
    proto_display = PROTOCOL_DISPLAY_NAMES.get(proto_name, proto_name)

    vantages = sorted(sub["target"].unique())
    vantage_colors = {"ixpN": "#e74c3c", "cl[5]": "#3498db"}

    fig, axes = plt.subplots(1, 2, figsize=(13, 5), sharey=True)

    for ax_idx, scope in enumerate(["independent", "cumulative"]):
        ax = axes[ax_idx]
        scope_sub = sub[sub["scope"] == scope]
        if scope_sub.empty:
            ax.set_title(f"{scope.capitalize()} (No data)")
            continue

        windows = scope_sub.sort_values(by=["start_time", "end_time"])["window_label"].unique()
        x = np.arange(len(windows))

        if not compare_mode:
            width = 0.35
            for i, v in enumerate(vantages):
                v_data = scope_sub[scope_sub["target"] == v]
                means = [v_data[v_data["window_label"] == w]["mean"].values[0] if not v_data[v_data["window_label"] == w].empty else 0.0 for w in windows]
                rads = [v_data[v_data["window_label"] == w]["radius"].values[0] if not v_data[v_data["window_label"] == w].empty else 0.0 for w in windows]

                v_label = VANTAGE_NAMES.get(v, v)
                color = vantage_colors.get(v, plt.cm.tab10(i))

                offset = (i - 0.5) * width
                rects = ax.bar(x + offset, means, width, yerr=rads, capsize=3, label=v_label, color=color, edgecolor="#222222", linewidth=0.6, alpha=0.9)

                for rect in rects:
                    h = rect.get_height()
                    if h > 0.01:
                        ax.annotate(f"{h:.2f}",
                                    xy=(rect.get_x() + rect.get_width() / 2, h),
                                    xytext=(0, 3), textcoords="offset points",
                                    ha="center", va="bottom", fontsize=8)

            ax.legend(title="Vantage Point", frameon=True, facecolor="#fdfdfd")
        else:
            n_vantages = len(vantages)
            group_spacing = 0.7 / max(n_vantages, 1)
            bar_w = group_spacing * 0.42

            for i, v in enumerate(vantages):
                v_sub = scope_sub[scope_sub["target"] == v]
                v_color = vantage_colors.get(v, plt.cm.tab10(i))
                v_center = (i - (n_vantages - 1) / 2) * group_spacing

                for j, dset in enumerate([label1, label2]):
                    d_sub = v_sub[v_sub["dataset"] == dset]
                    means = [d_sub[d_sub["window_label"] == w]["mean"].values[0] if not d_sub[d_sub["window_label"] == w].empty else 0.0 for w in windows]
                    rads = [d_sub[d_sub["window_label"] == w]["radius"].values[0] if not d_sub[d_sub["window_label"] == w].empty else 0.0 for w in windows]

                    bar_offset = v_center + (j - 0.5) * bar_w
                    hatch = None if j == 0 else "//"
                    alpha = 0.9 if j == 0 else 0.55

                    v_name = VANTAGE_NAMES.get(v, v)
                    ax.bar(x + bar_offset, means, bar_w, yerr=rads, capsize=2,
                           color=v_color, alpha=alpha, hatch=hatch, edgecolor="#222222", linewidth=0.6,
                           label=f"{v_name} ({dset})" if ax_idx == 0 else "")

            if ax_idx == 0:
                ax.legend(frameon=True, facecolor="#fdfdfd", fontsize=8)

        ax.set_title(f"{scope.capitalize()} Windows")
        ax.set_xlabel("Time Window (s)")
        if ax_idx == 0:
            ax.set_ylabel(f"{m_name} ({m_unit})")
        ax.set_xticks(x)
        ax.set_xticklabels(windows)
        ax.grid(True, axis="y")

    title_str = f"{proto_display} - {m_name} vs Time Window"
    if compare_mode:
        title_str += f" ({label1} vs {label2})"
    fig.suptitle(title_str, fontsize=13, weight="bold")
    plt.tight_layout()

    out_file = out_dir / f"adversary_{metric_key}_bar.png"
    fig.savefig(out_file, dpi=300)
    plt.close(fig)


def plot_protocol_cusum_cumulative_features(df_proto: pd.DataFrame, proto_name: str, out_dir: Path,
                                             compare_mode: bool = False, label1: str = "Primary", label2: str = "Comparison"):
    """
    Generate dedicated figure per protocol comparing cumulative CUSUM Z(t) scores
    across cumulative time windows on the X-axis for each traffic feature.
    """
    cusum_sub = df_proto[(df_proto["is_cusum"] == True) & (df_proto["scope"] == "cumulative")].copy()
    if cusum_sub.empty:
        return

    proto_display = PROTOCOL_DISPLAY_NAMES.get(proto_name, proto_name)
    base_color = PROTOCOL_COLORS.get(proto_name, "#3498db")

    feature_keys = [
        "dns_query_rate",
        "tcp_outgoing_packet_rate",
        "tcp_incoming_packet_rate",
        "packet_size_mean",
        "packet_interarrival_mean"
    ]

    feature_titles = {
        "dns_query_rate": "DNS Query Rate",
        "tcp_outgoing_packet_rate": "TCP Outgoing Packet Rate",
        "tcp_incoming_packet_rate": "TCP Incoming Packet Rate",
        "packet_size_mean": "Mean Packet Size",
        "packet_interarrival_mean": "Mean Packet Inter-arrival",
    }

    cum_windows = ["[10-910]s", "[10-1810]s", "[10-2710]s", "[10-3610]s"]
    x = np.arange(len(cum_windows))

    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    axes_flat = axes.flatten()

    for idx, fk in enumerate(feature_keys):
        ax = axes_flat[idx]
        feat_sub = cusum_sub[cusum_sub["metric"] == fk]

        if not compare_mode:
            width = 0.5
            means, rads = [], []
            for w in cum_windows:
                w_match = feat_sub[feat_sub["window_label"] == w]
                means.append(w_match["mean"].values[0] if not w_match.empty else 0.0)
                rads.append(w_match["radius"].values[0] if not w_match.empty else 0.0)

            rects = ax.bar(x, means, width, yerr=rads, capsize=3, color=base_color, edgecolor="#222222", linewidth=0.6, alpha=0.9)
            for rect in rects:
                h = rect.get_height()
                if h > 0.0001:
                    ax.annotate(f"{h:.3f}",
                                xy=(rect.get_x() + rect.get_width() / 2, h),
                                xytext=(0, 3), textcoords="offset points",
                                ha="center", va="bottom", fontsize=8.5, fontweight="semibold")
        else:
            width = 0.35
            d1_means, d1_rads = [], []
            d2_means, d2_rads = [], []

            for w in cum_windows:
                d1_match = feat_sub[(feat_sub["window_label"] == w) & (feat_sub["dataset"] == label1)]
                d2_match = feat_sub[(feat_sub["window_label"] == w) & (feat_sub["dataset"] == label2)]

                d1_means.append(d1_match["mean"].values[0] if not d1_match.empty else 0.0)
                d1_rads.append(d1_match["radius"].values[0] if not d1_match.empty else 0.0)

                d2_means.append(d2_match["mean"].values[0] if not d2_match.empty else 0.0)
                d2_rads.append(d2_match["radius"].values[0] if not d2_match.empty else 0.0)

            rects1 = ax.bar(x - width/2, d1_means, width, yerr=d1_rads, capsize=2.5,
                            label=label1, color=base_color, edgecolor="#222222", linewidth=0.6, alpha=0.9)
            rects2 = ax.bar(x + width/2, d2_means, width, yerr=d2_rads, capsize=2.5,
                            label=label2, color=base_color, alpha=0.55, hatch="//", edgecolor="#222222", linewidth=0.6)

            for rect in rects1:
                h = rect.get_height()
                if h > 0.0001:
                    ax.annotate(f"{h:.2f}",
                                xy=(rect.get_x() + rect.get_width() / 2, h),
                                xytext=(0, 2), textcoords="offset points",
                                ha="center", va="bottom", fontsize=7.5)

            for rect in rects2:
                h = rect.get_height()
                if h > 0.0001:
                    ax.annotate(f"{h:.2f}",
                                xy=(rect.get_x() + rect.get_width() / 2, h),
                                xytext=(0, 2), textcoords="offset points",
                                ha="center", va="bottom", fontsize=7.5)

            if idx == 0:
                ax.legend(frameon=True, facecolor="#fdfdfd", fontsize=9)

        ax.set_title(feature_titles.get(fk, fk), fontsize=11, fontweight="bold")
        ax.set_xlabel("Time Window (s)", fontsize=10)
        ax.set_ylabel("CUSUM Z(t)", fontsize=10)
        ax.set_xticks(x)
        ax.set_xticklabels(cum_windows, fontsize=9)
        ax.grid(True, axis="y")

    # Panel 6 (index 5): Combined comparison at final window [10-3610]s across all features
    ax6 = axes_flat[5]
    final_win = "[10-3610]s"
    final_sub = cusum_sub[cusum_sub["window_label"] == final_win]
    fx = np.arange(len(feature_keys))
    feature_short_labels = ["DNS Rate", "TCP Out", "TCP In", "Pkt Size", "Inter-arr"]

    if not compare_mode:
        f_means = [final_sub[final_sub["metric"] == fk]["mean"].values[0] if not final_sub[final_sub["metric"] == fk].empty else 0.0 for fk in feature_keys]
        f_rads = [final_sub[final_sub["metric"] == fk]["radius"].values[0] if not final_sub[final_sub["metric"] == fk].empty else 0.0 for fk in feature_keys]
        rects = ax6.bar(fx, f_means, 0.5, yerr=f_rads, capsize=2.5, color=base_color, edgecolor="#222222", linewidth=0.6, alpha=0.9)
        for rect in rects:
            h = rect.get_height()
            if h > 0.0001:
                ax6.annotate(f"{h:.2f}", xy=(rect.get_x() + rect.get_width()/2, h), xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=7.5)
    else:
        d1_f_means = [final_sub[(final_sub["metric"] == fk) & (final_sub["dataset"] == label1)]["mean"].values[0] if not final_sub[(final_sub["metric"] == fk) & (final_sub["dataset"] == label1)].empty else 0.0 for fk in feature_keys]
        d1_f_rads = [final_sub[(final_sub["metric"] == fk) & (final_sub["dataset"] == label1)]["radius"].values[0] if not final_sub[(final_sub["metric"] == fk) & (final_sub["dataset"] == label1)].empty else 0.0 for fk in feature_keys]
        d2_f_means = [final_sub[(final_sub["metric"] == fk) & (final_sub["dataset"] == label2)]["mean"].values[0] if not final_sub[(final_sub["metric"] == fk) & (final_sub["dataset"] == label2)].empty else 0.0 for fk in feature_keys]
        d2_f_rads = [final_sub[(final_sub["metric"] == fk) & (final_sub["dataset"] == label2)]["radius"].values[0] if not final_sub[(final_sub["metric"] == fk) & (final_sub["dataset"] == label2)].empty else 0.0 for fk in feature_keys]

        rects1 = ax6.bar(fx - 0.18, d1_f_means, 0.35, yerr=d1_f_rads, capsize=2, label=label1, color=base_color, edgecolor="#222222", linewidth=0.6, alpha=0.9)
        rects2 = ax6.bar(fx + 0.18, d2_f_means, 0.35, yerr=d2_f_rads, capsize=2, label=label2, color=base_color, alpha=0.55, hatch="//", edgecolor="#222222", linewidth=0.6)

        for rect in rects1:
            h = rect.get_height()
            if h > 0.0001:
                ax6.annotate(f"{h:.2f}", xy=(rect.get_x() + rect.get_width()/2, h), xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=7)
        for rect in rects2:
            h = rect.get_height()
            if h > 0.0001:
                ax6.annotate(f"{h:.2f}", xy=(rect.get_x() + rect.get_width()/2, h), xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=7)

    ax6.set_title(f"All Features at {final_win}", fontsize=11, fontweight="bold")
    ax6.set_xticks(fx)
    ax6.set_xticklabels(feature_short_labels, rotation=15, ha="right", fontsize=8.5)
    ax6.set_ylabel("CUSUM Z(t)", fontsize=10)
    ax6.grid(True, axis="y")

    title_str = f"{proto_display} - Cumulative CUSUM Z(t) Scores vs Time Window"
    if compare_mode:
        title_str += f" ({label1} vs {label2})"

    fig.suptitle(title_str, fontsize=14, weight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])

    fig.savefig(out_dir / f"cusum_cumulative_features_{proto_name}.png", dpi=300)
    if out_dir.name != "comparison_plots":
        fig.savefig(out_dir / "cusum_cumulative_features.png", dpi=300)
    plt.close(fig)


def plot_hcs_tgen_performance_summary(df_proto: pd.DataFrame, proto_name: str, out_dir: Path, label1: str = "HCS+TGen"):
    """
    Generate a 2x2 multi-panel figure for a protocol showing mean latencies (p25, p50, p75, p100),
    goodput, system integrity, and availability strictly for HCS+TGen data.
    """
    proto_display = PROTOCOL_DISPLAY_NAMES.get(proto_name, proto_name)

    # Filter for HCS+TGen dataset
    hcs_df = df_proto[df_proto["dataset"] == label1].copy()
    if hcs_df.empty:
        avail_dsets = df_proto["dataset"].unique()
        if len(avail_dsets) > 0:
            hcs_df = df_proto[df_proto["dataset"] == avail_dsets[0]].copy()
        else:
            return

    fig, axes = plt.subplots(2, 2, figsize=(14, 9.5))

    # Panel 1: Latency Percentiles (p25, p50, p75, p100)
    ax1 = axes[0, 0]
    lat_sub = hcs_df[hcs_df["metric"].isin(["latency25", "latency50", "latency75", "latency100"]) & (hcs_df["scope"] == "cumulative")]
    if lat_sub.empty:
        lat_sub = hcs_df[hcs_df["metric"].isin(["latency25", "latency50", "latency75", "latency100"]) & (hcs_df["scope"] == "independent")]

    if not lat_sub.empty:
        cum_windows = lat_sub.sort_values(by=["start_time", "end_time"])["window_label"].unique()
        x = np.arange(len(cum_windows))
        lat_metrics = [("latency25", "p25", "#aed6f1"),
                       ("latency50", "p50", "#5DADE2"),
                       ("latency75", "p75", "#2874A6"),
                       ("latency100", "p100", "#1B4F72")]

        width = 0.18
        for j, (m_key, m_lbl, m_col) in enumerate(lat_metrics):
            m_data = lat_sub[lat_sub["metric"] == m_key]
            means = [m_data[m_data["window_label"] == w]["mean"].values[0] if not m_data[m_data["window_label"] == w].empty else 0.0 for w in cum_windows]
            rads = [m_data[m_data["window_label"] == w]["radius"].values[0] if not m_data[m_data["window_label"] == w].empty else 0.0 for w in cum_windows]

            offset = (j - 1.5) * width
            rects = ax1.bar(x + offset, means, width, yerr=rads, capsize=2, label=m_lbl, color=m_col, edgecolor="#222222", linewidth=0.5)

            for rect in rects:
                h = rect.get_height()
                if h > 0.001:
                    ax1.annotate(f"{h:.2f}",
                                 xy=(rect.get_x() + rect.get_width() / 2, h),
                                 xytext=(0, 2), textcoords="offset points",
                                 ha="center", va="bottom", fontsize=7.5)

        ax1.set_xticks(x)
        ax1.set_xticklabels(cum_windows, fontsize=9)
        ax1.legend(title="Percentile", frameon=True, facecolor="#fdfdfd", fontsize=8.5)
    else:
        ax1.text(0.5, 0.5, "No Latency Data", ha="center", va="center")

    ax1.set_title("Mean Latencies (p25, p50, p75, p100) [Log Scale]", fontsize=11, fontweight="bold")
    ax1.set_xlabel("Time Window (s)", fontsize=10)
    ax1.set_ylabel("Latency (s)", fontsize=10)
    ax1.set_yscale("log")
    ax1.grid(True, axis="y")

    # Panel 2: Goodput
    ax2 = axes[0, 1]
    gp_sub = hcs_df[hcs_df["metric"] == "goodput"].sort_values(by=["start_time", "end_time"])
    if not gp_sub.empty:
        cum_gp = gp_sub[gp_sub["scope"] == "cumulative"]
        ind_gp = gp_sub[gp_sub["scope"] == "independent"]
        windows = list(dict.fromkeys(list(cum_gp["window_label"]) + list(ind_gp["window_label"])))
        x2 = np.arange(len(windows))
        width2 = 0.35

        cum_means = [cum_gp[cum_gp["window_label"] == w]["mean"].values[0] if not cum_gp[cum_gp["window_label"] == w].empty else 0.0 for w in windows]
        cum_rads = [cum_gp[cum_gp["window_label"] == w]["radius"].values[0] if not cum_gp[cum_gp["window_label"] == w].empty else 0.0 for w in windows]
        ind_means = [ind_gp[ind_gp["window_label"] == w]["mean"].values[0] if not ind_gp[ind_gp["window_label"] == w].empty else 0.0 for w in windows]
        ind_rads = [ind_gp[ind_gp["window_label"] == w]["radius"].values[0] if not ind_gp[ind_gp["window_label"] == w].empty else 0.0 for w in windows]

        rects_c = ax2.bar(x2 - width2/2, cum_means, width2, yerr=cum_rads, capsize=2.5, label="Cumulative", color="#2ecc71", edgecolor="#222222", linewidth=0.5)
        rects_i = ax2.bar(x2 + width2/2, ind_means, width2, yerr=ind_rads, capsize=2.5, label="Independent", color="#27ae60", alpha=0.6, hatch="//", edgecolor="#222222", linewidth=0.5)

        for rect in list(rects_c) + list(rects_i):
            h = rect.get_height()
            if h > 0.01:
                ax2.annotate(f"{h:.1f}", xy=(rect.get_x() + rect.get_width()/2, h), xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=7.5)

        ax2.set_xticks(x2)
        ax2.set_xticklabels(windows, fontsize=9)
        ax2.legend(frameon=True, facecolor="#fdfdfd", fontsize=8.5)
    else:
        ax2.text(0.5, 0.5, "No Goodput Data", ha="center", va="center")

    ax2.set_title("Goodput", fontsize=11, fontweight="bold")
    ax2.set_xlabel("Time Window (s)", fontsize=10)
    ax2.set_ylabel("Goodput (Bits/s)", fontsize=10)
    ax2.grid(True, axis="y")

    # Panel 3: System Integrity
    ax3 = axes[1, 0]
    int_sub = hcs_df[(hcs_df["metric"] == "integrity") & (hcs_df["target"] == "system")].sort_values(by=["start_time", "end_time"])
    if not int_sub.empty:
        cum_int = int_sub[int_sub["scope"] == "cumulative"]
        ind_int = int_sub[int_sub["scope"] == "independent"]
        windows = list(dict.fromkeys(list(cum_int["window_label"]) + list(ind_int["window_label"])))
        x3 = np.arange(len(windows))
        width3 = 0.35

        cum_means = [cum_int[cum_int["window_label"] == w]["mean"].values[0] if not cum_int[cum_int["window_label"] == w].empty else 0.0 for w in windows]
        cum_rads = [cum_int[cum_int["window_label"] == w]["radius"].values[0] if not cum_int[cum_int["window_label"] == w].empty else 0.0 for w in windows]
        ind_means = [ind_int[ind_int["window_label"] == w]["mean"].values[0] if not ind_int[ind_int["window_label"] == w].empty else 0.0 for w in windows]
        ind_rads = [ind_int[ind_int["window_label"] == w]["radius"].values[0] if not ind_int[ind_int["window_label"] == w].empty else 0.0 for w in windows]

        rects_c = ax3.bar(x3 - width3/2, cum_means, width3, yerr=cum_rads, capsize=2.5, label="Cumulative", color="#9b59b6", edgecolor="#222222", linewidth=0.5)
        rects_i = ax3.bar(x3 + width3/2, ind_means, width3, yerr=ind_rads, capsize=2.5, label="Independent", color="#8e44ad", alpha=0.6, hatch="//", edgecolor="#222222", linewidth=0.5)

        for rect in list(rects_c) + list(rects_i):
            h = rect.get_height()
            if h > 0.01:
                ax3.annotate(f"{h:.2f}", xy=(rect.get_x() + rect.get_width()/2, h), xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=7.5)

        ax3.set_xticks(x3)
        ax3.set_xticklabels(windows, fontsize=9)
        ax3.set_ylim(0, 1.15)
        ax3.legend(frameon=True, facecolor="#fdfdfd", fontsize=8.5)
    else:
        ax3.text(0.5, 0.5, "No Integrity Data", ha="center", va="center")

    ax3.set_title("System Integrity", fontsize=11, fontweight="bold")
    ax3.set_xlabel("Time Window (s)", fontsize=10)
    ax3.set_ylabel("Integrity Ratio [0-1]", fontsize=10)
    ax3.grid(True, axis="y")

    # Panel 4: Availability (MTBF)
    ax4 = axes[1, 1]
    avail_sub = hcs_df[hcs_df["metric"] == "availability"].sort_values(by=["start_time", "end_time"])
    if not avail_sub.empty:
        cum_av = avail_sub[avail_sub["scope"] == "cumulative"]
        ind_av = avail_sub[avail_sub["scope"] == "independent"]
        windows = list(dict.fromkeys(list(cum_av["window_label"]) + list(ind_av["window_label"])))
        x4 = np.arange(len(windows))
        width4 = 0.35

        cum_means = [cum_av[cum_av["window_label"] == w]["mean"].values[0] if not cum_av[cum_av["window_label"] == w].empty else 0.0 for w in windows]
        cum_rads = [cum_av[cum_av["window_label"] == w]["radius"].values[0] if not cum_av[cum_av["window_label"] == w].empty else 0.0 for w in windows]
        ind_means = [ind_av[ind_av["window_label"] == w]["mean"].values[0] if not ind_av[ind_av["window_label"] == w].empty else 0.0 for w in windows]
        ind_rads = [ind_av[ind_av["window_label"] == w]["radius"].values[0] if not ind_av[ind_av["window_label"] == w].empty else 0.0 for w in windows]

        rects_c = ax4.bar(x4 - width4/2, cum_means, width4, yerr=cum_rads, capsize=2.5, label="Cumulative", color="#e74c3c", edgecolor="#222222", linewidth=0.5)
        rects_i = ax4.bar(x4 + width4/2, ind_means, width4, yerr=ind_rads, capsize=2.5, label="Independent", color="#c0392b", alpha=0.6, hatch="//", edgecolor="#222222", linewidth=0.5)

        for rect in list(rects_c) + list(rects_i):
            h = rect.get_height()
            if h > 0.01:
                ax4.annotate(f"{h:.1f}", xy=(rect.get_x() + rect.get_width()/2, h), xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=7.5)

        ax4.set_xticks(x4)
        ax4.set_xticklabels(windows, fontsize=9)
        ax4.legend(frameon=True, facecolor="#fdfdfd", fontsize=8.5)
    else:
        ax4.text(0.5, 0.5, "No Availability Data", ha="center", va="center")

    ax4.set_title("Availability (MTBF)", fontsize=11, fontweight="bold")
    ax4.set_xlabel("Time Window (s)", fontsize=10)
    ax4.set_ylabel("MTBF (seconds)", fontsize=10)
    ax4.grid(True, axis="y")

    fig.suptitle(f"{proto_display} - Performance & Dependability Summary ({label1})", fontsize=14, weight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])

    fig.savefig(out_dir / f"hcs_tgen_performance_summary_{proto_name}.png", dpi=300)
    if out_dir.name != "comparison_plots":
        fig.savefig(out_dir / "hcs_tgen_performance_summary.png", dpi=300)
    plt.close(fig)


def plot_all_protocol_metrics_dashboard(df_proto: pd.DataFrame, proto_name: str, out_dir: Path,
                                         compare_mode: bool = False, label1: str = "Primary", label2: str = "Comparison"):
    """
    Generate a 2x4 comprehensive multi-panel dashboard of all core metrics for a protocol.
    """
    proto_display = PROTOCOL_DISPLAY_NAMES.get(proto_name, proto_name)
    fig, axes = plt.subplots(2, 4, figsize=(18, 9))
    title_str = f"{proto_display} - Complete Metrics Dashboard (Independent Windows)"
    if compare_mode:
        title_str += f" ({label1} vs {label2})"
    fig.suptitle(title_str, fontsize=16, weight="bold")

    plot_specs = [
        {"metric": "latency50", "title": "Median Latency (p50)", "ylabel": "Seconds (s)", "color": "#3498db"},
        {"metric": "goodput", "title": "Goodput", "ylabel": "Bits/s", "color": "#2ecc71"},
        {"metric": "integrity", "target": "system", "title": "System Integrity", "ylabel": "Ratio [0-1]", "color": "#9b59b6"},
        {"metric": "availability", "title": "Availability (MTBF)", "ylabel": "Seconds (s)", "color": "#e74c3c"},
        {"metric": "dns_query_rate", "title": "DNS Query Rate (ixpN)", "target": "ixpN", "ylabel": "Queries/s", "color": "#f39c12"},
        {"metric": "tcp_incoming_packet_rate", "title": "Incoming Packet Rate (ixpN)", "target": "ixpN", "ylabel": "Pkts/s", "color": "#1abc9c"},
        {"metric": "tcp_outgoing_packet_rate", "title": "Outgoing Packet Rate (ixpN)", "target": "ixpN", "ylabel": "Pkts/s", "color": "#e67e22"},
        {"metric": "packet_size_mean", "title": "Mean Packet Size (ixpN)", "target": "ixpN", "ylabel": "Bytes", "color": "#34495e"},
    ]

    for idx, spec in enumerate(plot_specs):
        row, col = divmod(idx, 4)
        ax = axes[row, col]

        m = spec["metric"]
        target = spec.get("target")
        query_str = f"(metric == '{m}') & (scope == 'independent')"
        if target:
            query_str += f" & (target == '{target}')"

        sub = df_proto.query(query_str).sort_values(by=["start_time", "end_time"])
        if sub.empty:
            query_str_cum = query_str.replace("scope == 'independent'", "scope == 'cumulative'")
            sub = df_proto.query(query_str_cum).sort_values(by=["start_time", "end_time"])

        if not sub.empty:
            windows = sub.sort_values(by=["start_time", "end_time"])["window_label"].unique()
            x = np.arange(len(windows))

            if not compare_mode:
                means = sub["mean"].values
                rads = sub["radius"].values
                rects = ax.bar(x, means, 0.45, yerr=rads, capsize=3, color=spec["color"], edgecolor="#222222", linewidth=0.6)
                ax.set_xticks(x)
                ax.set_xticklabels(windows, rotation=25)
                for rect in rects:
                    h = rect.get_height()
                    if h > 0.01:
                        ax.annotate(f"{h:.1f}",
                                    xy=(rect.get_x() + rect.get_width() / 2, h),
                                    xytext=(0, 2), textcoords="offset points",
                                    ha="center", va="bottom", fontsize=7.5)
            else:
                width = 0.38
                for j, dset in enumerate([label1, label2]):
                    d_sub = sub[sub["dataset"] == dset]
                    means = [d_sub[d_sub["window_label"] == w]["mean"].values[0] if not d_sub[d_sub["window_label"] == w].empty else 0.0 for w in windows]
                    rads = [d_sub[d_sub["window_label"] == w]["radius"].values[0] if not d_sub[d_sub["window_label"] == w].empty else 0.0 for w in windows]

                    offset = (j - 0.5) * width
                    hatch = None if j == 0 else "//"
                    alpha = 1.0 if j == 0 else 0.55

                    ax.bar(x + offset, means, width, yerr=rads, capsize=2,
                           color=spec["color"], alpha=alpha, hatch=hatch, edgecolor="#222222", linewidth=0.6,
                           label=dset if idx == 0 else "")

                ax.set_xticks(x)
                ax.set_xticklabels(windows, rotation=25)
        else:
            ax.text(0.5, 0.5, "No Data", ha="center", va="center")

        ax.set_title(spec["title"])
        ax.set_ylabel(spec["ylabel"])
        ax.grid(True, axis="y")

    if compare_mode:
        axes[0, 0].legend(frameon=True, facecolor="#fdfdfd", fontsize=8)

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    fig.savefig(out_dir / "protocol_complete_metrics_dashboard.png", dpi=300)
    plt.close(fig)


# -----------------------------------------------------------------------------
# Cross-Protocol Comparison Plots
# -----------------------------------------------------------------------------
def plot_cross_protocol_comparisons(df_all: pd.DataFrame, out_dir: Path,
                                    compare_mode: bool = False, label1: str = "Primary", label2: str = "Comparison",
                                    testbed_data=None):
    """
    Generate comprehensive cross-protocol comparison bar plots for ALL metrics vs time windows.
    If compare_mode is True, plots side-by-side bars for label1 vs label2 for each protocol at each window.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    protocols = sorted(df_all["protocol"].unique())

    comparison_specs = [
        # Latency Percentiles
        {"metric": "latency50", "scope": "independent", "title": "Median Latency (p50) Comparison [Independent Windows]", "ylabel": "Latency (s)", "fname": "comparison_latency_p50_independent.png"},
        {"metric": "latency50", "scope": "cumulative", "title": "Median Latency (p50) Comparison [Cumulative Windows]", "ylabel": "Latency (s)", "fname": "comparison_latency_p50_cumulative.png"},
        {"metric": "latency25", "scope": "independent", "title": "25th Percentile Latency (p25) Comparison [Independent Windows]", "ylabel": "Latency (s)", "fname": "comparison_latency_p25_independent.png"},
        {"metric": "latency75", "scope": "independent", "title": "75th Percentile Latency (p75) Comparison [Independent Windows]", "ylabel": "Latency (s)", "fname": "comparison_latency_p75_independent.png"},
        {"metric": "latency100", "scope": "independent", "title": "Max Latency (p100) Comparison [Independent Windows]", "ylabel": "Latency (s)", "fname": "comparison_latency_p100_independent.png"},

        # Goodput
        {"metric": "goodput", "scope": "independent", "title": "Goodput Comparison [Independent Windows]", "ylabel": "Goodput (Bits/s)", "fname": "comparison_goodput_independent.png"},
        {"metric": "goodput", "scope": "cumulative", "title": "Goodput Comparison [Cumulative Windows]", "ylabel": "Goodput (Bits/s)", "fname": "comparison_goodput_cumulative.png"},

        # System Integrity
        {"metric": "integrity", "target": "system", "scope": "independent", "title": "System Integrity Comparison [Independent Windows]", "ylabel": "Integrity Ratio [0-1]", "fname": "comparison_system_integrity_independent.png"},
        {"metric": "integrity", "target": "system", "scope": "cumulative", "title": "System Integrity Comparison [Cumulative Windows]", "ylabel": "Integrity Ratio [0-1]", "fname": "comparison_system_integrity_cumulative.png"},

        # Availability
        {"metric": "availability", "scope": "cumulative", "title": "Availability (MTBF) Comparison [Cumulative Windows]", "ylabel": "MTBF (s)", "fname": "comparison_availability_cumulative.png"},
        {"metric": "availability", "scope": "independent", "title": "Availability (MTBF) Comparison [Independent Windows]", "ylabel": "MTBF (s)", "fname": "comparison_availability_independent.png"},

        # DNS Query Rate
        {"metric": "dns_query_rate", "target": "ixpN", "scope": "independent", "title": "DNS Query Rate at IXP (ixpN) Comparison [Independent Windows]", "ylabel": "Queries/s", "fname": "comparison_dns_query_rate_ixpN_independent.png"},
        {"metric": "dns_query_rate", "target": "ixpN", "scope": "cumulative", "title": "DNS Query Rate at IXP (ixpN) Comparison [Cumulative Windows]", "ylabel": "Queries/s", "fname": "comparison_dns_query_rate_ixpN_cumulative.png"},
        {"metric": "dns_query_rate", "target": "cl[5]", "scope": "independent", "title": "DNS Query Rate at Client Net (cl[5]) Comparison [Independent Windows]", "ylabel": "Queries/s", "fname": "comparison_dns_query_rate_cl5_independent.png"},
        {"metric": "dns_query_rate", "target": "cl[5]", "scope": "cumulative", "title": "DNS Query Rate at Client Net (cl[5]) Comparison [Cumulative Windows]", "ylabel": "Queries/s", "fname": "comparison_dns_query_rate_cl5_cumulative.png"},

        # TCP Incoming Packet Rate
        {"metric": "tcp_incoming_packet_rate", "target": "ixpN", "scope": "independent", "title": "TCP Incoming Packet Rate at IXP (ixpN) Comparison [Independent Windows]", "ylabel": "Pkts/s", "fname": "comparison_tcp_incoming_packet_rate_ixpN_independent.png"},
        {"metric": "tcp_incoming_packet_rate", "target": "ixpN", "scope": "cumulative", "title": "TCP Incoming Packet Rate at IXP (ixpN) Comparison [Cumulative Windows]", "ylabel": "Pkts/s", "fname": "comparison_tcp_incoming_packet_rate_ixpN_cumulative.png"},
        {"metric": "tcp_incoming_packet_rate", "target": "cl[5]", "scope": "independent", "title": "TCP Incoming Packet Rate at Client Net (cl[5]) Comparison [Independent Windows]", "ylabel": "Pkts/s", "fname": "comparison_tcp_incoming_packet_rate_cl5_independent.png"},
        {"metric": "tcp_incoming_packet_rate", "target": "cl[5]", "scope": "cumulative", "title": "TCP Incoming Packet Rate at Client Net (cl[5]) Comparison [Cumulative Windows]", "ylabel": "Pkts/s", "fname": "comparison_tcp_incoming_packet_rate_cl5_cumulative.png"},

        # TCP Outgoing Packet Rate
        {"metric": "tcp_outgoing_packet_rate", "target": "ixpN", "scope": "independent", "title": "TCP Outgoing Packet Rate at IXP (ixpN) Comparison [Independent Windows]", "ylabel": "Pkts/s", "fname": "comparison_tcp_outgoing_packet_rate_ixpN_independent.png"},
        {"metric": "tcp_outgoing_packet_rate", "target": "ixpN", "scope": "cumulative", "title": "TCP Outgoing Packet Rate at IXP (ixpN) Comparison [Cumulative Windows]", "ylabel": "Pkts/s", "fname": "comparison_tcp_outgoing_packet_rate_ixpN_cumulative.png"},
        {"metric": "tcp_outgoing_packet_rate", "target": "cl[5]", "scope": "independent", "title": "TCP Outgoing Packet Rate at Client Net (cl[5]) Comparison [Independent Windows]", "ylabel": "Pkts/s", "fname": "comparison_tcp_outgoing_packet_rate_cl5_independent.png"},
        {"metric": "tcp_outgoing_packet_rate", "target": "cl[5]", "scope": "cumulative", "title": "TCP Outgoing Packet Rate at Client Net (cl[5]) Comparison [Cumulative Windows]", "ylabel": "Pkts/s", "fname": "comparison_tcp_outgoing_packet_rate_cl5_cumulative.png"},

        # Mean Packet Size
        {"metric": "packet_size_mean", "target": "ixpN", "scope": "independent", "title": "Mean Packet Size at IXP (ixpN) Comparison [Independent Windows]", "ylabel": "Bytes", "fname": "comparison_packet_size_mean_ixpN_independent.png"},
        {"metric": "packet_size_mean", "target": "ixpN", "scope": "cumulative", "title": "Mean Packet Size at IXP (ixpN) Comparison [Cumulative Windows]", "ylabel": "Bytes", "fname": "comparison_packet_size_mean_ixpN_cumulative.png"},
        {"metric": "packet_size_mean", "target": "cl[5]", "scope": "independent", "title": "Mean Packet Size at Client Net (cl[5]) Comparison [Independent Windows]", "ylabel": "Bytes", "fname": "comparison_packet_size_mean_cl5_independent.png"},

        # Mean Packet Inter-arrival
        {"metric": "packet_interarrival_mean", "target": "ixpN", "scope": "independent", "title": "Mean Packet Inter-arrival at IXP (ixpN) Comparison [Independent Windows]", "ylabel": "Seconds (s)", "fname": "comparison_packet_interarrival_mean_ixpN_independent.png"},
        {"metric": "packet_interarrival_mean", "target": "ixpN", "scope": "cumulative", "title": "Mean Packet Inter-arrival at IXP (ixpN) Comparison [Cumulative Windows]", "ylabel": "Seconds (s)", "fname": "comparison_packet_interarrival_mean_ixpN_cumulative.png"},
        {"metric": "packet_interarrival_mean", "target": "cl[5]", "scope": "independent", "title": "Mean Packet Inter-arrival at Client Net (cl[5]) Comparison [Independent Windows]", "ylabel": "Seconds (s)", "fname": "comparison_packet_interarrival_mean_cl5_independent.png"},
    ]

    for spec in comparison_specs:
        m = spec["metric"]
        scope = spec["scope"]
        target = spec.get("target")

        query_str = f"(metric == '{m}') & (scope == '{scope}')"
        if target:
            query_str += f" & (target == '{target}')"

        sub = df_all.query(query_str).copy()
        if sub.empty:
            continue

        windows = sub.sort_values(by=["start_time", "end_time"])["window_label"].unique()
        fig, ax = plt.subplots(figsize=(11.5, 6))
        x = np.arange(len(windows))
        n_protos = len(protocols)

        if not compare_mode:
            width = 0.8 / max(n_protos, 1)
            for i, proto in enumerate(protocols):
                p_sub = sub[sub["protocol"] == proto]
                means = [p_sub[p_sub["window_label"] == w]["mean"].values[0] if not p_sub[p_sub["window_label"] == w].empty else 0.0 for w in windows]
                rads = [p_sub[p_sub["window_label"] == w]["radius"].values[0] if not p_sub[p_sub["window_label"] == w].empty else 0.0 for w in windows]

                proto_display = PROTOCOL_DISPLAY_NAMES.get(proto, proto)
                color = PROTOCOL_COLORS.get(proto, plt.cm.tab10(i / max(n_protos, 1)))

                offset = (i - (n_protos - 1) / 2) * width
                ax.bar(x + offset, means, width, yerr=rads, capsize=3, label=proto_display, color=color, edgecolor="#222222", linewidth=0.6)

            ax.legend(title="Protocol", frameon=True, facecolor="#fdfdfd")
        else:
            group_spacing = 0.8 / max(n_protos, 1)
            bar_w = group_spacing * 0.42

            for i, proto in enumerate(protocols):
                p_sub = sub[sub["protocol"] == proto]
                color = PROTOCOL_COLORS.get(proto, plt.cm.tab10(i / max(n_protos, 1)))
                proto_center = (i - (n_protos - 1) / 2) * group_spacing

                for j, dset in enumerate([label1, label2]):
                    d_sub = p_sub[p_sub["dataset"] == dset]
                    means = [d_sub[d_sub["window_label"] == w]["mean"].values[0] if not d_sub[d_sub["window_label"] == w].empty else 0.0 for w in windows]
                    rads = [d_sub[d_sub["window_label"] == w]["radius"].values[0] if not d_sub[d_sub["window_label"] == w].empty else 0.0 for w in windows]

                    bar_offset = proto_center + (j - 0.5) * bar_w
                    hatch = None if j == 0 else "//"
                    alpha = 1.0 if j == 0 else 0.55

                    ax.bar(x + bar_offset, means, bar_w, yerr=rads, capsize=2,
                           color=color, alpha=alpha, hatch=hatch, edgecolor="#222222", linewidth=0.6)

            make_comparison_legend(ax, protocols, label1, label2)

        title_text = spec["title"]
        if compare_mode:
            title_text += f"\n({label1} vs {label2})"
        ax.set_title(title_text)
        ax.set_xlabel("Time Window (s)")
        ax.set_ylabel(spec["ylabel"])
        ax.set_xticks(x)
        ax.set_xticklabels(windows)
        ax.grid(True, axis="y")
        plt.tight_layout()

        fig.savefig(out_dir / spec["fname"], dpi=300)
        plt.close(fig)

    plot_cross_protocol_summary_grid(df_all, protocols, out_dir / "comparison_all_protocols_dashboard.png", compare_mode, label1, label2)

    # Superplots (Linear & Log Scale, Full & No-DNS Summary)
    plot_superplot_hcs_tgen_performance(df_all, out_dir, label1=label1, use_log_scale=False, testbed_data=testbed_data)
    plot_superplot_hcs_tgen_performance(df_all, out_dir, label1=label1, use_log_scale=True, testbed_data=testbed_data)

    plot_superplot_cusum_cumulative_features(df_all, out_dir, compare_mode=compare_mode, label1=label1, label2=label2, use_log_scale=False, exclude_dns_in_summary=False)
    plot_superplot_cusum_cumulative_features(df_all, out_dir, compare_mode=compare_mode, label1=label1, label2=label2, use_log_scale=True, exclude_dns_in_summary=False)
    plot_superplot_cusum_cumulative_features(df_all, out_dir, compare_mode=compare_mode, label1=label1, label2=label2, use_log_scale=False, exclude_dns_in_summary=True)
    plot_superplot_cusum_cumulative_features(df_all, out_dir, compare_mode=compare_mode, label1=label1, label2=label2, use_log_scale=True, exclude_dns_in_summary=True)


def plot_superplot_hcs_tgen_performance(df_all: pd.DataFrame, out_dir: Path, label1: str = "HCS+TGen",
                                         use_log_scale: bool = False,
                                         testbed_data: Optional[Dict[str, Any]] = None):
    """
    Generate Superplot 1: Multi-panel figure combining all protocol performance & dependability results for HCS+TGen.
    Combines Median Latency (p50), Goodput, System Integrity, and Availability (MTBF) across time windows.

    If testbed_data is provided (dict keyed by protocol name, e.g. 'obfs4', 'webtunnel', 'skyhook'),
    an additional bar is rendered next to each simulation bar showing the real-testbed measurement.
    Testbed bars use a cross-hatch ("xx") pattern and a bold black edge to distinguish them clearly.
    """
    # Mapping from simulation protocol key -> testbed JSON key
    TESTBED_KEY_MAP = {
        "only_obfs": "obfs4",
        "only_webtunnel": "webtunnel",
        "only_skyhook": "skyhook",
    }

    hcs_df = df_all[(df_all["dataset"] == label1) & (df_all["is_cusum"] == False)].copy()
    if hcs_df.empty:
        dsets = df_all["dataset"].unique()
        if len(dsets) > 0:
            hcs_df = df_all[(df_all["dataset"] == dsets[0]) & (df_all["is_cusum"] == False)].copy()
        else:
            return

    protocols = ["only_obfs", "only_webtunnel", "only_skyhook", "only_mastodon"]
    available_protos = [p for p in protocols if p in hcs_df["protocol"].unique()]
    if not available_protos:
        available_protos = sorted(hcs_df["protocol"].unique())

    cum_windows = ["[10-910]s", "[10-1810]s", "[10-2710]s", "[10-3610]s"]
    x = np.arange(len(cum_windows))
    n_protos = len(available_protos)

    # When testbed data exists, we add an extra bar slot per protocol that has testbed coverage
    has_testbed = testbed_data is not None and len(testbed_data) > 0

    fig, axes = plt.subplots(2, 2, figsize=(15, 9.5))

    plot_specs = [
        {"metric": "latency50", "scope": "cumulative", "target": None, "title": "Median Latency (p50)", "ylabel": "Seconds (s)"},
        {"metric": "goodput", "scope": "cumulative", "target": None, "title": "Goodput", "ylabel": "Bits/s"},
        {"metric": "integrity", "scope": "cumulative", "target": "system", "title": "System Integrity", "ylabel": "Ratio [0-1]"},
        {"metric": "availability", "scope": "cumulative", "target": None, "title": "Availability (MTBF)", "ylabel": "Seconds (s)"},
    ]

    # -------------------------------------------------------------------------
    # Panel 1: Latency Percentiles (p25, p50, p75, p100) across all protocols
    # -------------------------------------------------------------------------
    ax1 = axes[0, 0]
    lat_keys = [("latency25", "p25", 0.35), ("latency50", "p50", 0.55), ("latency75", "p75", 0.75), ("latency100", "p100", 0.95)]
    lat_sub = hcs_df[hcs_df["metric"].isin(["latency25", "latency50", "latency75", "latency100"]) & (hcs_df["scope"] == "cumulative")].copy()

    # Testbed has p0–p100 (5 percentiles); simulation has 4 (p25–p100).
    # Layout per protocol: [sim_p25 sim_p50 sim_p75 sim_p100 | tb_p0 tb_p25 tb_p50 tb_p75 tb_p100]
    tb_lat_keys = [
        ("p0_min_seconds",     "p0",   0.20),
        ("p25_seconds",        "p25",  0.35),
        ("p50_median_seconds", "p50",  0.55),
        ("p75_seconds",        "p75",  0.75),
        ("p100_max_seconds",   "p100", 0.95),
    ]
    n_sim_bars = 4
    n_tb_bars  = len(tb_lat_keys) if has_testbed else 0
    n_lat_bars_per_proto = n_sim_bars + n_tb_bars
    group_w = 0.82
    proto_w = group_w / max(n_protos, 1)
    bar_w = proto_w / max(n_lat_bars_per_proto, 1)

    for i, proto in enumerate(available_protos):
        p_sub = lat_sub[lat_sub["protocol"] == proto]
        proto_display = PROTOCOL_DISPLAY_NAMES.get(proto, proto)
        color = PROTOCOL_COLORS.get(proto, plt.cm.tab10(i))
        proto_center = (i - (n_protos - 1) / 2) * proto_w

        # Simulation bars occupy slots 0..n_sim_bars-1
        for j, (m_key, m_lbl, alpha) in enumerate(lat_keys):
            m_data = p_sub[p_sub["metric"] == m_key]
            means = [m_data[m_data["window_label"] == w]["mean"].values[0] if not m_data[m_data["window_label"] == w].empty else 0.0 for w in cum_windows]
            rads  = [m_data[m_data["window_label"] == w]["radius"].values[0] if not m_data[m_data["window_label"] == w].empty else 0.0 for w in cum_windows]

            bar_offset = proto_center + (j - (n_lat_bars_per_proto - 1) / 2) * bar_w
            ax1.bar(x + bar_offset, means, bar_w, yerr=rads, capsize=1.5,
                    color=color, alpha=alpha, edgecolor="#222222", linewidth=0.5)

        # Testbed bars occupy slots n_sim_bars..n_lat_bars_per_proto-1 (all 5 percentiles), ONLY for [10-3610]s
        if has_testbed:
            tb_key = TESTBED_KEY_MAP.get(proto)
            if tb_key and tb_key in testbed_data:
                tb_lats = testbed_data[tb_key]["percentile_latencies"]
                target_w = "[10-3610]s"
                if target_w in cum_windows:
                    w_idx = cum_windows.index(target_w)
                    x_target = np.array([x[w_idx]])
                    for k, (json_key, tb_lbl, alpha) in enumerate(tb_lat_keys):
                        tb_val_scalar = tb_lats.get(json_key, 0.0)
                        slot = n_sim_bars + k
                        bar_offset = proto_center + (slot - (n_lat_bars_per_proto - 1) / 2) * bar_w
                        ax1.bar(x_target + bar_offset, [tb_val_scalar], bar_w,
                                color=color, alpha=alpha, hatch="//",
                                edgecolor="#000000", linewidth=0.8)


    title_suffix = " (Log Scale)" if use_log_scale else " [Log Scale]"
    ax1.set_title("Mean Latencies (p25, p50, p75, p100)" + title_suffix, fontsize=11, fontweight="bold")
    ax1.set_xlabel("Time Window (s)", fontsize=10)
    ax1.set_ylabel("Latency (s)", fontsize=10)
    ax1.set_xticks(x)
    ax1.set_xticklabels(cum_windows, fontsize=9)
    ax1.set_yscale("log")
    ax1.grid(True, axis="y")

    # Legend for Panel 1
    from matplotlib.patches import Patch
    proto_patches = [Patch(facecolor=PROTOCOL_COLORS.get(p, plt.cm.tab10(idx)), edgecolor="#222222", label=PROTOCOL_DISPLAY_NAMES.get(p, p)) for idx, p in enumerate(available_protos)]
    perc_patches = [Patch(facecolor="#555555", alpha=alpha, edgecolor="#222222", label=m_lbl) for _, m_lbl, alpha in lat_keys]
    if has_testbed:
        tb_perc_patches = [Patch(facecolor="#888888", alpha=alpha, hatch="//", edgecolor="#000000", linewidth=0.8, label=f"Testbed {tb_lbl}")
                           for _, tb_lbl, alpha in tb_lat_keys]
    else: 
        tb_perc_patches = []
    ax1.legend(handles=proto_patches + perc_patches + tb_perc_patches, loc="upper left", frameon=True, facecolor="#fdfdfd", fontsize=7.5, ncol=2)

    # -------------------------------------------------------------------------
    for idx, spec in enumerate(plot_specs[1:], start=1):
        row, col = divmod(idx, 2)
        ax = axes[row, col]

        m = spec["metric"]
        scope = spec["scope"]
        target = spec["target"]

        query_str = f"(metric == '{m}') & (scope == '{scope}')"
        if target:
            query_str += f" & (target == '{target}')"

        sub = hcs_df.query(query_str).copy()

        # When testbed bars are added, shrink simulation bar width to leave room
        tb_panels = {"goodput", "integrity"}  # panels that show testbed data
        show_tb_this_panel = has_testbed and (m in tb_panels)
        slots_per_proto = 2 if show_tb_this_panel else 1
        width = (0.8 / max(n_protos, 1)) / slots_per_proto

        for i, proto in enumerate(available_protos):
            p_sub = sub[sub["protocol"] == proto]
            means = [p_sub[p_sub["window_label"] == w]["mean"].values[0] if not p_sub[p_sub["window_label"] == w].empty else 0.0 for w in cum_windows]
            rads = [p_sub[p_sub["window_label"] == w]["radius"].values[0] if not p_sub[p_sub["window_label"] == w].empty else 0.0 for w in cum_windows]

            proto_display = PROTOCOL_DISPLAY_NAMES.get(proto, proto)
            color = PROTOCOL_COLORS.get(proto, plt.cm.tab10(i))
            group_center = (i - (n_protos - 1) / 2) * (width * slots_per_proto)

            if show_tb_this_panel:
                sim_offset = group_center - width / 2
            else:
                sim_offset = group_center

            rects = ax.bar(x + sim_offset, means, width, yerr=rads, capsize=2.5,
                           label=proto_display, color=color, edgecolor="#222222", linewidth=0.6)

            for rect in rects:
                h = rect.get_height()
                if h > 0.001:
                    ax.annotate(f"{h:.2f}" if m == "integrity" else (f"{h:.1f}" if h >= 1.0 else f"{h:.2f}"),
                                xy=(rect.get_x() + rect.get_width() / 2, h),
                                xytext=(0, 2), textcoords="offset points",
                                ha="center", va="bottom", fontsize=7.5)

            # Testbed bar for this protocol (ONLY for [10-3610]s window)
            if show_tb_this_panel:
                tb_key = TESTBED_KEY_MAP.get(proto)
                if tb_key and tb_key in testbed_data:
                    if m == "goodput":
                        tb_val_scalar = testbed_data[tb_key]["total_received_goodput"]["bps"]
                    elif m == "integrity":
                        tb_val_scalar = testbed_data[tb_key]["total_system_integrity"]
                    else:
                        tb_val_scalar = None

                    if tb_val_scalar is not None:
                        target_w = "[10-3610]s"
                        if target_w in cum_windows:
                            w_idx = cum_windows.index(target_w)
                            x_target = np.array([x[w_idx]])
                            tb_offset = group_center + width / 2
                            tb_rects = ax.bar(x_target + tb_offset, [tb_val_scalar], width,
                                              color=color, alpha=0.75, hatch="//",
                                              edgecolor="#000000", linewidth=1.0,
                                              label=f"{proto_display} (Testbed)" if False else "")
                            for rect in tb_rects:
                                h = rect.get_height()
                                if h > 0.001:
                                    ax.annotate(f"{h:.2f}" if m == "integrity" else (f"{h:.1f}" if h >= 1.0 else f"{h:.3f}"),
                                                xy=(rect.get_x() + rect.get_width() / 2, h),
                                                xytext=(0, 2), textcoords="offset points",
                                                ha="center", va="bottom", fontsize=7.0,
                                                fontstyle="italic", color="#333333")

        title_suffix = " (Log Scale)" if use_log_scale else ""
        ax.set_title(spec["title"] + title_suffix, fontsize=11, fontweight="bold")
        ax.set_xlabel("Time Window (s)", fontsize=10)
        ax.set_ylabel(spec["ylabel"], fontsize=10)
        ax.set_xticks(x)
        ax.set_xticklabels(cum_windows, fontsize=9)

        if use_log_scale:
            if m == "integrity" or m == "availability":
                ax.set_yscale("symlog", linthresh=0.01)
            else:
                ax.set_yscale("log")
        else:
            if m == "integrity":
                ax.set_ylim(0, 1.15)

        ax.grid(True, axis="y")
        if idx == 1:
            legend_handles, legend_labels = ax.get_legend_handles_labels()
            if show_tb_this_panel:
                # Add a generic testbed indicator to legend
                testbed_legend_patch = Patch(facecolor="#888888", alpha=0.75, hatch="//",
                                             edgecolor="#000000", linewidth=1.0, label="Testbed")
                ax.legend(handles=legend_handles + [testbed_legend_patch],
                          title="Protocol", frameon=True, facecolor="#fdfdfd", fontsize=8.5)
            else:
                ax.legend(title="Protocol", frameon=True, facecolor="#fdfdfd", fontsize=8.5)

    main_title = f"Superplot: Combined Performance & Dependability ({label1})"
    if use_log_scale:
        main_title += " [Log Scale]"
    fig.suptitle(main_title, fontsize=15, weight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])

    fname = "superplot_hcs_tgen_performance_logscale.png" if use_log_scale else "superplot_hcs_tgen_performance.png"
    out_file = out_dir / fname
    fig.savefig(out_file, dpi=300)
    if out_dir.name == "comparison_plots":
        fig.savefig(out_dir.parent / fname, dpi=300)
    plt.close(fig)


def plot_superplot_cusum_cumulative_features(df_all: pd.DataFrame, out_dir: Path, compare_mode: bool = False,
                                              label1: str = "HCS+TGen", label2: str = "TGen Only",
                                              use_log_scale: bool = False, exclude_dns_in_summary: bool = False):
    """
    Generate Superplot 2: Multi-panel figure combining all protocols for cumulative CUSUM Z(t) scores across features.
    X-axis represents cumulative time windows with grouped bars for each protocol.
    If exclude_dns_in_summary is True, generates a clean 2x2 grid (4 subplots) omitting DNS query rate and the 10-3610 summary panel.
    """
    cusum_sub = df_all[(df_all["is_cusum"] == True) & (df_all["scope"] == "cumulative")].copy()
    if cusum_sub.empty:
        return

    protocols = ["only_obfs", "only_webtunnel", "only_skyhook", "only_mastodon"]
    available_protos = [p for p in protocols if p in cusum_sub["protocol"].unique()]
    if not available_protos:
        available_protos = sorted(cusum_sub["protocol"].unique())

    if exclude_dns_in_summary:
        feature_keys = [
            "tcp_outgoing_packet_rate",
            "tcp_incoming_packet_rate",
            "packet_size_mean",
            "packet_interarrival_mean"
        ]
    else:
        feature_keys = [
            "dns_query_rate",
            "tcp_outgoing_packet_rate",
            "tcp_incoming_packet_rate",
            "packet_size_mean",
            "packet_interarrival_mean"
        ]

    feature_titles = {
        "dns_query_rate": "DNS Query Rate",
        "tcp_outgoing_packet_rate": "TCP Outgoing Packet Rate",
        "tcp_incoming_packet_rate": "TCP Incoming Packet Rate",
        "packet_size_mean": "Mean Packet Size",
        "packet_interarrival_mean": "Mean Packet Inter-arrival",
    }

    cum_windows = ["[10-910]s", "[10-1810]s", "[10-2710]s", "[10-3610]s"]
    x = np.arange(len(cum_windows))
    n_protos = len(available_protos)

    if exclude_dns_in_summary:
        fig, axes = plt.subplots(2, 2, figsize=(15, 9.5))
    else:
        fig, axes = plt.subplots(2, 3, figsize=(16, 9.5))

    axes_flat = axes.flatten()

    if not compare_mode:
        width = 0.8 / max(n_protos, 1)
        hcs_sub = cusum_sub[cusum_sub["dataset"] == label1]
        if hcs_sub.empty and len(cusum_sub["dataset"].unique()) > 0:
            hcs_sub = cusum_sub[cusum_sub["dataset"] == cusum_sub["dataset"].unique()[0]]

        for idx, fk in enumerate(feature_keys):
            ax = axes_flat[idx]
            f_sub = hcs_sub[hcs_sub["metric"] == fk]

            for i, proto in enumerate(available_protos):
                p_sub = f_sub[f_sub["protocol"] == proto]
                means = [p_sub[p_sub["window_label"] == w]["mean"].values[0] if not p_sub[p_sub["window_label"] == w].empty else 0.0 for w in cum_windows]
                rads = [p_sub[p_sub["window_label"] == w]["radius"].values[0] if not p_sub[p_sub["window_label"] == w].empty else 0.0 for w in cum_windows]

                proto_display = PROTOCOL_DISPLAY_NAMES.get(proto, proto)
                color = PROTOCOL_COLORS.get(proto, plt.cm.tab10(i))
                offset = (i - (n_protos - 1) / 2) * width

                rects = ax.bar(x + offset, means, width, yerr=rads, capsize=2.5, label=proto_display, color=color, edgecolor="#222222", linewidth=0.6)

                for rect in rects:
                    h = rect.get_height()
                    if h > 0.0001:
                        ax.annotate(f"{h:.2f}", xy=(rect.get_x() + rect.get_width() / 2, h), xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=7.5)

            title_suffix = " (Log Scale)" if use_log_scale else ""
            ax.set_title(feature_titles.get(fk, fk) + title_suffix, fontsize=11, fontweight="bold")
            ax.set_xlabel("Time Window (s)", fontsize=10)
            ax.set_ylabel("CUSUM Z(t)", fontsize=10)
            ax.set_xticks(x)
            ax.set_xticklabels(cum_windows, fontsize=9)
            if use_log_scale:
                ax.set_yscale("symlog", linthresh=0.1)
            ax.grid(True, axis="y")

            if idx == 0:
                ax.legend(title="Protocol", frameon=True, facecolor="#fdfdfd", fontsize=8.5)

        if not exclude_dns_in_summary:
            # Panel 6 (index 5): Overview at final window [10-3610]s across all 5 features
            ax6 = axes_flat[5]
            final_win = "[10-3610]s"
            final_sub = hcs_sub[hcs_sub["window_label"] == final_win]
            fx = np.arange(len(feature_keys))
            feature_short_labels = ["DNS Rate", "TCP Out", "TCP In", "Pkt Size", "Inter-arr"]
            f_width = 0.8 / max(n_protos, 1)

            for i, proto in enumerate(available_protos):
                p_sub = final_sub[final_sub["protocol"] == proto]
                means = [p_sub[p_sub["metric"] == fk]["mean"].values[0] if not p_sub[p_sub["metric"] == fk].empty else 0.0 for fk in feature_keys]
                rads = [p_sub[p_sub["metric"] == fk]["radius"].values[0] if not p_sub[p_sub["metric"] == fk].empty else 0.0 for fk in feature_keys]

                proto_display = PROTOCOL_DISPLAY_NAMES.get(proto, proto)
                color = PROTOCOL_COLORS.get(proto, plt.cm.tab10(i))
                offset = (i - (n_protos - 1) / 2) * f_width

                rects = ax6.bar(fx + offset, means, f_width, yerr=rads, capsize=2, label=proto_display, color=color, edgecolor="#222222", linewidth=0.6)

                for rect in rects:
                    h = rect.get_height()
                    if h > 0.0001:
                        ax6.annotate(f"{h:.2f}", xy=(rect.get_x() + rect.get_width() / 2, h), xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=7)

            title_suffix = " (Log Scale)" if use_log_scale else ""
            ax6.set_title(f"All Features at {final_win}" + title_suffix, fontsize=11, fontweight="bold")
            ax6.set_xticks(fx)
            ax6.set_xticklabels(feature_short_labels, rotation=15, ha="right", fontsize=8.5)
            ax6.set_ylabel("CUSUM Z(t)", fontsize=10)
            if use_log_scale:
                ax6.set_yscale("symlog", linthresh=0.1)
            ax6.grid(True, axis="y")

    else:
        # Comparison mode (HCS+TGen vs TGen Only side-by-side per protocol)
        group_spacing = 0.85 / max(n_protos, 1)
        bar_w = group_spacing * 0.42

        for idx, fk in enumerate(feature_keys):
            ax = axes_flat[idx]
            f_sub = cusum_sub[cusum_sub["metric"] == fk]

            for i, proto in enumerate(available_protos):
                p_sub = f_sub[f_sub["protocol"] == proto]
                color = PROTOCOL_COLORS.get(proto, plt.cm.tab10(i))
                proto_center = (i - (n_protos - 1) / 2) * group_spacing

                for j, dset in enumerate([label1, label2]):
                    d_sub = p_sub[p_sub["dataset"] == dset]
                    means = [d_sub[d_sub["window_label"] == w]["mean"].values[0] if not d_sub[d_sub["window_label"] == w].empty else 0.0 for w in cum_windows]
                    rads = [d_sub[d_sub["window_label"] == w]["radius"].values[0] if not d_sub[d_sub["window_label"] == w].empty else 0.0 for w in cum_windows]

                    bar_offset = proto_center + (j - 0.5) * bar_w
                    hatch = None if j == 0 else "//"
                    alpha = 1.0 if j == 0 else 0.55

                    ax.bar(x + bar_offset, means, bar_w, yerr=rads, capsize=2,
                           color=color, alpha=alpha, hatch=hatch, edgecolor="#222222", linewidth=0.6)

            title_suffix = " (Log Scale)" if use_log_scale else ""
            ax.set_title(feature_titles.get(fk, fk) + title_suffix, fontsize=11, fontweight="bold")
            ax.set_xlabel("Time Window (s)", fontsize=10)
            ax.set_ylabel("CUSUM Z(t)", fontsize=10)
            ax.set_xticks(x)
            ax.set_xticklabels(cum_windows, fontsize=9)
            if use_log_scale:
                ax.set_yscale("symlog", linthresh=0.1)
            ax.grid(True, axis="y")

            if idx == 0:
                make_comparison_legend(ax, available_protos, label1, label2, loc="upper right")

        if not exclude_dns_in_summary:
            # Panel 6: Overview at final window [10-3610]s
            ax6 = axes_flat[5]
            final_win = "[10-3610]s"
            final_sub = cusum_sub[cusum_sub["window_label"] == final_win]
            fx = np.arange(len(feature_keys))
            feature_short_labels = ["DNS Rate", "TCP Out", "TCP In", "Pkt Size", "Inter-arr"]

            for i, proto in enumerate(available_protos):
                p_sub = final_sub[final_sub["protocol"] == proto]
                color = PROTOCOL_COLORS.get(proto, plt.cm.tab10(i))
                proto_center = (i - (n_protos - 1) / 2) * group_spacing

                for j, dset in enumerate([label1, label2]):
                    d_sub = p_sub[p_sub["dataset"] == dset]
                    means = [d_sub[d_sub["metric"] == fk]["mean"].values[0] if not d_sub[d_sub["metric"] == fk].empty else 0.0 for fk in feature_keys]
                    rads = [d_sub[d_sub["metric"] == fk]["radius"].values[0] if not d_sub[d_sub["metric"] == fk].empty else 0.0 for fk in feature_keys]

                    bar_offset = proto_center + (j - 0.5) * bar_w
                    hatch = None if j == 0 else "//"
                    alpha = 1.0 if j == 0 else 0.55

                    ax6.bar(fx + bar_offset, means, bar_w, yerr=rads, capsize=2,
                            color=color, alpha=alpha, hatch=hatch, edgecolor="#222222", linewidth=0.6)

            title_suffix = " (Log Scale)" if use_log_scale else ""
            ax6.set_title(f"All Features at {final_win}" + title_suffix, fontsize=11, fontweight="bold")
            ax6.set_xticks(fx)
            ax6.set_xticklabels(feature_short_labels, rotation=15, ha="right", fontsize=8.5)
            ax6.set_ylabel("CUSUM Z(t)", fontsize=10)
            if use_log_scale:
                ax6.set_yscale("symlog", linthresh=0.1)
            ax6.grid(True, axis="y")

    prefix = "superplot_cusum_cumulative_features"
    if exclude_dns_in_summary:
        prefix += "_nodns"
    if use_log_scale:
        prefix += "_logscale"

    title_str = "Superplot: Combined Cumulative CUSUM Z(t) Scores Across All Protocols"
    if exclude_dns_in_summary:
        title_str += " (No DNS)"
    if compare_mode:
        title_str += f" ({label1} vs {label2})"
    if use_log_scale:
        title_str += " [Log Scale]"

    fig.suptitle(title_str, fontsize=14, weight="bold", y=0.98)
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])

    fname = f"{prefix}.png"
    out_file = out_dir / fname
    fig.savefig(out_file, dpi=300)
    if out_dir.name == "comparison_plots":
        fig.savefig(out_dir.parent / fname, dpi=300)
    plt.close(fig)


def plot_cross_protocol_summary_grid(df_all: pd.DataFrame, protocols: List[str], out_path: Path,
                                      compare_mode: bool = False, label1: str = "Primary", label2: str = "Comparison"):
    """
    Create a 2x3 overview grid comparing all protocols on major metrics.
    """
    fig, axes = plt.subplots(2, 3, figsize=(18, 10))
    main_title = "CP3 Isolated Protocols - Cross-Protocol Performance & Adversary Comparison"
    if compare_mode:
        main_title += f" ({label1} vs {label2})"
    fig.suptitle(main_title, fontsize=15, weight="bold")

    panel_specs = [
        {"metric": "latency50", "scope": "independent", "title": "Median Latency (p50)", "ylabel": "Seconds (s)"},
        {"metric": "goodput", "scope": "independent", "title": "Goodput", "ylabel": "Bits/s"},
        {"metric": "integrity", "target": "system", "scope": "independent", "title": "System Integrity", "ylabel": "Ratio [0-1]"},
        {"metric": "availability", "scope": "cumulative", "title": "Availability (MTBF)", "ylabel": "Seconds (s)"},
        {"metric": "tcp_incoming_packet_rate", "target": "ixpN", "scope": "independent", "title": "TCP Incoming Packet Rate (ixpN)", "ylabel": "Pkts/s"},
        {"metric": "tcp_outgoing_packet_rate", "target": "ixpN", "scope": "independent", "title": "TCP Outgoing Packet Rate (ixpN)", "ylabel": "Pkts/s"},
    ]

    for idx, spec in enumerate(panel_specs):
        row, col = divmod(idx, 3)
        ax = axes[row, col]

        m = spec["metric"]
        scope = spec["scope"]
        target = spec.get("target")

        q_str = f"(metric == '{m}') & (scope == '{scope}')"
        if target:
            q_str += f" & (target == '{target}')"

        sub = df_all.query(q_str).copy()
        if sub.empty:
            ax.text(0.5, 0.5, "No Data", ha="center", va="center")
            continue

        windows = sub.sort_values(by=["start_time", "end_time"])["window_label"].unique()
        x = np.arange(len(windows))
        n_protos = len(protocols)

        if not compare_mode:
            width = 0.8 / max(n_protos, 1)
            for i, proto in enumerate(protocols):
                p_sub = sub[sub["protocol"] == proto]
                means = [p_sub[p_sub["window_label"] == w]["mean"].values[0] if not p_sub[p_sub["window_label"] == w].empty else 0.0 for w in windows]
                rads = [p_sub[p_sub["window_label"] == w]["radius"].values[0] if not p_sub[p_sub["window_label"] == w].empty else 0.0 for w in windows]

                proto_display = PROTOCOL_DISPLAY_NAMES.get(proto, proto)
                color = PROTOCOL_COLORS.get(proto, plt.cm.tab10(i / max(n_protos, 1)))
                offset = (i - (n_protos - 1) / 2) * width

                ax.bar(x + offset, means, width, yerr=rads, capsize=2, label=proto_display if idx == 0 else "", color=color, edgecolor="#222222", linewidth=0.5)
        else:
            group_spacing = 0.8 / max(n_protos, 1)
            bar_w = group_spacing * 0.42
            for i, proto in enumerate(protocols):
                p_sub = sub[sub["protocol"] == proto]
                color = PROTOCOL_COLORS.get(proto, plt.cm.tab10(i / max(n_protos, 1)))
                proto_center = (i - (n_protos - 1) / 2) * group_spacing

                for j, dset in enumerate([label1, label2]):
                    d_sub = p_sub[p_sub["dataset"] == dset]
                    means = [d_sub[d_sub["window_label"] == w]["mean"].values[0] if not d_sub[d_sub["window_label"] == w].empty else 0.0 for w in windows]
                    rads = [d_sub[d_sub["window_label"] == w]["radius"].values[0] if not d_sub[d_sub["window_label"] == w].empty else 0.0 for w in windows]

                    bar_offset = proto_center + (j - 0.5) * bar_w
                    hatch = None if j == 0 else "//"
                    alpha = 1.0 if j == 0 else 0.55

                    ax.bar(x + bar_offset, means, bar_w, yerr=rads, capsize=1.5,
                           color=color, alpha=alpha, hatch=hatch, edgecolor="#222222", linewidth=0.5)

        ax.set_title(spec["title"])
        ax.set_xlabel("Time Window (s)")
        ax.set_ylabel(spec["ylabel"])
        ax.set_xticks(x)
        ax.set_xticklabels(windows, rotation=20)
        ax.grid(True, axis="y")

    if not compare_mode:
        axes[0, 0].legend(title="Protocol", frameon=True, facecolor="#fdfdfd", fontsize=8.5)
    else:
        make_comparison_legend(axes[0, 0], protocols, label1, label2, loc="upper right")

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    fig.savefig(out_path, dpi=300)
    plt.close(fig)


# -----------------------------------------------------------------------------
# Main Execution
# -----------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Parse and plot SMC simulation results for CP3 isolated protocols.")
    parser.add_argument("--results-dir", type=str,
                        default="use-cases/challenge-problem-3/cp3_scenarios/scenario1_isolated_protocols/results_saved",
                        help="Directory containing protocol result subfolders or JSON files.")
    parser.add_argument("--compare", type=str, default=None,
                        help="Path to a second set of results directory to compare against (e.g., scenario2_tgenonly/results).")
    parser.add_argument("--label1", type=str, default=None,
                        help="Label for the primary results set (defaults to auto-detected name like 'HCS+TGen').")
    parser.add_argument("--label2", type=str, default=None,
                        help="Label for the comparison results set (defaults to auto-detected name like 'TGen Only').")
    parser.add_argument("--quatex-file", type=str,
                        default="use-cases/challenge-problem-3/cp3_scenarios/scenario1/pwnd_cp3_scenario_1-quatex.maude",
                        help="Path to the QuaTEx query definition file.")
    parser.add_argument("--output-dir", type=str, default=None,
                        help="Output directory for generated plots and summaries (defaults to <results-dir>/analysis).")
    parser.add_argument("--csv", action="store_true", default=True,
                        help="Save parsed results to CSV.")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress detailed stdout query table printing.")
    parser.add_argument("--testbed-json", type=str, default=None,
                        help="Path to testbed performance JSON (e.g. testbed/performance.json). "
                             "When provided, adds testbed result bars to the superplot for obfs4, webtunnel, skyhook.")

    args = parser.parse_args()
    set_plot_style()

    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent

    results_dir = Path(args.results_dir)
    if not results_dir.is_absolute():
        results_dir = repo_root / results_dir

    if not results_dir.exists():
        alt = repo_root / "use-cases/challenge-problem-3/cp3_scenarios/scenario1_isolated_protocols/results"
        if alt.exists():
            results_dir = alt

    quatex_path = Path(args.quatex_file)
    if not quatex_path.is_absolute():
        quatex_path = repo_root / quatex_path

    if args.output_dir:
        out_dir = Path(args.output_dir)
        if not out_dir.is_absolute():
            out_dir = repo_root / out_dir
    else:
        out_dir = results_dir / "analysis"

    out_dir.mkdir(parents=True, exist_ok=True)

    compare_mode = args.compare is not None
    label1 = args.label1 if args.label1 else detect_dataset_label(results_dir, "Primary")
    
    label2 = None
    compare_dir = None
    if compare_mode:
        compare_dir = Path(args.compare)
        if not compare_dir.is_absolute():
            compare_dir = repo_root / compare_dir
        if not compare_dir.exists():
            print(f"Error: Comparison results directory not found: {compare_dir}")
            return
        label2 = args.label2 if args.label2 else detect_dataset_label(compare_dir, "Comparison")

    # Load testbed performance data if provided
    testbed_data: Optional[Dict[str, Any]] = None
    if args.testbed_json:
        tb_path = Path(args.testbed_json)
        if not tb_path.is_absolute():
            tb_path = repo_root / tb_path
        if tb_path.exists():
            with open(tb_path) as f:
                testbed_data = json.load(f)
            print(f" Testbed JSON:                  {tb_path}")
        else:
            print(f" WARNING: Testbed JSON not found: {tb_path}")

    print("=" * 75)
    print(" CP3 Isolated Protocols Result Parser & Plotter")
    print("=" * 75)
    print(f" Results Directory 1 ({label1}): {results_dir}")
    if compare_mode:
        print(f" Results Directory 2 ({label2}): {compare_dir}")
    print(f" QuaTEx File:                   {quatex_path}")
    print(f" Output Directory:              {out_dir}")
    print("=" * 75)

    # 1. Parse QuaTEx definition file
    quatex_meta = parse_quatex_file(quatex_path)
    print(f"✓ Parsed {len(quatex_meta)} queries from QuaTEx definition.")

    # 2. Load and parse JSON results
    protocol_results1 = load_all_protocol_results(results_dir, quatex_meta)
    if not protocol_results1:
        print(f"Error: No protocol results found in {results_dir}")
        return

    df1 = build_flat_dataframe(protocol_results1, dataset_label=label1)

    if compare_mode:
        protocol_results2 = load_all_protocol_results(compare_dir, quatex_meta)
        if not protocol_results2:
            print(f"Error: No protocol results found in comparison directory {compare_dir}")
            return
        df2 = build_flat_dataframe(protocol_results2, dataset_label=label2)
        df_all = pd.concat([df1, df2], ignore_index=True)
        print(f"✓ Loaded simulation results for {len(protocol_results1)} protocols ({label1}) & {len(protocol_results2)} protocols ({label2}).")
    else:
        df_all = df1
        print(f"✓ Loaded simulation results for {len(protocol_results1)} protocols: {', '.join(protocol_results1.keys())}")

    # 3. Save CSV
    if args.csv:
        csv_file = out_dir / "cp3_all_queries_summary.csv"
        df_all.to_csv(csv_file, index=False)
        print(f"✓ Saved full dataset to CSV: {csv_file}")

    # 4. Print query values if not quiet
    if not args.quiet:
        print("\n" + "=" * 75)
        print(" Summary of Key Metrics Across Protocols")
        print("=" * 75)

        key_metrics = ["latency50", "goodput", "integrity", "tcp_incoming_packet_rate", "tcp_outgoing_packet_rate"]
        summary_df = df_all[(df_all["metric"].isin(key_metrics)) & (df_all["target"].isin(["system", "ixpN", "wtCl1IrcAddr", "skyCl3IrcAddr", "obfsCl5IrcAddr", "iodCl7IrcAddr", "masCl9IrcAddr"]))]

        display_cols = ["dataset", "protocol", "scope", "metric", "window_label", "target_display", "mean", "radius"]
        piv = summary_df[display_cols].sort_values(by=["metric", "scope", "protocol", "window_label"])
        print(piv.to_string(index=False))

    # 5. Generate All Plots in Analysis Directory
    print("\nGenerating Plots in Analysis Directory...")

    adversary_features_list = [
        "dns_query_rate",
        "tcp_incoming_packet_rate",
        "tcp_outgoing_packet_rate",
        "packet_size_mean",
        "packet_interarrival_mean"
    ]

    for proto_name, pdata in protocol_results1.items():
        proto_df = df_all[df_all["protocol"] == proto_name]
        proto_plot_dir = out_dir / proto_name
        proto_plot_dir.mkdir(parents=True, exist_ok=True)

        # Performance plots
        plot_percentile_latency(proto_df, proto_name, proto_plot_dir, compare_mode, label1, label2)
        plot_goodput_bar(proto_df, proto_name, proto_plot_dir, compare_mode, label1, label2)
        plot_integrity_bar(proto_df, proto_name, proto_plot_dir, compare_mode, label1, label2)
        plot_availability_bar(proto_df, proto_name, proto_plot_dir, compare_mode, label1, label2)

        # Individual adversary feature plots vs time window
        for feat in adversary_features_list:
            plot_individual_adversary_feature(proto_df, proto_name, feat, proto_plot_dir, compare_mode, label1, label2)

        # Cumulative CUSUM feature comparison per protocol (one figure per protocol)
        plot_protocol_cusum_cumulative_features(proto_df, proto_name, proto_plot_dir, compare_mode, label1, label2)

        # Dedicated HCS+TGen Performance & Dependability Summary figure
        plot_hcs_tgen_performance_summary(proto_df, proto_name, proto_plot_dir, label1=label1)

        if compare_mode:
            comparison_dir = out_dir / "comparison_plots"
            comparison_dir.mkdir(parents=True, exist_ok=True)
            plot_protocol_cusum_cumulative_features(proto_df, proto_name, comparison_dir, compare_mode, label1, label2)
            plot_hcs_tgen_performance_summary(proto_df, proto_name, comparison_dir, label1=label1)

        # Multi-panel dashboard
        plot_all_protocol_metrics_dashboard(proto_df, proto_name, proto_plot_dir, compare_mode, label1, label2)

        print(f"  ✓ Created complete plot suite for {proto_name} in {proto_plot_dir}")

    # Cross-protocol comparison plots
    comparison_dir = out_dir / "comparison_plots"
    plot_cross_protocol_comparisons(df_all, comparison_dir, compare_mode, label1, label2, testbed_data=testbed_data)
    print(f"  ✓ Created complete cross-protocol comparison plots in {comparison_dir}")

    print("\n" + "=" * 75)
    print(" Parsing and Plotting Complete!")
    print(f" Output Location: {out_dir}")
    print("=" * 75)


if __name__ == "__main__":
    main()
