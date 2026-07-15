from pathlib import Path
import os
from enum import Enum
import collections.abc

class Protocol(Enum):
    # singles
    NA = "na"
    DNS = "dns"
    MASTODON = "mastodon"
    DESTINI_MASTODON = "destini_mastodon"
    IODINE_DNS = "iodine_dns"
    # composites
    DESTINI_MASTODON_IODINE_DNS = "destini_mastodon_iodine_dns"

class GLOBALS:
    MODULE_NAME = 'HCS_TEST'
    MODEL_TYPES = ['nondet', 'prob']
    MONITOR_ADDRESS = 'monAddr'
    TOPLEVELDIR = Path(os.path.dirname(__file__)).parent.parent


def flatten(d, parent_key='', sep='.'):
    """
    Flattens a nested dictionary. Keys from nested dictionaries are
    combined with their parent keys using the specified separator.

    Args:
        d (dict): The dictionary to flatten.
        parent_key (str): The prefix for the current keys (used during recursion).
        sep (str): The separator string to use between nested keys (default is '.').

    Returns:
        dict: A new dictionary with a single level of depth.
    """
    items = []

    for k, v in d.items():
        # Create the new key.
        # If parent_key exists, join it with the current key `k`.
        # Otherwise, just use `k`.

        #new_key = f"{parent_key}{sep}{k}" if parent_key else k
        new_key = k

        # Check if the value is a dictionary (using MutableMapping handles dict and dict-like objects)
        if isinstance(v, collections.abc.MutableMapping):
            # Recursively flatten the nested dictionary and extend our items list
            items.extend(flatten(v, new_key, sep=sep).items())
        else:
            # It's a leaf node, add it to the list
            items.append((new_key, v))

    return dict(items)