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
        
        if args.graph and hasattr(sim, 'test_traces'):
            from visualizer.graph_generator import generate_sequence_mermaid
            from mermaid import Mermaid
            from mermaid.graph import Graph

            for test_name, trace in sim.test_traces.items():
                mermaid_str = generate_sequence_mermaid(test_name, trace)
                safe_name = test_name.replace(' ', '_').replace('/', '_')
                out_name = f"{args.input_file}.{safe_name}.sequence.md"
                with open(out_name, "w") as f:
                    f.write(mermaid_str)
                print(f"Saved sequence diagram for test '{test_name}' to {out_name}")
                
                # Render using mermaid-py library natively
                try:
                    # Strip markdown blocks for mermaid API syntax strictness
                    raw_mermaid = mermaid_str.replace("```mermaid\n", "").replace("\n```", "").strip()
                    graph = Graph(f"Sequence_{safe_name}", raw_mermaid)
                    m = Mermaid(graph)
                    png_out_name = f"{args.input_file}.{safe_name}.sequence.png"
                    m.to_png(png_out_name)
                    print(f"Saved PNG sequence diagram for test '{test_name}' to {png_out_name}")
                except Exception as e:
                    print(f"Warning: Failed to render PNG sequence diagram locally via mermaid-py for '{test_name}'. ({e})")
            
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
