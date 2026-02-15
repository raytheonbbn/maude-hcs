import matplotlib.pyplot as plt
import csv
import re
import numpy as np
import os

# --- Configuration ---
filename = './use-cases/challenge-problem-2/cp2_scenarios_tne/comparison_merged.csv'

# Increased Font Sizes for better readability
FONT_TITLE = 22
FONT_LABEL = 18
FONT_TICK = 14


def parse_csv_data(filepath):
    """
    Parses the merged CSV file.
    Expects format: Measure, Scenario 1, tne_1, Scenario 2, tne_2, ...
    Each data cell is "Mean (Std Dev)"
    """
    parsed_data = {}

    # Regex to extract numeric mean and std dev from "Value (Value)"
    pattern = r"(\d+\.?\d*)\s*\((\d+\.?\d*)\)"

    try:
        with open(filepath, mode='r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)  # Skip header

            for row in reader:
                if not row: continue
                measure = row[0]

                scenario_means = []
                scenario_stds = []
                tne_means = []
                tne_stds = []

                # Data starts from index 1.
                # Scenarios are at 1, 3, 5... (odd indices)
                # TNEs are at 2, 4, 6... (even indices)
                for i in range(1, len(row)):
                    match = re.search(pattern, row[i])
                    if match:
                        val_mean = float(match.group(1))
                        val_std = float(match.group(2))
                    else:
                        val_mean, val_std = 0.0, 0.0

                    if i % 2 != 0:  # Scenario column
                        scenario_means.append(val_mean)
                        scenario_stds.append(val_std)
                    else:  # TNE column
                        tne_means.append(val_mean)
                        tne_stds.append(val_std)

                parsed_data[measure] = {
                    'scenario_means': scenario_means,
                    'scenario_stds': scenario_stds,
                    'tne_means': tne_means,
                    'tne_stds': tne_stds
                }
    except FileNotFoundError:
        print(f"Error: {filepath} not found.")
        return {}
    except Exception as e:
        print(f"Error parsing CSV: {e}")
        return {}

    return parsed_data


def save_comparison_plot(x, y_orig, yerr_orig, y_tne, yerr_tne, title, ylabel, filename):
    """
    Creates a plot with two overlaid series (Original vs TNE).
    """
    plt.figure(figsize=(12, 7))

    # Plot Original Data
    plt.errorbar(
        x, y_orig, yerr=yerr_orig,
        fmt='-o', capsize=5, capthick=2, elinewidth=2,
        color='#1f77b4', label='Scenario Data', linewidth=2, markersize=8
    )

    # Plot TNE Data
    plt.errorbar(
        x, y_tne, yerr=yerr_tne,
        fmt='--s', capsize=5, capthick=2, elinewidth=2,
        color='#ff7f0e', label='TNE Data', linewidth=2, markersize=8, alpha=0.8
    )

    plt.title(title, fontsize=FONT_TITLE, fontweight='bold', pad=20)
    plt.xlabel("Scenario ID", fontsize=FONT_LABEL)
    plt.ylabel(ylabel, fontsize=FONT_LABEL)

    plt.xticks(x, fontsize=FONT_TICK)
    plt.yticks(fontsize=FONT_TICK)
    plt.grid(True, linestyle='--', alpha=0.6)

    plt.legend(fontsize=FONT_LABEL)

    # Add light background shading for error areas
    plt.fill_between(x, np.array(y_orig) - np.array(yerr_orig), np.array(y_orig) + np.array(yerr_orig), color='#1f77b4',
                     alpha=0.1)
    plt.fill_between(x, np.array(y_tne) - np.array(yerr_tne), np.array(y_tne) + np.array(yerr_tne), color='#ff7f0e',
                     alpha=0.1)

    plt.tight_layout()
    plt.savefig(filename)
    plt.close()
    print(f"Saved: {filename}")


# --- Execution ---
if __name__ == "__main__":
    data = parse_csv_data(filename)
    scenarios = np.arange(1, 13)

    if not data:
        print(f"No data found. Please ensure '{filename}' is available in the current directory.")
    else:
        # Measures to plot (defined in original script as prob_measures)
        target_measures = [
            "ExfilFilesC2", "ExfilFilesC8", "ExfilFilesMA1",
            "Goodput", "Latency", "OpDurationC2",
            "OpDurationC8", "OpDurationMA1"
        ]

        for measure in target_measures:
            if measure in data:
                m_data = data[measure]

                # Prepare TNE data series
                y_tne = m_data['tne_means']
                yerr_tne = m_data['tne_stds']

                # Apply conversion for Goodput: bytes to bits (factor of 8)
                if measure == "Goodput":
                    y_tne = [val * 8 for val in y_tne]
                    yerr_tne = [val * 8 for val in yerr_tne]

                save_comparison_plot(
                    x=scenarios,
                    y_orig=m_data['scenario_means'],
                    yerr_orig=m_data['scenario_stds'],
                    y_tne=y_tne,
                    yerr_tne=yerr_tne,
                    title=f"Comparison: {measure} (Mean & Std Dev)",
                    ylabel="Value",
                    filename=f"{measure}_comparison.png"
                )