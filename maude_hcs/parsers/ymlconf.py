import json
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional
import math

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
    baseline: Dict[str, Any]
    actual: Dict[str, Any]


class YmlConf:
    """
    Parses the system configuration YAML file into structured objects.
    """

    def __init__(self, yml_path: str):
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
        self.adversary: Adversary = self._parse_adversary(self.data)

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

    def _parse_adversary(self, data: dict) -> Adversary:
        # "Adversary: Baseline and Actual sections"
        # Mapping 'adversary_phase0' to baseline and 'adversary_phase1' to actual
        # based on standard CP2 naming conventions implied in the prompt.
        baseline = data.get('adversary_phase0', {})
        actual = data.get('adversary_phase1', {})

        return Adversary(baseline=baseline, actual=actual)

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