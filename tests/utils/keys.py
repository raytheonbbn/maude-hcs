import pytest
from .context import RunConfig

run_cfg_key = pytest.StashKey[RunConfig]()