from dataclasses import dataclass
from dataclasses_json import dataclass_json

@dataclass_json
@dataclass
class IpAddress:
    octets: list[int]

@dataclass_json
@dataclass
class Address:
    name: str   # Variable name for this address in Maude
    maude: str  # Maude code to construct this address
    ip: IpAddress | None = None