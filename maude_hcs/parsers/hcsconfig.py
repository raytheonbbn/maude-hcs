import json
from dataclasses import dataclass, field
from typing import List

from dataclasses_json import dataclass_json

from maude_hcs.parsers.graph import Topology

# By using `default_factory=dict`, we ensure that a new dictionary is created
# for each instance, preventing mutable default argument issues.

@dataclass_json
@dataclass
class NondeterministicParameters:
    """Dataclass for nondeterministic simulation parameters."""
    pass

@dataclass_json
@dataclass
class ProbabilisticParameters:
    """Dataclass for probabilistic simulation parameters."""
    pass

@dataclass_json
@dataclass
class UnderlyingNetwork:
    """Dataclass for the underlying network configuration."""
    module: str


@dataclass_json
@dataclass
class WeirdNetwork:
    """Dataclass for the 'weird' (covert) network configuration."""
    module: str

@dataclass_json
@dataclass
class BackgroundTraffic:
    """Dataclass for background traffic parameters."""
    module: str

@dataclass_json
@dataclass
class Application:
    """Dataclass for the application layer configuration."""
    module: str

@dataclass_json
@dataclass
class Output:
    """Dataclass for output and reporting settings."""
    directory: str = "./results"
    result_format: str = "maude"
    save_output: bool = True
    force_save: bool = False
    visualize: bool = False
    preamble: List[str]     = field(default_factory=list)

@dataclass_json
@dataclass
class HCSConfig:
    """Main dataclass to represent the entire JSON configuration."""
    name: str    
    topology: Topology
    output: Output

    @staticmethod
    def from_file(file_path: str) -> 'HCSConfig':
        with open(file_path, 'r') as f:
            data = json.load(f)
        return HCSConfig.from_dict(data)

    def save(self, file_path: str):
        """
        Exports the dataclass instance to a JSON file.

        Args:
            file_path: The path where the JSON file will be saved.
        """
        with open(file_path, 'w') as f:
            # Convert the dataclass to a dict, then handle the special key name
            data = self.to_dict()
            # data['probabilistic_parameters']['nsResourceBounds?'] = data['probabilistic_parameters'].pop('nsResourceBounds')
            json.dump(data, f, indent=4)
