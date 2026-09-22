from parse import parse
from dataclasses import dataclass
from dataclasses_json import dataclass_json

@dataclass_json
@dataclass(frozen=True)
class Query:
    typ: str # independent or cumulative
    name: str
    start: int
    end: int

    def to_win_str(self):
        return f"t{self.start}_t{self.end}"

    def to_name(self):
        return f"{self.typ}:{self.name}:{self.to_win_str()}"

@dataclass_json
@dataclass(frozen=True)
class IntegrityQuery(Query):
    client: str

@dataclass_json
@dataclass(frozen=True)
class ConfidentialityQuery(Query):
    vantage: str

def parse_query(q: str) -> Query:
    """Parses a Query from a line of quatex produced as in generate_quatex.py, using the comment after the line"""

    comment_only_res = parse("{}; // {}", q)
    assert comment_only_res is not None
    comment_only = comment_only_res[1]

    try_five = parse("{} {} {} {} {}", comment_only)

    if try_five is not None:
        if try_five[1] == "integrity":
            return IntegrityQuery(*try_five)
        else:
            return ConfidentialityQuery(*try_five)

    try_four = parse("{} {} {} {}", comment_only)
    assert try_four is not None
    return Query(*try_four)

def parse_quatex(quatex: str) -> list[Query]:
    return [
        parse_query(line.strip())
        for line in quatex.splitlines()
        if line.strip() is not None
    ]