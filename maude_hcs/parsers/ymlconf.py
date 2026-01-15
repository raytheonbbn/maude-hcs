import json
from dataclasses import dataclass, field
from fileinput import filename
from typing import List, Tuple, Dict, Any, Optional
import math
import re

from dataclasses_json import dataclass_json
import yaml
import logging
from pathlib import Path

from maude_hcs import PROJECT_TOPLEVEL_DIR
from maude_hcs.parsers.graph import Topology
from maude_hcs.parsers.markovJsonToMaudeParser import find_and_load_json
from maude_hcs.parsers.protocolconfig import XFile

logger = logging.getLogger(__name__)

@dataclass_json
@dataclass
class UnderlyingNetwork:
    server_fqdn: str
    server_address: str

@dataclass_json
@dataclass
class Alice:
    mastodon_user: str
    raceboat_prof_config: str
    raceboat_prof: str
    hashtags: List[str]
    xfiles: List[XFile]

@dataclass_json
@dataclass
class Bob:
    mastodon_user: str
    raceboat_prof_config: str
    raceboat_prof: str

@dataclass_json
@dataclass
class Iodine:
    max_query_length: int
    max_response_size: int

@dataclass_json
@dataclass
class CoverImage:
    name: str
    capacity_bytes: int
    size_bytes: int

    def to_maude(self, image_id: int) -> str:
        """
        Generates the Maude term for a single image.
        Format: image(id, size_bytes, capacity_bytes)
        """
        return f"image({image_id}, {self.size_bytes}, {self.capacity_bytes})"

@dataclass_json
@dataclass
class Destini:
    jpeg_covers: list[CoverImage] = field(default_factory=list)

    def save(self, file_path: str):
        """
        Exports the dataclass instance to a JSON file.

        Args:
            file_path: The path where the JSON file will be saved.
        """
        with open(file_path, 'w') as f:
            # Convert the dataclass to a dict, then handle the special key name
            data = self.to_dict()
            json.dump(data, f, indent=4)

    @staticmethod
    def from_file(file_path: str) -> 'Destini':
        with open(file_path, 'r') as f:
            data = json.load(f)
        return Destini.from_dict(data)

    def to_maude(self, identifier) -> str:
        """
        Generates the Maude code for the list of images.

        Process:
        1. Creates a map (imageNameMap) from str to Nat to capture name-to-id mappings.
        2. Generates the ByteSeqL string using the associative constructor '::'.
        3. Returns the Maude op and eq definitions for both the map and the list.
        """
        image_name_map: Dict[str, int] = {}
        maude_terms: List[str] = []
        next_id = 1

        for cover in self.jpeg_covers:
            # 1. Create/Retrieve mapping from name to ID
            if cover.name not in image_name_map:
                image_name_map[cover.name] = next_id
                next_id += 1

            # Get the ID for this specific image name
            current_id = image_name_map[cover.name]

            # Generate the term: image(id, size, capacity)
            maude_terms.append(cover.to_maude(current_id))

        # 2. Generate the ByteSeqL
        # Using the associative constructor '::'.
        # If the list is empty, we default to 'nilBS' (the identity element).
        if not maude_terms:
            rhs = "nilBS"
        else:
            rhs = " :: ".join(maude_terms)

        # 3. Generate the Map body
        # Standard Maude Map syntax: "key" |-> value
        map_parts = []
        for name, pid in image_name_map.items():
            map_parts.append(f'"{name}" |-> {pid}')

        if not map_parts:
            map_rhs = "empty"
        else:
            # Using comma as separator for standard Map{String, Nat}
            map_rhs = "(" + ", ".join(map_parts) + ")"

        # 4. Construct the final Maude code
        lines = []
        map_name = f'{identifier}-map'
        # lines.append(f"op {map_name} : -> " + "Map{String, Nat} .")
        # lines.append(f"eq {map_name} = {map_rhs} .")

        lines.append("")
        lines.append(f"op {identifier} : -> ByteSeqL .")
        lines.append(f"eq {identifier} = {rhs} .")
        lines.append("\n")

        return "\n".join(lines)

@dataclass_json
@dataclass
class Application:
    alice: Alice
    bob: Bob
    iodine: Iodine
    destini: Destini


@dataclass_json
@dataclass
class Adversary:
    baseline: Dict[str, Any] = field(default_factory=dict)
    actual: Dict[str, Any] = field(default_factory=dict)
    router_pre_nat: Dict[str, Any] = field(default_factory=dict)
    router_post_nat: Dict[str, Any] = field(default_factory=dict)
    baseline_bins: Dict[str, Any] = field(default_factory=dict)

    def render_template(self, start_time:float = 0) -> Dict[str, Any]:
        """
        Creates the input dictionary for QuatexGenerator.generate_file.
        Maps the script parameters from the YAML structure to the short codes expected by the generator.
        """
        # Mapping from Generator Keys -> YAML Script Names for Moving Averages
        key_map = {
            'qps': 'moving_average/average_dns_query_rate',
            'qsize': 'moving_average/average_dns_query_size',
            'respsize': 'moving_average/average_dns_response_size',
            'uploadrate': 'moving_average/average_https_upload_rate'
        }

        config = {}
        config['start_time'] = start_time  # Default start time

        # --- Process Moving Averages (Post-NAT) ---
        scripts = self.router_post_nat.get('scripts', [])

        # Create a lookup map for easy access by script name
        script_params_map = {}
        for script in scripts:
            name = script.get('name')
            params = script.get('params', {})
            if name:
                script_params_map[name] = params

        for gen_key, yaml_name in key_map.items():
            if yaml_name in script_params_map:
                params = script_params_map[yaml_name]

                # Clean 's' parameter (e.g., "10secs" -> 10)
                s_raw = params.get('s')
                s_val = s_raw
                if isinstance(s_raw, str):
                    # Extract digits
                    match = re.match(r"(\d+(\.\d+)?)", s_raw)
                    if match:
                        s_val = float(match.group(1)) if '.' in match.group(1) else int(match.group(1))

                config[gen_key] = {
                    'k': float(params.get('k')),
                    'n': params.get('n'),
                    's': float(s_val),
                    'm': float(params.get('m'))
                }

        # --- Process Cumulative Thresholds (Pre & Post NAT) ---
        # Helper to get params for a script name from a list of scripts
        def get_script_params(scripts_list, script_name):
            for script in scripts_list:
                if script.get('name') == script_name:
                    return script.get('params', {})
            return {}

        pre_nat_scripts = self.router_pre_nat.get('scripts', [])
        post_nat_scripts = self.router_post_nat.get('scripts', [])

        # Map: Generator Key -> (IsPreNat, Script Name, Param Name)
        cumulative_map = {
            'N_query_pre_nat': (True, 'cumulative/dns_query_count', 'dns_q_threshold'),
            'N_query_post_nat': (False, 'cumulative/dns_query_count', 'dns_q_threshold'),
            'N_query_size_pre_nat': (True, 'cumulative/dns_query_bytes', 'dns_byte_threshold'),
            'N_query_size_post_nat': (False, 'cumulative/dns_query_bytes', 'dns_byte_threshold'),
            'N_response_pre_nat': (True, 'cumulative/dns_response_bytes', 'dns_resp_byte_threshold'),
            'N_response_post_nat': (False, 'cumulative/dns_response_bytes', 'dns_resp_byte_threshold'),
            'N_http_conn_pre_nat': (True, 'cumulative/https_connection_count', 'https_conn_threshold'),
            'N_http_conn_post_nat': (False, 'cumulative/https_connection_count', 'https_conn_threshold'),
            'N_http_upload_pre_nat': (True, 'cumulative/https_upload_bytes', 'https_upload_byte_threshold'),
            'N_http_upload_post_nat': (False, 'cumulative/https_upload_bytes', 'https_upload_byte_threshold')
        }

        for gen_key, (is_pre, script_name, param_key) in cumulative_map.items():
            target_scripts = pre_nat_scripts if is_pre else post_nat_scripts
            params = get_script_params(target_scripts, script_name)
            val = params.get(param_key)
            if val is not None:
                config[gen_key] = val

        return config

    def getMaxWindowSize(self, key:str) -> float:
        """
        Computes the max value of s*n or s*m across all groups in the config.router_post_nat.
        Returns:
            float: The maximum window size.
        """
        assert key in ['m', 'n'], f"Key {key} is not valid. Must be 'm' or 'n'."
        max_w = 0.0
        scripts = self.router_post_nat.get('scripts', [])

        for script in scripts:
            params = script.get('params', {})
            s_raw = params.get('s')
            n_raw = params.get(key)

            # Only proceed if both s and m parameters exist
            if s_raw is not None and n_raw is not None:
                s_val = 0.0

                # Parse s (handle "10secs" string format or raw numbers)
                if isinstance(s_raw, (int, float)):
                    s_val = float(s_raw)
                elif isinstance(s_raw, str):
                    match = re.match(r"(\d+(\.\d+)?)", s_raw)
                    if match:
                        s_val = float(match.group(1))

                # Parse n
                try:
                    n_val = float(n_raw)

                    # Compute s * n
                    w = s_val * n_val
                    if w > max_w:
                        max_w = w
                except (ValueError, TypeError):
                    continue

        return max_w

class YmlConf:
    """
    Parses the system configuration YAML file into structured objects.
    """

    def __init__(self, yml_path: str):
        self.yml_path = yml_path

        # 1. Load the raw YAML
        with open(yml_path, 'r') as f:
            self.data = yaml.safe_load(f)

        # 2. Network Topology (Topology.from_yml)
        self.network = Topology.from_yml(yml_path)

        # 3. Background Traffic (TGEN)
        self.background_traffic: List[Tuple[str, str, int]] = self._parse_tgen(self.data)

        # 4. Underlying Network
        self.underlying_network: UnderlyingNetwork = self._parse_underlying(self.data)

        # 5. Application
        self.application: Application = self._parse_application(self.data)

        # 6. Adversary
        self.adversary: Adversary = self._parse_adversary(self.data, self.yml_path)

    def _parse_tgen(self, data: dict) -> List[Tuple[str, str, int]]:
        """
        Parses tgen_clients section.
        Returns a list of tuples: (type, profile_json, num_actors)
        """
        tgen_configs = []
        clients_section = data.get('tgen_clients', {})
        configs = clients_section.get('configs', {})

        for config_name, config_data in configs.items():
            total_actors = config_data.get('total', 0)
            tgen_type = config_data.get('type', 'unknown')
            profiles = config_data.get('profiles', {})

            # Temporary storage to handle the rounding logic
            calculated_profiles = []

            # Iterate through profiles to calculate counts
            for profile_key, profile_data in profiles.items():
                json_file = profile_data.get('profile')
                # read json and get the params dictionary
                percent = profile_data.get('percent', 0)

                # Formula: ceil(percent * total / 100)
                # Note: 'percent' in yaml is typically 30 for 30%, not 0.3
                count = math.ceil((percent * total_actors) / 100.0)
                calculated_profiles.append({
                    'type': tgen_type,
                    'json': json_file,
                    'count': count
                })

            # Adjustment Logic:
            # "Reduce the last section as needed to match total"
            current_sum = sum(p['count'] for p in calculated_profiles)

            if current_sum != total_actors and calculated_profiles:
                # If we have overshot or undershot, adjust the LAST profile
                # The requirement specifically says "reduce the last section as needed"
                # implying we might have overshot due to ceil()
                diff = current_sum - total_actors
                last_profile = calculated_profiles[-1]

                # Adjust count, ensuring we don't go negative
                new_count = max(0, last_profile['count'] - diff)
                last_profile['count'] = new_count

            # Final check to ensure we match total exactly (if required strictly)
            # or just append what we have calculated.
            for p in calculated_profiles:
                if p['count'] > 0:
                    tgen_configs.append((p['type'], p['json'], p['count']))
        return tgen_configs

    def _parse_underlying(self, data: dict) -> UnderlyingNetwork:
        ADDR = 'mastodon_server'
        mastodon_server = data.get(ADDR, {})
        fqdn = mastodon_server.get('server_fqdn', '') + '.'
        return UnderlyingNetwork(
            server_fqdn=fqdn,
            server_address=ADDR
        )

    def _parse_application(self, data: dict) -> Application:
        app_section = data.get('application', {})

        # Alice
        alice_data = app_section.get('alice', {})
        alice = Alice(
            mastodon_user=alice_data.get('mastodon_user', ''),
            raceboat_prof_config=alice_data.get('raceboat_prof_config', ''),
            raceboat_prof=alice_data.get('raceboat_prof', ''),
            hashtags=[],
            xfiles=[] # TODO fix when in yml conf
        )

        # Bob
        bob_data = app_section.get('bob', {})
        bob = Bob(
            mastodon_user=bob_data.get('mastodon_user', ''),
            raceboat_prof_config=bob_data.get('raceboat_prof_config', ''),
            raceboat_prof=bob_data.get('raceboat_prof', '')
        )

        # Iodine
        iodine_data = app_section.get('iodine', {})
        iodine = Iodine(
            max_query_length=iodine_data.get('max_query_length', 0),
            max_response_size=iodine_data.get('max_response_size', 0)
        )

        # Destini
        # These params are static/hardcoded
        destini = self.load_destini_from_json()

        return Application(alice=alice, bob=bob, iodine=iodine, destini=destini)

    def _parse_adversary(self, data: dict, ymlpath: str) -> Adversary:
        baseline = data.get('adversary_phase0', {})
        actual = data.get('adversary_phase1', {})

        # Populate pre/post nat
        vantage_points = actual.get('vantage_points', {})
        router_pre_nat = vantage_points.get('router_pre_nat', {})
        router_post_nat = vantage_points.get('router_post_nat', {})

        # get adversary bins if they exist
        # first get the filename for the bins
        filename = None
        baseline_bin_data = {}
        scripts = router_post_nat.get('scripts', [])
        for script in scripts:
            name = script.get('name')
            params = script.get('params', {})
            if name == 'bin_loader':
                filename = params['json_path']
                break
        if filename:
            f = Path(ymlpath).parent.joinpath('zeek').joinpath(filename[1:])
            try:
                baseline_bin_data = find_and_load_json(f.parent, f.parts[-1])
            except:
                logger.warning(f'Failed to load baseline bin data from {f}')

        return Adversary(
            baseline=baseline,
            baseline_bins=baseline_bin_data,
            actual=actual,
            router_pre_nat=router_pre_nat,
            router_post_nat=router_post_nat
        )

    def load_destini_from_json(self) -> Destini:
        """
        Parses a JSON file and creates a Destini object.
        """
        json_content = find_and_load_json(PROJECT_TOPLEVEL_DIR, 'destini_covers.json')
        # from_json() is provided by the @dataclass_json decorator
        return Destini.from_dict(json_content)

def parse_destini(input_directory: str) -> str:
    """
    Scans a directory for files, creates CoverImage objects, builds a Destini object,
    and returns its JSON string representation.

    Args:
        input_directory (str): Path to the directory containing cover images.

    Returns:
        str: The JSON string representation of the Destini object.
    """
    input_path = Path(input_directory)
    if not input_path.is_dir():
        raise NotADirectoryError(f"The input path {input_directory} is not a valid directory.")

    cover_images = []

    # Iterate over all files in the directory
    for file_path in input_path.iterdir():
        if file_path.is_file():
            # Create CoverImage object
            # name is file stem (filename without extension)
            # size is file size in bytes
            # capacity is hardcoded to 3000 as requested
            image = CoverImage(
                name=file_path.stem,
                capacity_bytes=3000,
                size_bytes=file_path.stat().st_size
            )
            cover_images.append(image)

    # Create Destini object
    return Destini(jpeg_covers=cover_images)