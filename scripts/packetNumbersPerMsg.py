import re
import sys
import argparse
import numpy as np
import matplotlib.pyplot as plt

def analyze_logs(file_path, mode):
    # Determine the regex pattern and plot labels based on the selected mode
    if mode == 'numpkts':
        pattern = re.compile(r'numPkts\s+(\d+)')
        target_name = "numPkts"
        plot_title = 'Histogram of numPkts Samples'
        x_label = 'Number of Packets (numPkts)'
    elif mode == 'tpl':
        # Matches 'len(tpl) <int>' and captures the integer
        pattern = re.compile(r'len\(tpl\)\s+(\d+)') 
        target_name = "len(tpl)"
        plot_title = 'Histogram of tpl Sizes'
        x_label = 'Size of tpl (len(tpl))'
    
    extracted_values = []
    
    print(f"Parsing '{file_path}' for {target_name}. This may take a moment...")
    
    try:
        # Read line-by-line to handle the ~1GB file without memory overflow
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            for line in file:
                match = pattern.search(line)
                if match:
                    extracted_values.append(int(match.group(1)))
                    
    except FileNotFoundError:
        print(f"Error: The file '{file_path}' was not found.")
        sys.exit(1)

    if not extracted_values:
        print(f"No '{target_name}' patterns found in the file.")
        sys.exit(0)

    data = np.array(extracted_values)
    
    # Calculate statistics
    stats = {
        'Count': len(data),
        'Min': np.min(data),
        'Max': np.max(data),
        'Mean': np.mean(data),
        'Std Dev': np.std(data)
    }
    
    print(f"\n--- Statistics for {target_name} ---")
    for key, value in stats.items():
        if key in ('Count', 'Min', 'Max'):
            print(f"{key:10}: {value}")
        else:
            print(f"{key:10}: {value:.2f}")

    print("\nGenerating histogram...")
    
    # Update matplotlib parameters for larger, more readable fonts
    plt.rcParams.update({
        'font.size': 14,          # General font size
        'axes.titlesize': 18,     # Title size
        'axes.labelsize': 16,     # X and Y label size
        'xtick.labelsize': 12,    # X tick label size
        'ytick.labelsize': 12     # Y tick label size
    })
    
    plt.figure(figsize=(12, 7))
    
    # Plot histogram (using log scale on Y to show both rare and common values)
    plt.hist(data, bins=50, color='skyblue', edgecolor='black', log=True)
    
    plt.title(plot_title)
    plt.xlabel(x_label)
    plt.ylabel('Frequency (Log Scale)')
    plt.grid(axis='y', alpha=0.5, linestyle='--')
    
    # Applies tight layout to prevent labels from getting clipped
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse a large log file and extract statistics.")
    parser.add_argument("filename", help="Path to the log file to parse")
    parser.add_argument(
        "-m", "--mode", 
        choices=['numpkts', 'tpl'], 
        default='numpkts',
        help="Choose what to parse: 'numpkts' (default) or 'tpl'"
    )
    
    args = parser.parse_args()
    analyze_logs(args.filename, args.mode)