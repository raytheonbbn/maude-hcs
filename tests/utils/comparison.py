"""Explicit contracts for fixed-seed smoke and distributional regressions."""
import json
from pathlib import Path
import math
from scipy.stats import ks_2samp


def validate_policy(policy):
    if not isinstance(policy, dict) or policy.get("mode") not in {"smoke", "distribution"}:
        raise ValueError("SMC regression requires comparison.mode: smoke or distribution")
    allowed = {"mode"} if policy["mode"] == "smoke" else {"mode", "delta", "alpha", "min_samples"}
    if set(policy) - allowed:
        raise ValueError(f"Unknown comparison settings: {set(policy) - allowed}")
    if policy["mode"] == "distribution":
        if not 0 < policy.get("delta", 0) < 1 or not 0 < policy.get("alpha", 0) < 1:
            raise ValueError("Distribution comparison requires alpha and delta between 0 and 1")
        if not isinstance(policy.get("min_samples"), int) or policy["min_samples"] < 2:
            raise ValueError("Distribution comparison requires min_samples >= 2")


def compare_smc(obtained, expected, policy):
    validate_policy(policy)
    # Refuse comparisons against legacy/incompatible references. Updating these
    # is an explicit review action, never an automatic migration during testing.
    for data in (obtained, expected):
        assert data.get("schema_version") == 2, "Reference schema changed; review and regenerate the snapshot"
        assert "provenance" in data, "Missing provenance"
    assert obtained.keys() == expected.keys(), "Result metadata keys differ"
    for key in obtained.keys() - {"results", "sample_rows", "run_ids"}:
        assert obtained[key] == expected[key], f"Incompatible metadata: {key}"
    actual, reference = obtained["results"], expected["results"]
    assert actual and actual.keys() == reference.keys(), "Query names differ or no queries returned"
    # Fixed-look family-wise confidence budget across all query comparisons.
    alpha = policy.get("alpha", 0.05) / len(actual)
    for name in actual:
        a, b = actual[name], reference[name]
        assert a["query"] == b["query"], f"Query definition changed: {name}"
        x, y = a["samples"], b["samples"]
        assert x and y and all(math.isfinite(v) for v in x + y), f"Invalid samples: {name}"
        if policy["mode"] == "smoke":
            assert a == b, f"Fixed-seed quantitative result changed: {name}"
        else:
            assert min(len(x), len(y)) >= policy["min_samples"], f"Too few samples for {name}: {len(x)}, {len(y)}"
            distance = float(ks_2samp(x, y).statistic)
            # Two one-sample DKW bounds plus a union bound. A non-significant
            # equality test is not evidence that the distance is below delta.
            margin = sum(math.sqrt(math.log(4 / alpha) / (2 * n)) for n in (len(x), len(y)))
            upper = min(1.0, distance + margin)
            assert upper < policy["delta"], (
                f"{name}: equivalence not established: KS={distance:.6g}, upper={upper:.6g}, "
                f"delta={policy['delta']}, samples=({len(x)}, {len(y)}), query_alpha={alpha:.6g}"
            )
    if policy["mode"] == "smoke":
        assert obtained["sample_rows"] == expected["sample_rows"], "Joint sample rows changed"
        assert obtained["run_ids"] == expected["run_ids"], "Run identifiers changed"


def check_reference(path, *, smc=False, regenerate=False):
    """Do not silently bless a missing or obsolete reference during a normal run."""
    if regenerate:
        return
    path = Path(path)
    if not path.is_file():
        raise AssertionError(f"Missing reference: {path}. Review outputs and use --force-regen explicitly.")
    if smc and json.loads(path.read_text()).get("schema_version") != 2:
        raise AssertionError(f"Legacy SMC reference: {path}. Query identities/provenance changed; review and regenerate explicitly.")
