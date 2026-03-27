import argparse
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from parser.dsl_parser import parse_and_resolve
from transpiler.maude_transpiler import transpile_to_maude
from visualizer.graph_generator import generate_graphs
from parser.validator import SemanticValidator, ValidatorException

def main():
    parser = argparse.ArgumentParser(description="proto-ir: Protocol Modeler & Verifier CLI")
    parser.add_argument("input_file", help="Path to the input DSL model file")
    parser.add_argument("-c", "--config", help="Path to JSON/YAML config file")
    parser.add_argument("-o", "--output", help="Path to output Maude file")
    parser.add_argument("-g", "--graph", action="store_true", help="Generate Graphviz visualization PNGs")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input_file):
        print(f"Error: Input file '{args.input_file}' not found.")
        sys.exit(1)

    print(f"Parsing and resolving imports for '{args.input_file}'...")
    try:
        program = parse_and_resolve(args.input_file)
    except Exception as e:
        print(f"Syntax Error during parsing:\n{e}")
        sys.exit(1)
        
    print(f"Parsed AST: {len(program.machines)} machines, {len(program.tests)} tests found.")
    
    # Execute semantic validation pass
    try:
        validator = SemanticValidator(program)
        validator.validate()
    except ValidatorException as ve:
        print(f"Compilation Error: {ve}")
        sys.exit(1)
    
    config_params = {}
    if args.config:
        import yaml
        if not os.path.exists(args.config):
            print(f"Error: Config file '{args.config}' not found.")
            sys.exit(1)
        with open(args.config, "r") as f:
            config_params = yaml.safe_load(f) or {}
        print(f"Loaded {len(config_params)} parameters from {args.config}")
    
    if args.graph:
        graphs = generate_graphs(program)
        for i, g in enumerate(graphs):
            out_name = f"{args.input_file}.graph_{i}"
            try:
                g.render(out_name, format="png", cleanup=True)
                print(f"Saved graph visualization to {out_name}.png")
            except Exception as e:
                print(f"Warning: Failed to render {out_name}. Graphviz 'dot' might not be installed. ({e})")
                
    # Run built-in DSL tests via Simulation
    if program.tests:
        from simulator.state_machine import DSLSimulator
        sim = DSLSimulator(program, config_params)
        sim.run_all()
            
    maude_files = transpile_to_maude(program, config_params)
    
    if args.output:
        os.makedirs(args.output, exist_ok=True)
        for filename, content in maude_files.items():
            path = os.path.join(args.output, filename)
            with open(path, "w") as f:
                f.write(content)
        print(f"Code successfully transpiled to directory '{args.output}'")
    else:
        print("\n--- Transpiled Maude Code ---")
        for filename, content in maude_files.items():
            print(f"--- {filename} ---")
            print(content)

if __name__ == "__main__":
    main()
