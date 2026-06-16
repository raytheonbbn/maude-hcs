import sys
import csv
import re
import os

def main():
    if len(sys.argv) != 3:
        print("Usage: python merge_metrics.py <path_to_summary.txt> <path_to_metrics_summary.csv>")
        sys.exit(1)

    summary_file = sys.argv[1]
    metrics_file = sys.argv[2]
    
    # Save the output to the same directory as summary.txt
    output_file = os.path.join(os.path.dirname(summary_file), "comparison_merged.csv")

    # Map the metric names from the CSV to the target SMC rows
    metric_mapping = {
        'C2_file_count': 'ExfilFilesC2',
        'C8_file_count': 'ExfilFilesC8',
        'MA1_file_count': 'ExfilFilesMA1',
        'goodput_bytes_per_second': 'Goodput',
        'latency': 'Latency',
        'C2_time_elapsed': 'OpDurationC2',
        'C8_time_elapsed': 'OpDurationC8',
        'MA1_time_elapsed': 'OpDurationMA1',
    }

    # The exact 8 target metrics/rows we want to write
    target_metrics = [
        'ExfilFilesC2', 'ExfilFilesC8', 'ExfilFilesMA1', 'Goodput', 
        'Latency', 'OpDurationC2', 'OpDurationC8', 'OpDurationMA1'
    ]

    # 1. Parse empirical data from metrics_summary.csv
    # Dictionary structure: tne_data[scenario_id][mapped_metric] = "mean (std)"
    tne_data = {}
    with open(metrics_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            scenario_id = int(row['scenario_id'])
            metric = row['metric']
            
            if metric in metric_mapping:
                mapped_metric_name = metric_mapping[metric]
                mean = float(row['mean'])
                std = float(row['std'])
                
                if scenario_id not in tne_data:
                    tne_data[scenario_id] = {}
                
                # Formatting as "mean (std)" rounded to 2 decimal places to match SMC
                tne_data[scenario_id][mapped_metric_name] = f"{mean:.2f} ({std:.2f})"

    # 2. Parse SMC data from summary.txt dynamically finding scenario columns
    # Dictionary structure: smc_data[mapped_metric][scenario_id] = "val"
    smc_data = {m: {} for m in target_metrics}
    col_to_scenario = {} # Maps column index -> scenario_id
    
    with open(summary_file, 'r') as f:
        for line in f:
            # Splitting on 2 or more spaces to properly separate columns
            parts = re.split(r'\s{2,}', line.strip())
            if not parts:
                continue
            
            # Identify headers and map column index to scenario ID
            if parts[0] == 'Measure':
                for idx, col_name in enumerate(parts[1:]):
                    # Extract the number from "Scenario X"
                    match = re.search(r'Scenario\s+(\d+)', col_name, re.IGNORECASE)
                    if match:
                        col_to_scenario[idx] = int(match.group(1))
                continue
            
            # Skip divider line
            if parts[0].startswith('---'):
                continue
                
            metric_name = parts[0]
            if metric_name in target_metrics:
                for idx, val in enumerate(parts[1:]):
                    # Only map if we successfully identified this column's scenario ID
                    if idx in col_to_scenario:
                        scenario_id = col_to_scenario[idx]
                        
                        # Example input: "5.83 (0.85) [1.00]"
                        # Extract only the "mean (std)" portion
                        match = re.match(r'([\d\.]+\s*\([\d\.]+\))', val)
                        if match:
                            smc_data[metric_name][scenario_id] = match.group(1)
                        else:
                            smc_data[metric_name][scenario_id] = val

    # 3. Merge and write to comparison_merged.csv
    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        
        # Build Header row assuming 12 total scenarios
        max_scenarios = 12
        header = ["Measure"]
        for i in range(1, max_scenarios + 1):
            header.append(f"Scenario {i}")
            header.append(f"tne_{i}")
        writer.writerow(header)

        # Build each Metric row
        for metric in target_metrics:
            row = [metric]
            for i in range(1, max_scenarios + 1):
                # Retrieve SMC value aligned by explicit scenario ID (defaults to zeros if missing)
                smc_val = smc_data[metric].get(i, "0.00 (0.00)")
                row.append(smc_val)
                
                # Retrieve tne empirical value aligned by explicit scenario ID
                tne_val = tne_data.get(i, {}).get(metric, "0.00 (0.00)")
                row.append(tne_val)
                
            writer.writerow(row)
            
    print(f"Data successfully aligned, merged, and saved to {output_file}")

if __name__ == "__main__":
    main()