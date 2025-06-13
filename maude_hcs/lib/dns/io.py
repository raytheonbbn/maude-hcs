import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Any

# By using `default_factory=dict`, we ensure that a new dictionary is created
# for each instance, preventing mutable default argument issues.

@dataclass
class Link:
    """Represents a network link with its properties."""
    latency: float
    jitter: float
    loss: float

@dataclass
class NondeterministicParameters:
    """Dataclass for nondeterministic simulation parameters."""
    fileSize: int
    packetSize: int
    packetOverhead: int
    maxMinimiseCount: int
    maxFragmentLen: int
    maxFragmentTx: int

@dataclass
class ProbabilisticParameters:
    """Dataclass for probabilistic simulation parameters."""
    maxPacketSize: int
    nsResourceBounds: bool  # Renamed from 'nsResourceBounds?' for valid identifier
    pacingTimeoutDelay: float
    pacingTimeoutDelayMax: float
    ackTimeoutDelay: float

@dataclass
class UnderlyingNetwork:
    """Dataclass for the underlying network configuration."""
    module: str
    populate_resolver_cache: bool
    record_ttl: int
    addr_prefix: str
    everythingelse_name: str
    everythingelse_num_records: int
    pwnd2_name: str
    pwnd2_base_name: str
    resolver_name: str
    corporate_name: str
    nodes: Dict[str, Any] = field(default_factory=dict)
    links: Dict[str, Link] = field(default_factory=dict)

@dataclass
class WeirdNetwork:
    """Dataclass for the 'weird' (covert) network configuration."""
    module: str
    client_address: str
    client_weird_qtype: str
    monitor_address: str
    links: Dict[str, Link] = field(default_factory=dict)

@dataclass
class BackgroundTraffic:
    """Dataclass for background traffic parameters."""
    num_paced_clients: int
    paced_client_address_prefix: str
    paced_client_Tlimit: int
    paced_client_MaxQPS: int

@dataclass
class Application:
    """Dataclass for the application layer configuration."""
    module: str
    send_app_address: str
    overwrite_queue: bool
    send_app_queue_pkt_sizes: List[int]
    app_start_send_time: float
    rcv_app_address: str
    include_dns_client: bool
    background_traffic: BackgroundTraffic

@dataclass
class Output:
    """Dataclass for output and reporting settings."""
    directory: str
    result_format: str
    save_output: bool
    force_save: bool
    visualize: bool
    preamble: List[str]

@dataclass
class CorporateIodineConfig:
    """Main dataclass to represent the entire JSON configuration."""
    name: str
    nondeterministic_parameters: NondeterministicParameters
    probabilistic_parameters: ProbabilisticParameters
    underlying_network: UnderlyingNetwork
    weird_network: WeirdNetwork
    application: Application
    output: Output

    @staticmethod
    def from_json(file_path: str) -> 'CorporateIodineConfig':
        """
        Loads and instantiates the dataclass from a JSON file.

        Args:
            file_path: The path to the JSON configuration file.

        Returns:
            An instance of CorporateIodineConfig.
        """
        with open(file_path, 'r') as f:
            data = json.load(f)

        # The JSON key 'nsResourceBounds?' is not a valid Python identifier.
        # We need to handle this key separately.
        prob_params_data = data['probabilistic_parameters']
        prob_params_data['nsResourceBounds'] = prob_params_data.pop('nsResourceBounds?')

        # Recursively build the dataclasses from the dictionary
        return CorporateIodineConfig(
            name=data['name'],
            nondeterministic_parameters=NondeterministicParameters(**data['nondeterministic_parameters']),
            probabilistic_parameters=ProbabilisticParameters(**prob_params_data),
            underlying_network=UnderlyingNetwork(
                **{k: v if k != 'links' else {link_name: Link(**link_data) for link_name, link_data in v.items()}
                   for k, v in data['underlying_network'].items()}
            ),
            weird_network=WeirdNetwork(
                **{k: v if k != 'links' else {link_name: Link(**link_data) for link_name, link_data in v.items()}
                   for k, v in data['weird_network'].items()}
            ),
            application=Application(
                **{k: v if k != 'background_traffic' else BackgroundTraffic(**v)
                   for k, v in data['application'].items()}
            ),
            output=Output(**data['output'])
        )

    def to_json(self, file_path: str):
        """
        Exports the dataclass instance to a JSON file.

        Args:
            file_path: The path where the JSON file will be saved.
        """
        with open(file_path, 'w') as f:
            # Convert the dataclass to a dict, then handle the special key name
            data = asdict(self)
            data['probabilistic_parameters']['nsResourceBounds?'] = data['probabilistic_parameters'].pop('nsResourceBounds')
            json.dump(data, f, indent=4)
