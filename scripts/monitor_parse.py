import subprocess
import json
from collections import defaultdict
import numpy as np
from scipy.stats import wasserstein_distance
from datetime import datetime
import re
import os
import sys

# python monitor_parse.py <tgen_log_file> <raceboat_post_log_file> <raceboat_fetch_log_file> <results_out_file>"

# --- Command Definitions (Using {log_file} placeholder) ---

# 1. tgenPosting (Original Single-Line Stats)
TGEN_POSTING_CMD = "grep \"STATS.*num_to_post\" {log_file} | cut -d'=' -f2"

# 2. tgenFetching (Two-Line Attachments Stats)
DOWNLOAD_CMD = "grep 'Downloading [0-9]\\+ attachment' {log_file} | cut -d' ' -f7"
DOWNLOAD_CMD_2 = "grep 'Downloading [0-9] attachment' {log_file} | cut -d' ' -f5"
MONITOR_STATS_CMD = "grep 'STATS.*monitor_download' {log_file} | cut -d' ' -f6-"
MONITOR_STATS_CMD = "grep 'STATS.*download\"' {log_file} | cut -d' ' -f6-"

# 3. raceboatPosting (Three-Line Post Durations)
RACEBOAT_POSTING_IMAGES_CMD = "grep \"PluginMastodon::enqueueContent: called with params.linkId\" {log_file} | cut -d' ' -f10,11"
RACEBOAT_POSTING_START_CMD = "grep \"Raceboat::TransportComponentWrapper::doAction: called with handlesJson\" {log_file} | cut -d' ' -f2,11"
RACEBOAT_POSTING_STOP_CMD = "grep \"PluginCommsTwoSixStubUserModelReactiveFile::onTransportEvent: called with event.json\" {log_file} | cut -d' ' -f2"

# 4. raceboatFetching (Hashtag Fetch Duration)
RACEBOAT_FETCHING_START_CMD = "grep \"PluginMastodon::doAction: Fetching from single link\" {log_file} | cut -d' ' -f2"
RACEBOAT_FETCHING_END_CMD = "grep \"Link::fetch: .*items for hashtag\" {log_file} | cut -d' ' -f2,8"

# Timestamp format for parsing (H:M:S.microseconds)
TIME_FORMAT = '%H:%M:%S.%f'

# --- Core Utility Functions ---

def execute_shell_command(command, log_file):
    """Executes a shell command gracefully."""
    full_command = command.format(log_file=log_file)
    try:
        result = subprocess.run(
            full_command, 
            capture_output=True, 
            text=True, 
            shell=True,
            check=True
        )
        return result.stdout.strip().split('\n')
    except subprocess.CalledProcessError as e:
        if e.returncode == 1: 
            return []
        print(f"❌ ERROR: Shell command failed: {full_command}. Stderr: {e.stderr.strip()}")
        return []

# --- Statistical Processing (Returns serializable dictionary) ---

def process_and_analyze_data(data):
    """
    Groups data by 'num_images' and calculates statistics, returning a JSON-serializable dictionary.
    """
    grouped_times = defaultdict(list)
    for item in data: grouped_times[item['num_images']].append(item['elapsed_time'])

    analysis_results = {}
    for num_images, times_list in grouped_times.items():
        if len(times_list) < 2: continue
            
        times_array = np.array(times_list)
        
        # Calculate statistics
        min_val = np.min(times_array); max_val = np.max(times_array)
        mean_val = np.mean(times_array); median_val = np.median(times_array)
        std_val = np.std(times_array)

        # Earth Mover's Distance (Wasserstein Distance)
        emd_val = 0.0
        if std_val > 0:
            N = len(times_array) * 10 
            normal_sample = np.random.normal(loc=mean_val, scale=std_val, size=N)
            emd_val = wasserstein_distance(times_array, normal_sample)

        # Convert all statistical results to native Python floats for JSON serialization
        analysis_results[str(num_images)] = {
            'count': len(times_list),
            'min': float(min_val),
            'max': float(max_val),
            'mean': float(mean_val),
            'median': float(median_val),
            'std': float(std_val),
            'emd_vs_normal': float(emd_val),
            'elapsed_times': times_list # Include raw list
        }
    return analysis_results

# --- Parsing Functions (Refactored to match new names) ---

# --- Analysis: tgenPosting ---
def parse_tgen_posting(log_file):
    lines = execute_shell_command(TGEN_POSTING_CMD, log_file)
    if not lines: return []
    parsed_data = []
    for line in lines:
        clean_line = line.strip().strip('"')
        if clean_line:
            try:
                data = json.loads(clean_line)
                if 'num_to_post' in data: data['num_images'] = data.pop('num_to_post') 
                if 'num_images' in data and 'elapsed_time' in data: parsed_data.append(data)
                else: raise KeyError("Missing 'num_images' or 'elapsed_time'.")
            except (json.JSONDecodeError, KeyError) as e:
                print(f"⚠️ ERROR (tgenPosting): Skipping line due to {type(e).__name__}: {e}. Data: {clean_line[:60]}")
    return parsed_data

# --- Analysis: tgenFetching ---
def parse_tgen_fetching(log_file):
    counts = [int(c.strip()) for c in execute_shell_command(DOWNLOAD_CMD, log_file) if c.strip().isdigit()]
    alt_counts = [int(c.strip()) for c in execute_shell_command(DOWNLOAD_CMD_2, log_file) if c.strip().isdigit()]
    json_strings = execute_shell_command(MONITOR_STATS_CMD, log_file)
    #print(f"Counts: {counts} | altcounts: {alt_counts} | {len(json_strings)}")
        
    if len(counts) != len(json_strings) and (counts or json_strings):
        if len(alt_counts) == len(json_strings) and alt_counts:
            print(f"Using alt counts.")
            counts = alt_counts
        else:
            print(f"⚠️ WARNING (tgenFetching): Mismatched counts! Found {len(counts)} and {len(alt_counts)} counts and {len(json_strings)} JSON objects.")
        
    parsed_data = []
    for count, json_str in zip(counts, json_strings):
        try:
            json_payload = json_str.split('STATS=')[1].strip()
            data = json.loads(json_payload)
            
            data['num_images'] = count
            if 'elapsed_time' in data: parsed_data.append(data)
            else: raise KeyError("Missing 'elapsed_time' after parsing.")
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            try:
                json_payload = "{" + json_str.strip().replace("'", "")
                data = json.loads(json_payload)

                timing_data = data["hashtag_collect"]["timing_data"]
                if 'elapsed_time' in timing_data:
                  parsed_data.append({"num_images": count, "elapsed_time": timing_data["elapsed_time"]})
                else: raise KeyError("Missing 'elapsed_time' after parsing.")
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                print(f"⚠️ ERROR (tgenFetching): Skipping pair due to {type(e).__name__}: {e}. JSON: {json_str[:60]}")
            
    return parsed_data

# --- Analysis: raceboatPosting Helpers ---

def parse_rb_post_images(log_file):
    data_map = {}; lines = execute_shell_command(RACEBOAT_POSTING_IMAGES_CMD, log_file)
    for line in lines:
        try:
            action_id_match = re.search(r'action\.actionId=(\d+)', line)
            json_match = re.search(r'action\.json=({.*}),', line)
            if not action_id_match or not json_match: raise ValueError("Missing action ID or JSON payload.")
            action_id = int(action_id_match.group(1)); data = json.loads(json_match.group(1))
            if 'numImages' not in data: raise KeyError("Missing 'numImages' key in JSON payload.")
            data_map[action_id] = {'num_images': data['numImages']}
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            print(f"⚠️ ERROR (raceboatPosting/Images): Skipping line due to {type(e).__name__}: {e}. Data: {line[:60]}")
    return data_map

def parse_rb_post_start(log_file):
    data_map = {}; lines = execute_shell_command(RACEBOAT_POSTING_START_CMD, log_file)
    for line in lines:
        try:
            parts = line.split(': id:'); 
            if len(parts) != 2: raise ValueError("Unexpected log line format (missing ': id:').")
            timestamp_str = parts[0].strip(); action_id = int(parts[1].strip().strip('}'))
            time_obj = datetime.strptime(timestamp_str, TIME_FORMAT)
            data_map[action_id] = {'start_time': time_obj}
        except (ValueError, IndexError) as e:
            print(f"⚠️ ERROR (raceboatPosting/Start): Skipping line due to {type(e).__name__}: {e}. Data: {line[:60]}")
    return data_map

def parse_rb_post_stop(log_file):
    time_list = []; lines = execute_shell_command(RACEBOAT_POSTING_STOP_CMD, log_file)
    for line in lines:
        try:
            timestamp_str = line.strip().strip(':')
            time_obj = datetime.strptime(timestamp_str, TIME_FORMAT)
            time_list.append(time_obj)
        except (ValueError, IndexError) as e:
            print(f"⚠️ ERROR (raceboatPosting/Stop): Skipping line due to {type(e).__name__}: {e}. Data: {line[:60]}")
    return time_list

def parse_raceboat_posting(log_file):
    num_images_data = parse_rb_post_images(log_file)
    start_data = parse_rb_post_start(log_file)
    stop_times = parse_rb_post_stop(log_file)
    
    merged_by_id = {}; final_data = []
    for action_id, img_data in num_images_data.items():
        if action_id in start_data: merged_by_id[action_id] = {**img_data, **start_data[action_id]}

    sorted_starts = sorted(merged_by_id.values(), key=lambda x: x['start_time'])
    
    for start_event, stop_time in zip(sorted_starts, stop_times):
        try:
            duration = (stop_time - start_event['start_time']).total_seconds()
            if duration <= 0: raise ValueError("Duration is non-positive (stop time <= start time).")
            
            final_data.append({
                'num_images': start_event['num_images'], 
                'elapsed_time': duration
            })
        except ValueError as e:
            print(f"⚠️ ERROR (raceboatPosting/Merge): Skipping event due to {type(e).__name__}: {e}. Start: {start_event['start_time']}, Stop: {stop_time}")
            
    return final_data

# --- Analysis: raceboatFetching ---
def parse_raceboat_fetching(log_file):
    start_time_strings = execute_shell_command(RACEBOAT_FETCHING_START_CMD, log_file)
    end_lines = execute_shell_command(RACEBOAT_FETCHING_END_CMD, log_file)
    
    start_times = []
    for ts_str in start_time_strings:
        try:
            clean_ts_str = ts_str.strip().strip(':')
            start_times.append(datetime.strptime(clean_ts_str, TIME_FORMAT))
        except ValueError as e:
            print(f"⚠️ ERROR (raceboatFetching/Start): Skipping time due to {type(e).__name__}: {e}. Data: {ts_str[:60]}")
            
    end_events = [] 
    for line in end_lines:
        try:
            parts = line.split()
            if len(parts) != 2: raise ValueError("Unexpected log line format (not 'timestamp count').")
            if not parts[1].isdigit(): raise ValueError("Item count is not a valid integer.")
                
            end_time = datetime.strptime(parts[0].strip().strip(':'), TIME_FORMAT)
            item_count = int(parts[1].strip())
            end_events.append({'end_time': end_time, 'num_images': item_count})
        except (ValueError, IndexError) as e:
            print(f"⚠️ ERROR (raceboatFetching/End): Skipping line due to {type(e).__name__}: {e}. Data: {line[:60]}")
    
    final_data = []
    if len(start_times) != len(end_events):
        print(f"⚠️ WARNING (raceboatFetching/Merge): Mismatched counts! Found {len(start_times)} starts and {len(end_events)} ends.")

    for start_time, end_event in zip(start_times, end_events):
        try:
            duration = (end_event['end_time'] - start_time).total_seconds()
            if duration <= 0: raise ValueError("Duration is non-positive (stop time <= start time).")
            
            final_data.append({
                'num_images': end_event['num_images'], 
                'elapsed_time': duration
            })
        except ValueError as e:
            print(f"⚠️ ERROR (raceboatFetching/Merge): Skipping event due to {type(e).__name__}: {e}.")
            
    return final_data

# --- Main Orchestrator ---

def run_all_analyses(tgen_log, rb_post_log, rb_fetch_log):
    """Executes all four analyses against the specified log files."""
    
    final_results = {}
    
    # 1. tgenPosting
    print("Running tgenPosting analysis (A1)...")
    data_1 = parse_tgen_posting(tgen_log)
    if data_1:
        final_results['tgenPosting'] = process_and_analyze_data(data_1)
        print(f"✅ tgenPosting complete. Found {len(data_1)} valid entries.")
    else:
        final_results['tgenPosting'] = {}
        print("— Skipping tgenPosting: No valid entries found.")

    # 2. tgenFetching
    print("\nRunning tgenFetching analysis (A2)...")
    data_2 = parse_tgen_fetching(tgen_log)
    if data_2:
        final_results['tgenFetching'] = process_and_analyze_data(data_2)
        print(f"✅ tgenFetching complete. Found {len(data_2)} valid events.")
    else:
        final_results['tgenFetching'] = {}
        print("— Skipping tgenFetching: No valid events found.")

    # 3. raceboatPosting
    print("\nRunning raceboatPosting analysis (A3)...")
    data_3 = parse_raceboat_posting(rb_post_log)
    if data_3:
        final_results['raceboatPosting'] = process_and_analyze_data(data_3)
        print(f"✅ raceboatPosting complete. Found {len(data_3)} valid actions.")
    else:
        final_results['raceboatPosting'] = {}
        print("— Skipping raceboatPosting: No valid actions found.")

    # 4. raceboatFetching
    print("\nRunning raceboatFetching analysis (A4)...")
    data_4 = parse_raceboat_fetching(rb_fetch_log)
    if data_4:
        final_results['raceboatFetching'] = process_and_analyze_data(data_4)
        print(f"✅ raceboatFetching complete. Found {len(data_4)} valid events.")
    else:
        final_results['raceboatFetching'] = {}
        print("— Skipping raceboatFetching: No valid events found.")

    return final_results

# --- Main Execution ---

if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Usage: python monitor_parse.py <tgen_log_file> <raceboat_post_log_file> <raceboat_fetch_log_file> <results_file>")
        sys.exit(1)

    TGEN_LOG_FILE = sys.argv[1]
    RACEBOAT_POST_LOG_FILE = sys.argv[2]
    RACEBOAT_FETCH_LOG_FILE = sys.argv[3]
    OUTPUT_FILE_NAME = sys.argv[4]

    log_files = [TGEN_LOG_FILE, RACEBOAT_POST_LOG_FILE, RACEBOAT_FETCH_LOG_FILE]
    
    # Check if files exist
    for f in log_files:
        if not os.path.exists(f):
            print(f"❌ Error: Log file not found at '{f}'.")
            sys.exit(1)
    
    print("--- Starting Multi-Log Analysis ---")
    print(f"Tgen Log: {TGEN_LOG_FILE}")
    print(f"Raceboat Post Log: {RACEBOAT_POST_LOG_FILE}")
    print(f"Raceboat Fetch Log: {RACEBOAT_FETCH_LOG_FILE}")
    print("-----------------------------------")


    # Run all analyses
    final_analysis_data = run_all_analyses(
        TGEN_LOG_FILE, 
        RACEBOAT_POST_LOG_FILE, 
        RACEBOAT_FETCH_LOG_FILE
    )

    # Write results to JSON file
    try:
        with open(OUTPUT_FILE_NAME, 'w') as f:
            json.dump(final_analysis_data, f, indent=4)
        print(f"\n✨ Analysis complete! Results written to **{OUTPUT_FILE_NAME}**")
    except Exception as e:
        print(f"\n❌ Error writing results to JSON file: {e}")

