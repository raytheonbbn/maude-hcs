# DNS observable composition experiment

This ports the experiment from commit `1854979` onto `tgen-scaling`. It uses the
current regression framework's `BuildConfig`, `TestConfig`, `build()` and isolated
`run()` wrapper with the existing SMC runner. No runner, snapshot comparison or
process-management changes are needed. The two CLI options only select this
experiment and its fixed sample budget.

The fixture retains scenario 1 networking and the DNS `normal_1` profile, with
no HCS clients. One arm has one generator in `client_net_mastodon`; the other has
two. Both use the same source fixture, frozen before either build. Generation
explicitly sets both start delays to zero, retaining its small startup jitter.
Shared DNS infrastructure remains in the model, including any interactions it
introduces.

The observable is aggregate `dnsQueryRate` at `cl[1]` over 0–60 seconds, using
existing `compObsFeatureX` visibility semantics. Performance mode omits baseline
collection; a guarded experiment-local adapter restores passive DNS logging and
removes the unused calibration timer. It does not change the production model.
A conflicting `--override-run-time` is rejected.

For M comparisons, run 2M single-source simulations and M joint simulations,
with distinct seeds and the runner’s automatic worker selection (`jobs=0`). Read the runner's `dumps/all_dumps` in run
order: its returned marginal samples are sorted and must not be used for pairing.
Sum disjoint consecutive pairs, consuming every single-source run once. Recover
integer counts before adding and dividing by 60 to avoid floating-point differences
between equivalent discrete rates. Keep empty windows; reject entirely inactive
arms, malformed dumps and incorrect sample counts.

Choose `"method": "p-value"` (default) or `"method": "bound"` in `experiment.json`.
The helper also accepts `ks_equivalence(x, y, delta=.05, alpha=.05, method='bound')`.

- `p-value`: use the two-sided SciPy KS equality-test p-value. Reject equality and
  fail when `pvalue < alpha`; otherwise pass. This means equality was not rejected,
  not that equivalence was established. SciPy's usual KS p-value calibration assumes
  continuous distributions; these count-derived rates have ties, so this mode is
  a diagnostic rather than the previous distribution-free equivalence guarantee.
- `bound`: retain the fixed-look KS distance interval from two DKW bounds and a
  union bound. Pass when the upper bound is below delta, fail when the lower bound
  exceeds delta, otherwise return inconclusive (which fails the pytest assertion).

Defaults are M=5000, delta=0.05, alpha=0.05. Delta affects only bound-mode decisions.
A small smoke test makes no equivalence claim. Do not repeatedly increase the
sample budget until a comparison passes.

Each completed comparison produces a uniquely named `dns-cdfs-<uuid>.png` beside
`report.json`, referenced by its `plot_file` field. The plot shows both ECDFs,
the KS location and gap, and a title with the p-value, statistic and location.
Both modes report these KS diagnostics as JSON scalars. `--results-dir` exports
the PNG alongside the copied JSON so the filename reference remains valid.

Run from the repository root with the project's Python environment:

```sh
# Helper tests and a real generator/SMC smoke test; full experiment skips by default.
python -m pytest tests/test_tgen_composition_helpers.py tests/test_tgen_independence.py

# Prepare both populations without simulation; preserve generated models.
python -m pytest tests/test_tgen_independence.py -k smoke --build --persist

# Full fixed-budget statistical experiment (potentially expensive).
python -m pytest tests/test_tgen_independence.py -k observable --tgen-statistical --persist --results-dir=/tmp/dns-composition-results

# Smaller diagnostic budget (bound mode cannot establish equivalence at M=100).
python -m pytest tests/test_tgen_independence.py -k observable --tgen-statistical --tgen-samples=100 --persist --results-dir=/tmp/dns-composition-results
```

Use direct test paths and `-k` to select these paired experiments, rather than
`--regression` or `--expected` (which select the framework's snapshot/configured
assertion tests). The existing execution wrapper's timeout applies unchanged.
`--persist` retains builds and logs; without it the current framework removes its
temporary directory even after failure. `--results-dir` saves a separate JSON
report with scenarios, generation/SMC settings, model hashes, ordered rates,
composed samples, means/variances and the distance interval. Build-only and error
reports are also written. Report paths are logged.

A bound-mode pass supports observable distributional composition for this fixture.
A p-value-mode pass only means the equality null was not rejected.
It does not prove independence, justify other populations or HCS configurations,
or establish a rewriting speedup. This implementation does not replace actors.

## Validation on tgen-scaling (2026-09-30)

The helper and real-SMC smoke selection passed 17 tests; the opt-in statistical
test skipped by default. Build-only mode generated both arms. The M=100 diagnostic
ran 200 single-source and 100 joint simulations in about 19 seconds and returned
inconclusive (KS=0.10, upper bound=0.39604), correctly failing the equivalence
assertion. Report export was verified. The full M=5000 experiment was not rerun;
these checks establish working execution, not statistical equivalence.
