from parse import parse
from dataclasses import dataclass, field
from dataclasses_json import dataclass_json, config

def net_name_to_alice(name: str) -> str:
    match name:
        case "masCl1IrcAddr" | "iodCl1IrcAddr" | "obfsCl1IrcAddr" | "skyCl1IrcAddr" | "wtCl1IrcAddr":
            return "alice_1"
        case "masCl2IrcAddr" | "iodCl2IrcAddr" | "obfsCl2IrcAddr" | "skyCl2IrcAddr" | "wtCl2IrcAddr":
            return "alice_2"
        case _:
            raise RuntimeError("Unrecognized client name")

@dataclass_json
@dataclass(frozen=True)
class Query:
    type: str = field(metadata=config(field_name="type")) # independent or cumulative
    feat: str
    start: int
    end: int

    def to_win_str(self):
        return f"t{self.start}_t{self.end}"

    def to_name(self):
        return f"{self.type}:{self.feat}:{self.to_win_str()}"

@dataclass_json
@dataclass(frozen=True)
class ClientIntegrityQuery(Query):
    client: str

    def to_name(self):
        return f"{self.type}:{self.feat}:{net_name_to_alice(self.client)}:{self.to_win_str()}"

@dataclass_json
@dataclass(frozen=True)
class ConfidentialityQuery(Query):
    vantage: str
    
    def to_name(self):
        return f"{self.type}:{self.feat}:{self.vantage}:{self.to_win_str()}"

def parse_query(q: str) -> Query:
    """Parses a Query from a line of quatex produced as in generate_quatex.py, using the comment after the line"""

    comment_only_res = parse("{}; // {}", q)
    assert comment_only_res is not None
    comment_only = comment_only_res[1]

    try_five = parse("{} {} {} {} {}", comment_only)

    if try_five is not None:
        if try_five[1] == "integrity":
            return ClientIntegrityQuery(*try_five)
        else:
            return ConfidentialityQuery(*try_five)

    try_four = parse("{} {} {} {}", comment_only)
    assert try_four is not None
    return Query(*try_four)

def parse_quatex(quatex: str) -> list[Query]:
    return [
        parse_query(line.strip())
        for line in quatex.splitlines()
        if line.strip()
    ]