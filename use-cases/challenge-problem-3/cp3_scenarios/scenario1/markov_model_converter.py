import json
import argparse
import sys
from copy import deepcopy

def convert_markov_model(input_data):
    """
    Converts a Markov model with embedded sleeps into a model with explicit wait states.
    
    Args:
        input_data (dict): The original JSON structure.
        
    Returns:
        dict: The converted JSON structure.
    """
    if "markov" not in input_data or "actions" not in input_data:
        raise ValueError("Invalid input format: missing 'markov' or 'actions' keys.")

    output_data = deepcopy(input_data)
    
    new_markov = {}
    new_actions = {}
    
    original_markov = input_data["markov"]
    original_actions = input_data["actions"]
    
    # Keep track of states that have a sleep associated with them
    states_with_sleep = set()

    for state_name, action_def in original_actions.items():
        # Copy the original action but remove the sleep if it exists
        new_action_def = deepcopy(action_def)
        
        if "sleep" in new_action_def:
            states_with_sleep.add(state_name)
            sleep_def = new_action_def.pop("sleep")
            
            # Create the new wait state action
            wait_state_name = f"{state_name}_wait"
            new_actions[wait_state_name] = {
                "type": "wait",
                "sleep": sleep_def
            }
            
        new_actions[state_name] = new_action_def
        
    for from_state, transitions in original_markov.items():
        if from_state in states_with_sleep:
            # If the current state had a sleep, all its outbound transitions
            # are now moved to the new wait state.
            # The current state will transition ONLY to its wait state with prob 1.0.
            wait_state_name = f"{from_state}_wait"
            new_markov[from_state] = {wait_state_name: 1.0}
            
            # The wait state will take over the original transitions
            new_markov[wait_state_name] = deepcopy(transitions)
        else:
            # If the state didn't have a sleep, its transitions remain the same
            new_markov[from_state] = deepcopy(transitions)

    output_data["markov"] = new_markov
    output_data["actions"] = new_actions
    
    return output_data

def main():
    parser = argparse.ArgumentParser(description="Convert Markov model JSON to use explicit wait states.")
    parser.add_argument("input_file", help="Path to the input JSON file.")
    parser.add_argument("output_file", help="Path to the output JSON file.")
    
    args = parser.parse_args()
    
    try:
        with open(args.input_file, 'r') as f:
            input_data = json.load(f)
    except FileNotFoundError:
        print(f"Error: Input file '{args.input_file}' not found.", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Input file '{args.input_file}' contains invalid JSON.", file=sys.stderr)
        sys.exit(1)
        
    try:
        converted_data = convert_markov_model(input_data)
    except ValueError as e:
        print(f"Error converting model: {e}", file=sys.stderr)
        sys.exit(1)
        
    try:
        with open(args.output_file, 'w') as f:
            json.dump(converted_data, f, indent=4)
        print(f"Successfully converted model and saved to '{args.output_file}'.")
    except IOError as e:
        print(f"Error writing to output file: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()