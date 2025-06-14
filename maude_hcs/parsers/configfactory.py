from enum import Enum
from pathlib import Path

from maude_hcs.parsers.dnshcsconfig import DNSHCSConfig

class Protocol(Enum):
    """An enumeration for network protocols."""
    DNS = "DNS"
    TCP = "TCP"

def buildHCSConfig(protocol: str, path: Path):
    if protocol.upper() == Protocol.DNS.value:
        return DNSHCSConfig.from_file(path)
    else:
        raise ValueError("Unsupported protocol")


