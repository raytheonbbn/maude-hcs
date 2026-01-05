from pathlib import Path
import os
from enum import Enum

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