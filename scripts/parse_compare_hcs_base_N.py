import json
import re
import argparse
import pprint
import sys
from compare_normal_dists import compare_theoretical_distributions

def round_float(f):
    """
    Given a float, convert it to a float with 3 decimal points.
    
    Args:
        f (float): The input float.
        
    Returns:
        float: The float rounded to 3 decimal places, or None if input is not a number.
    """
    if f is None:
        return None
    try:
        return round(float(f), 3)
    except (ValueError, TypeError):
        return None
    
def parse_exp_log(file_path):
    """
    Parses the 'Exp' log file to extract latency statistics.
    
    Args:
        file_path (str): The path to the 'iodine_hcs_base_200byte.log-out' file.
        
    Returns:
        dict: A dictionary containing the extracted statistics.
    """
    stats = {}
    in_stats_block = False
    try:
        with open(file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line == "--- Latency Statistics ---":
                    in_stats_block = True
                    continue
                
                if in_stats_block:
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip()
                        value = value.strip()
                        
                        if key == 'Number of samples':
                            stats['nsims'] = int(value)
                        elif key == 'Average latency':
                            stats['mean'] = float(value)
                        elif key == 'Standard deviation':
                            stats['std'] = float(value)
                        else:
                            stats[key] = value
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}")
        return None
    except Exception as e:
        print(f"An error occurred while parsing {file_path}: {e}")
        return None
        
    return stats

def parse_smc_log(file_path):
    """
    Parses the 'SMC' log file (JSON format) to extract statistics.
    
    Args:
        file_path (str): The path to the 'hcs_base_case1_200b' file.
        
    Returns:
        dict: A dictionary containing the extracted statistics.
    """
    stats = {}
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
            stats['nsims'] = data.get('nsims')
            if 'queries' in data and data['queries']:
                query_stats = data['queries'][0]
                stats['mean'] = query_stats.get('mean')
                stats['std'] = query_stats.get('std')
    except FileNotFoundError:
        print(f"Error: File not found at {file_path}")
        return None
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {file_path}")
        return None
    except (KeyError, IndexError) as e:
        print(f"Error: JSON structure in {file_path} is not as expected. Missing key: {e}")
        return None
    except Exception as e:
        print(f"An error occurred while parsing {file_path}: {e}")
        return None
        
    return stats

def main():
    """
    Main function to run the script, parse files, and print the result.
    """
    parser = argparse.ArgumentParser(
        description="Parse statistics from Exp and SMC log files."
    )
    parser.add_argument(
        "exp_file", 
        help="Path to the Exp log file (e.g., 'iodine_hcs_base_200byte.log-out.dat')"
    )
    parser.add_argument(
        "smc_file", 
        help="Path to the SMC log file (e.g., 'hcs_base_case1_200b.log')"
    )
    args = parser.parse_args()

    # --- Extract case and byte size from filenames ---
    # Example smc_file: 'hcs_base_case1_200b.log' -> case='case1', bytes='200b'
    # Example exp_file: 'iodine_hcs_base_200byte.log-out.dat' -> bytes='200b'
    
    case_match = re.search(r'case(\d+)', args.smc_file)
    bytes_match = re.search(r'(\d+)b(yte)?', args.smc_file)

    if not case_match or not bytes_match:
        print("Could not determine case or byte size from filenames. Using defaults.")
        sys.exit(1)
    else:
        case_name = f"case{case_match.group(1)}"
        byte_size_key = f"{bytes_match.group(1)}b"

    # --- Parse the log files ---
    exp_stats = parse_exp_log(args.exp_file)
    smc_stats = parse_smc_log(args.smc_file)

    if exp_stats is None or smc_stats is None:
        print("Aborting due to parsing errors.")
        return

    # --- Construct the final dictionary ---
    results = {
        f'{case_name}_{byte_size_key}': {
            'SMC': smc_stats,
            'EXP': exp_stats            
        }
    }

    scenarios = {
        f'{case_name}_{byte_size_key}': {
            'SMC': (round_float(smc_stats['mean']), round_float(smc_stats['std']), 'SMC', smc_stats['nsims']),
            'EXP': (round_float(exp_stats['mean']/1000), round_float(exp_stats['std']/1000), 'EXP', exp_stats['nsims'])
        }
    }

    # --- Print the final dictionary ---
    print("--- Parsed Statistics ---")
    pprint.pprint(scenarios)
    
    for scenario in scenarios:
        dist1_params = scenarios[scenario]['EXP']
        dist2_params = scenarios[scenario]['SMC']

        title = f"Comparing {scenario} distributions {dist1_params[2]} with {dist2_params[2]})"
        print(title)
        print("="*80)
        compare_theoretical_distributions(dist1_params, dist2_params, title)


if __name__ == "__main__":    
    main()    
    

