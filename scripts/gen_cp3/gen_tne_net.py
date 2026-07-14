import sys
import json
from pathlib import Path
from maude_hcs.parsers.tne_parser.generate_network_topology import go_network_gen
from maude_hcs.parsers import load_yaml_to_dict

if __name__ == "__main__":
    yaml_path = sys.argv[1]

    # 1. Load the raw YAML
    data = load_yaml_to_dict(Path(yaml_path), verbose=False)
    tne_network = go_network_gen(data)
    print(json.dumps(tne_network, indent=4))