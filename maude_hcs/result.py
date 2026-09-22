from dataclasses import dataclass
from dataclasses_json import dataclass_json

from .query import Query

@dataclass_json
@dataclass
class FeatResult:
    """Stores all the samples taken by a single feature query in a single 
    simulation run, as well as the query itself and calculated stats on the samples."""

    query: Query
    mean: float
    stddev: float
    samples: list[float]

    def __post_init__(self):
        self.samples.sort()

@dataclass_json
@dataclass(frozen=True)
class SimResult:
    """Stores all the feature samples for a single simulation run,
    and some information on the parameters of the run."""

    yaml_filename: str
    baseline_time: int
    run_time: int
    hcs_delay: int
    tgen_delay: int
    no_tgens: bool
    results: dict[str, FeatResult]