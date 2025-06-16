from enum import Enum
from pathlib import Path

from maude_hcs.parsers.dnshcsconfig import DNSHCSConfig

class Protocol(Enum):
    """An enumeration for network protocols."""
    DNS = "DNS"
    TCP = "TCP"

def buildHCSConfig(args, path: Path):
    protocol = args.protocol
    if protocol.upper() == Protocol.DNS.value:        
        # build from run args
        if args.run_args:
            return DNSHCSConfig.from_file(path)
        # build from shadow
        elif args.shadow_filename:
            return DNSHCSConfig.from_shadow(path)
    else:
        raise ValueError("Unsupported protocol")


