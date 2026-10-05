from dataclasses import dataclass, asdict
from dataclasses_json import dataclass_json

from .query import Query

@dataclass_json
@dataclass(frozen=True)
class FeatResult:
    """Stores all the samples taken by a single feature query in a single 
    simulation run, as well as the query itself and calculated stats on the samples."""

    query: Query
    mean: float
    stddev: float
    samples: list[float]

    def __post_init__(self) -> None:
        self.samples.sort()

@dataclass_json
@dataclass(frozen=True)
class SimParams:
    """Stores the parameters that determine the exact maude file used in a sim.
    Note that this doesn't contain all the same args taken by generate_cp3, since
    generate_cp3 does more than just create the maude file to be tested."""

    yaml_file:      str
    run_time:       int
    baseline_time:  int = 0
    hcs_delay:      int = 10
    tgen_delay:     int = 1
    no_tgens:       bool = False

@dataclass_json
@dataclass(frozen=True)
class SimResult:
    """Stores the SimParams and all FeatResults for a run."""

    params: SimParams
    results: dict[str, FeatResult]

    # Using asdict on SimResult wouldn't produce a dict with the right shape, so we use a custom method
    def to_dict(self) -> dict:
        ret = asdict(self.params)
        assert "result" not in ret
        ret["result"] = {k: asdict(v) for k, v in self.results.items()}
        return ret