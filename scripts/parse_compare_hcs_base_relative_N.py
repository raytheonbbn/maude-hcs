import json
import re
import matplotlib.pyplot as plt
import numpy as np
import sys

def extract_size_from_key(key):
    """Extracts the byte size from a dictionary key using regex."""
    match = re.search(r'(\d+)b', key)
    if match:
        return int(match.group(1))
    return None

def main():
    """
    Loads data from JSON files, calculates relative change against a baseline,
    and plots the results in a publication-quality format.
    """
    args = sys.argv
    if len(args) != 2:
         print(f'Expecting one argument the case number e.g. case2')
         sys.exit(1)
    case = sys.argv[1]
    # List of files to process
    filenames = [
        f"Comparing{case}_200bdistributionsEXPwithSMC.json",
        f"Comparing{case}_400bdistributionsEXPwithSMC.json",
        f"Comparing{case}_800bdistributionsEXPwithSMC.json",
        f"Comparing{case}_1600bdistributionsEXPwithSMC.json"
    ]

    # --- 1. Load data and extract metrics ---
    all_data = {}
    case_name = ""
    for fname in filenames:
        try:
            with open(fname, 'r') as f:
                data = json.load(f)
                # The dictionary has only one key
                key = list(data.keys())[0]
                size = extract_size_from_key(key)
                if size is not None:
                    all_data[size] = data[key]
                    # Extract the base name for the plot title and filename
                    if not case_name:
                        case_name = key.split(f'_{size}b')[0]
                else:
                    print(f"Warning: Could not extract size from key in {fname}")
        except (IOError, json.JSONDecodeError, IndexError) as e:
            print(f"Error processing file {fname}: {e}")
            return

    if not all_data:
        print("No data was loaded. Exiting.")
        return

    # --- 2. Sort data by file size ---
    sorted_sizes = sorted(all_data.keys())
    if not sorted_sizes:
        print("No valid data sizes found. Exiting.")
        return
        
    baseline_size = sorted_sizes[0]
    baseline_data = all_data[baseline_size]
    metrics = list(filter(lambda x: 'kl' in x, baseline_data.keys()))

    # --- 3. Calculate relative change ---
    relative_changes = {metric: [] for metric in metrics}

    for size in sorted_sizes:
        current_data = all_data[size]
        for metric in metrics:
            baseline_value = baseline_data[metric]
            current_value = current_data[metric]
            
            # Avoid division by zero if baseline is 0
            if baseline_value == 0:
                # If baseline is 0, relative change can be considered infinite
                # or just the current value. Here we handle it as 0 change if
                # current is also 0, otherwise we use a large number or NaN.
                # For this plot, we will just show the raw difference.
                change = current_value - baseline_value
            else:
                #change = (current_value - baseline_value) / abs(baseline_value)
                change = (current_value / baseline_value)
            
            relative_changes[metric].append(change)

    # --- 4. Plot the results for publication ---
    plt.style.use('seaborn-v0_8-paper')
    fig, ax = plt.subplots(figsize=(8, 6))

    # Define markers and line styles for clarity
    markers = ['o', 's', '^', 'D']
    linestyles = ['-', '--', '-.', ':']
    metric_labels = {
        'means_diff': 'Mean Difference',
        'stds_diff': 'Std Dev Difference',
        'kl_1_to_2': 'KL Divergence (1 to 2)',
        'kl_2_to_1': 'KL Divergence (2 to 1)'
    }


    for i, metric in enumerate(metrics):
        label = metric_labels.get(metric, metric)
        ax.plot(sorted_sizes, relative_changes[metric],
                label=label,
                marker=markers[i],
                linestyle=linestyles[i],
                markersize=8)

    # --- 5. Customize plot for readability ---
    ax.set_title(f'Relative Change in Metrics for {case_name}', fontsize=16, pad=20)
    ax.set_xlabel('File Size (bytes)', fontsize=14)
    ax.set_ylabel('Relative Change (from 200b baseline)', fontsize=14)
    
    # Set x-axis to show the actual sizes
    ax.set_xticks(sorted_sizes)
    ax.get_xaxis().set_major_formatter(plt.ScalarFormatter())

    ax.tick_params(axis='both', which='major', labelsize=12)
    ax.grid(True, which='both', linestyle='--', linewidth=0.5)
    ax.legend(fontsize=12, frameon=True, facecolor='white', framealpha=0.7)
    
    # Add a horizontal line at y=0 for the baseline reference
    ax.axhline(0, color='black', linewidth=0.8, linestyle='--')

    fig.tight_layout()

    # --- 6. Save the figure ---
    output_filename = f"{case_name}_relativechange.pdf"
    plt.savefig(output_filename, format='pdf', bbox_inches='tight')
    
    print(f"Plot successfully saved as '{output_filename}'")
    
    # To display the plot in an interactive environment
    # plt.show()

if __name__ == '__main__':
    main()