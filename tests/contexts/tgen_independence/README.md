# TGEN observable composition suite

This suite compares an N-generator simulation with independently composed
single-generator simulations. It reuses the regression framework's `BuildConfig`,
`TestConfig`, `build()`, isolated `run()` wrapper and SMC runner. Configuration lives
in `experiment.json`; no production-model or runner changes are required.

## Explicit selection

The version-2 configuration selects 18 cases, all at `ixpN`:

| TGEN | Profile | Features |
| --- | --- | --- |
| `dnsTgen` | `normal_1` | `dnsQueryRate`, `dnsQuerySize`, `dnsRespSize` |
| `masTgen` | `normal_1` | `tcpOutPktRate`, `tcpInPktRate`, `tcpPktSize` |
| `ftpTgen` | `medium` | same three TCP features |
| `minTgen` | `medium` | same three TCP features |
| `gorTgen` | `irc_1` | same three TCP features |
| `ircTgen` | `irc_1` | same three TCP features |

Each entry explicitly lists `features` and `vantage_points`, plus its ID, type,
profile, placement network and distinct single/joint seeds. Case IDs have the form
`dns-normal1__dnsTgen__dnsQueryRate__ixpN`. Duplicate IDs or observable selections,
unknown types/features, missing profiles and other vantages are rejected. Known
features without a composition recipe produce an explicit `unsupported` result.
`tcpPktInterarrival` is not selected or implemented.

All entries currently use `client_net_mastodon`. The fixture has no HCS clients and
retains scenario-1 networking and shared services. Each generated arm contains only
the selected source kind. Profiles are copied from scenario 1. Both start delays
are zero, retaining the generator's startup jitter. An experiment-local adapter
restores passive DNS/TCP logging in performance mode and removes the unused
baseline calibration timer. It does not add autonomous monitor user models.

Top-level `window_size` controls the positive integer duration in seconds (default
60), with `window_start` fixed at zero. The scenario, simulation limit, query,
composition and plots all use it. A conflicting `--override-run-time` is rejected.
Set `population` to N (default 2) and `samples` to M (default 5000). Entries sharing
type, profile, network and seeds reuse their two simulation arms; adding features
does not repeat simulation. Suite-wide settings are identical across shared arms.

## Composition and decisions

For each execution group, run NM single-source simulations and M joint simulations.
Read unsorted multi-column `dumps/all_dumps`, retaining columns from the same run
together; the runner's sorted marginal samples cannot preserve that pairing.
Compose consecutive disjoint blocks of N rows, using every row exactly once.

Rates are composed by summing packet counts and dividing by `window_size`. Mean
packet sizes are composed by summing bytes and dividing by summed counts, rather
than averaging per-run means. Direct model queries are checked against these
summary reconstructions on both arms. TCP totals use the model's union of visible
incoming/outgoing packets, avoiding double counting. Legitimate zero windows are
retained; a wholly empty arm produces `inactive`, never a statistical pass.

Choose `method` in the JSON:

- `p-value` (default): two-sided SciPy KS equality test; fail if `pvalue < alpha`,
  otherwise pass. Passing means non-rejection, not proof of independence or
  equivalence. Count-derived distributions have ties, so the continuous-null KS
  p-value calibration is a limitation of this diagnostic.
- `bound`: two DKW bounds and a union bound give a confidence interval for KS
  distance. Pass if its upper bound is below `delta`, fail if its lower bound
  exceeds `delta`, otherwise return `inconclusive`.

Default global alpha is 0.05, delta is 0.05, and multiplicity is `"none"`.
Optional `multiplicity: "bonferroni"` allocates
alpha/K to every configured case (K=18 here), including unsupported/inactive/error
cases. This gives simultaneous bound-mode coverage; p-value false-rejection
control depends on valid underlying p-values. `multiplicity: "none"` uses global
alpha per case and supports only per-case conclusions. Delta only affects bound
mode. Choose budgets and selections before looking at results; do not increase
samples repeatedly until a case passes.

## Running tests

Run from the repository root using the project's Python environment:

```sh
# Helper coverage and real SMC plumbing checks; statistical cases skip by default.
python -m pytest tests/test_tgen_composition_helpers.py tests/test_tgen_independence.py

# Build all six pairs without simulation and preserve the generated files.
python -m pytest tests/test_tgen_independence.py -k smoke --build --persist

# Select FTP and override the JSON duration for a smoke run.
python -m pytest tests/test_tgen_independence.py -k smoke --tgen-type=ftp --window_size=120

# FTP-only statistical diagnostic, with a 120-second window and M=100.
python -m pytest tests/test_tgen_independence.py -k statistical --tgen-statistical --tgen-type=ftp --window_size=120 --tgen-samples=100 --persist --results-dir=/tmp/tgen-results

# Full fixed-budget suite (potentially expensive).
python -m pytest tests/test_tgen_independence.py -k statistical --tgen-statistical --persist --results-dir=/tmp/tgen-results

# Explicit smaller diagnostic campaign; not a full-budget equivalence claim.
python -m pytest tests/test_tgen_independence.py -k statistical --tgen-statistical --tgen-samples=100 --persist --results-dir=/tmp/tgen-results
```

### Command-line options

| Flag | Effect | Default when omitted |
| --- | --- | --- |
| `--tgen-type=ftp` | Filter collected cases and simulations to one TGEN kind. | All entries in `experiment.json`. |
| `--window_size=120` | Override the observation duration, in positive integer seconds, for both arms. | JSON `window_size` (currently 60). |
| `--tgen-samples=100` | Set M for the statistical run: NM single-source simulations and M joint simulations per group. | JSON `samples` (currently 5000); smoke tests always use M=4. |
| `--tgen-statistical` | Enable statistical assertions. | Statistical tests skip. |
| `--build` | Generate models without running simulations. | Build and simulate. |
| `--persist` | Keep generated models and logs. | Temporary builds are cleaned up. |
| `--results-dir=/tmp/tgen-results` | Export reports, samples and plots into a unique run subdirectory. | No separate export. |

Use `--tgen-type=ftp` to select FTP; `--tgen-samples` takes a number, not a type.
Accepted type names are case-insensitive:

| Short name | Canonical kind |
| --- | --- |
| `dns` | `dnsTgen` |
| `mastodon` | `masTgen` |
| `ftp` | `ftpTgen` |
| `minio` | `minTgen` |
| `gorilla` | `gorTgen` |
| `irc` | `ircTgen` |

Unknown types and types absent from the experiment file are rejected. Type filtering
recomputes the statistical family: FTP alone selects three cases, so optional
Bonferroni uses alpha/3. With default multiplicity `"none"`, each case uses alpha.
The window override applies to generation, simulation, queries, composition and
plot labels without modifying the JSON file. A conflicting `--override-run-time`
is rejected.

Each observable has a named pytest result. Module fixtures execute the selected
suite once; `-k` filters assertions, not the experiment selection or alpha family.
Use `--tgen-type` to avoid running other types, and edit `experiments` to change
features or profiles.

Smoke tests accept valid inactive reports as plumbing outcomes. Statistical tests
require `pass` and fail for inactive, unsupported, inconclusive or error results.
A separate real DNS regression checks a fixed 30-second window; it skips when DNS
is excluded or `--window_size` is supplied, so it cannot override your selection.
Build-only tests skip assertions after building. The existing runner timeout and
automatic worker selection (`jobs=0`) apply unchanged. Use these test paths rather
than `--regression` or `--expected`, which select other framework tests.

## Reports

Each execution writes a unique `tgen-composition-*` directory with `report.json`.
The report records configuration, family size/effective alpha, source/library/model
hashes, generation and SMC settings, query manifests and group build paths. Its
`results` mapping contains every case, including failures. A group error affects
that group's cases while later groups still run; a feature error does not suppress
other features.

Raw row JSON files are stored once per group/arm. Per-case sample JSON files retain
joint and composed values. Every statistical comparison gets a UUID-named CDF PNG
beside `report.json`, referenced by `plot_file`. Plots use tight layout, show both
ECDFs and mark the KS location/gap, with p-value, statistic and location in the
title. Inactive/build-only/unsupported/error cases explain absent comparisons.
`--results-dir` copies the report and all referenced JSON/PNG artifacts into its
own run subdirectory. Build paths refer to original temporary directories; use
`--persist` to keep generated models and logs, including after a failed assertion.

## Validation (2026-10-04)

Helper and real-SMC checks passed 47 tests; the 18 opt-in statistical tests
skipped by default. Build-only mode generated all six pairs. The checks used
Matplotlib 3.10.8 (as pinned in the project); the local environment's older version
was supplied a temporary override for Python 3.14 compatibility.

After adding the CLI flags, helper tests plus a real FTP-only run using
`--tgen-type=ftp --window_size=37` passed 39 tests with 4 skipped. Its report
contained only three FTP cases in one shared execution group, and both arms used
the 37-second duration.

The fixed M=100 diagnostic ran all six pairs at 60 seconds, N=2, with the configured
seeds and Bonferroni alpha=0.05/18 (before the default changed to `"none"`).
All direct-feature reconstructions agreed with the model. Outcomes for the three listed features of each kind were:

| Kind | Outcomes |
| --- | --- |
| DNS | pass, pass, pass |
| Mastodon | inactive, inactive, inactive |
| FTP | pass, pass, pass |
| MinIO | inactive, inactive, inactive |
| Gorilla | fail, fail, fail |
| IRC | fail, fail, fail |

The statistical pytest command consequently failed 12 assertions. Inactivity here
means no relevant observed packets in at least one arm; it does not establish that
the kind never emits traffic. These results neither justify actor replacement nor
establish a speedup. The full M=5000 campaign has not been run. This implementation
provides reproducible observable-composition experiments, not an independence proof.
