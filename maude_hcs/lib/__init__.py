from pathlib import Path
import os
from enum import Enum

class Protocol(Enum):
    # singles
    # HTTP = "HTTP"
    # HTTPS = "HTTPS"
    # FTP = "FTP"
    # SSH = "SSH"
    # SMTP = "SMTP"
    NA = "NA"
    DNS = "DNS"
    MASTODON = "MASTODON"
    DESTINI_MASTODON = "DESTINI_MASTODON"
    IODINE_DNS = "IODINE_DNS"
    # composites
    DESTINI_MASTODON_IODINE_DNS = "DESTINI_MASTODON_IODINE_DNS"

class GLOBALS:
    MODULE_NAME = 'HCS_TEST'
    MODEL_TYPES = ['nondet', 'prob']
    MONITOR_ADDRESS = 'monAddr'
    TOPLEVELDIR = Path(os.path.dirname(__file__)).parent.parent