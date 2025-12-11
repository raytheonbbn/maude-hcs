from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Any, Optional
import math
import yaml
import logging
from maude_hcs.parsers.graph import Topology

logger = logging.getLogger(__name__)


@dataclass
class UnderlyingNetwork:
    server_fqdn: str


@dataclass
class Alice:
    mastodon_user: str
    raceboat_prof_config: str
    raceboat_prof: str


@dataclass
class Bob:
    mastodon_user: str
    raceboat_prof_config: str
    raceboat_prof: str


@dataclass
class Iodine:
    max_query_length: int
    max_response_size: int


@dataclass
class Destini:
    jpeg_covers: str


@dataclass
class Application:
    alice: Alice
    bob: Bob
    iodine: Iodine
    destini: Destini


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
        mastodon_server = data.get('mastodon_server', {})
        return UnderlyingNetwork(
            server_fqdn=mastodon_server.get('server_fqdn', '')
        )

    def _parse_application(self, data: dict) -> Application:
        app_section = data.get('application', {})

        # Alice
        alice_data = app_section.get('alice', {})
        alice = Alice(
            mastodon_user=alice_data.get('mastodon_user', ''),
            raceboat_prof_config=alice_data.get('raceboat_prof_config', ''),
            raceboat_prof=alice_data.get('raceboat_prof', '')
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
        destini_data = app_section.get('destini', {})
        destini = Destini(
            jpeg_covers=destini_data.get('jpeg_covers', '')
        )

        return Application(alice=alice, bob=bob, iodine=iodine, destini=destini)

    def _parse_adversary(self, data: dict) -> Adversary:
        # "Adversary: Baseline and Actual sections"
        # Mapping 'adversary_phase0' to baseline and 'adversary_phase1' to actual
        # based on standard CP2 naming conventions implied in the prompt.
        baseline = data.get('adversary_phase0', {})
        actual = data.get('adversary_phase1', {})

        return Adversary(baseline=baseline, actual=actual)