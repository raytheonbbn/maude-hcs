# TGEN observable composition suite

This suite compares an N-generator simulation with independently composed
single-generator simulations. It reuses the regression framework's `BuildConfig`,
`TestConfig`, `build()`, isolated `run()` wrapper and SMC runner. Configuration lives
in `experiment.json`. The generator supplies shared application-server transports,
and the regression SMC runner validates states and observations before accepting samples.

## Explicit selection

The version-2 configuration selects 54 cases: 18 observables at `ixpN`, each tested
at 60, 120 and 1000 seconds:

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
`dns-normal1__dnsTgen__dnsQueryRate__ixpN__w120s`. Duplicate IDs or observable selections,
unknown types/features, missing profiles and other vantages are rejected. Known
features without a composition recipe produce an explicit `unsupported` result.
`tcpPktInterarrival` is not selected or implemented.

All entries currently use `client_net_mastodon`. The fixture has no HCS clients and
retains scenario-1 networking and shared services. Each generated arm contains only
the selected source kind. Profiles are copied from scenario 1. Both start delays
are zero, retaining the generator's startup jitter. An experiment-local adapter
restores passive DNS/TCP logging in performance mode and removes the unused
baseline calibration timer. It does not add autonomous monitor user models. Mastodon and S3 each have one
shared TCP server whenever an HCS client or corresponding TGEN needs it, including
TGEN-only and mixed configurations.

Top-level `"window_size": [60, 120, 1000]` explicitly lists the durations in
seconds, with `window_start` fixed at zero. Use `[60]` for a single duration.
The list must be nonempty and contain unique positive integers; scalar values,
booleans, duplicates and fractional durations are rejected. Every feature × vantage
point × window size gets a separate pytest case and report result.

Each duration uses separate generated models and simulation runs. The scenario,
simulation limit, queries, composition and plots all use that duration. Entries
sharing type, profile, network, seeds **and duration** reuse their two simulation
arms; adding features does not repeat simulation. The configured seeds are reused
across durations, so results across windows need not be independent. Bonferroni
does not require independence between cases.

Set `population` to N (default 2) and `samples` to M (default 5000), per window.
`--window_size=120` replaces the list with `[120]`. `--override-run-time` is only
accepted if the selected list contains exactly that one duration.

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
alpha/K to every configured case (K=54 here across all windows), including
unsupported/inactive/error cases. This gives simultaneous bound-mode coverage; p-value false-rejection
control depends on valid underlying p-values. `multiplicity: "none"` uses global
alpha per case and supports only per-case conclusions. Delta only affects bound
mode. Choose budgets and selections before looking at results; do not increase
samples repeatedly until a case passes.

## Running tests

Run from the repository root using the project's Python environment:

```sh
# Helper coverage and real SMC plumbing checks; statistical cases skip by default.
python -m pytest tests/test_smc_validation.py tests/test_tgen_composition_helpers.py tests/test_tgen_independence.py

# Build all 18 type/window pairs without simulation and preserve the generated files.
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
| `--window_size=120` | Replace the window list with `[120]` for both arms. | JSON `window_size` (currently `[60, 120, 1000]`). |
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
recomputes the statistical family: FTP alone selects nine cases with the configured three windows, so optional
Bonferroni uses alpha/9. Adding `--window_size=120` selects three cases and alpha/3. With default multiplicity `"none"`, each case uses alpha.
The window override applies to generation, simulation, queries, composition and
plot labels without modifying the JSON file. A conflicting `--override-run-time`
is rejected.

Each observable and window combination has a named pytest result. Module fixtures execute the selected
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
that group's cases while later windows and groups still run; a feature error does
not suppress other features. Group IDs (for example `dns-normal1__w120s`), build
names, raw-row files, sample files, plot files and diagnostic state names include
the duration. The top-level experiment records the window list; each result and
execution group records its own scalar `window_size`.

Local SMC validation rejects a state still wrapped in unresolved `run(...)` and
observations that fail to reduce to finite numeric or Boolean literals. A stuck
simulation is an `error`, even if its query is constant; a completed, genuinely
empty observation can still be `inactive`. Errors record the arm seed, worker/sample
identity, query (when applicable), and diagnostic state. The group's arm metadata
contains `validation_errors`; their relative `state_file` references point to
copies beside the report and are included in exports. Original diagnostics and
logs remain in the build directory when `--persist` is used.

The adapter catches validation errors at the sample boundary so umaudemc's parallel
worker protocol can finish safely, then rejects the entire arm before accepting
any samples. Temporary worker dumps from failed arms are not valid experiment data.

Raw row JSON files are stored once per group/arm. Per-case sample JSON files retain
joint and composed values. Every statistical comparison gets a UUID-named CDF PNG
beside `report.json`, referenced by `plot_file`. Plots use tight layout, show both
ECDFs and mark the KS location/gap, with p-value, statistic and location in the
title. Inactive/build-only/unsupported/error cases explain absent comparisons.
`--results-dir` copies the report and all referenced JSON/PNG artifacts into its
own run subdirectory. Build paths refer to original temporary directories; use
`--persist` to keep generated models and logs, including after a failed assertion.

## Multi-window validation (2026-10-05)

The update passed 46 helper tests, 22 SMC validation tests and nine real DNS smoke
cases across `[60, 120, 1000]`. The helper tests exercise separate generation and
query durations, unique exported artifacts, the full Bonferroni family, CLI
selection, invalid window lists, and continuing after a window fails. The full
54-case statistical campaign was not run as part of this framework update.

## Validation (2026-10-04)

The final helper, generator, validation and real-SMC checks passed 77 tests;
the 18 opt-in statistical tests skipped by default. Earlier build-only validation
generated all six pairs. The checks used
Matplotlib 3.10.8 (as pinned in the project); the local environment's older version
was supplied a temporary override for Python 3.14 compatibility.

After adding the CLI flags, helper tests plus a real FTP-only run using
`--tgen-type=ftp --window_size=37` passed 39 tests with 4 skipped. Its report
contained only three FTP cases in one shared execution group, and both arms used
the 37-second duration.

The original M=100 campaign reported Mastodon and MinIO as inactive. Those six
results were invalid: the TGEN-only models lacked server-side TCP actors, became
stuck, and unresolved Maude observations were converted to zeros. The generator
and validation fixes above address both defects.

Repeating that campaign with M=100, a 60-second window, N=2, the same configured
seeds and the original Bonferroni alpha=0.05/18 yielded:

| Kind | Outcomes for its three configured features |
| --- | --- |
| DNS | pass, pass, pass |
| Mastodon | pass, pass, pass |
| FTP | pass, pass, pass |
| MinIO | pass, pass, pass |
| Gorilla | fail, fail, fail |
| IRC | fail, fail, fail |

All 18 cases produced valid comparisons with no inactive/error outcomes; direct
features agreed with summary reconstructions. The default multiplicity remains
`"none"`; Bonferroni was used explicitly to compare with the original campaign.
These diagnostic passes mean non-rejection, not proof of independence or a speedup.
The full M=5000 campaign has not been run.

Regression coverage includes deliberately missing server actors under parallel
SMC, symbolic observations, literal zeros, shared-server uniqueness for TGEN-only,
HCS-only and mixed populations, fixed-seed request/response exchanges, and bounded
60-second checks of the existing multi-client Mastodon/Skyhook HCS fixtures.
The original 6,030-second HCS regression selection was interrupted after 162 seconds;
its full-duration results are not claimed here.

## Why Gorilla and IRC legitimately fail composition

For the configured `irc_1` profiles and the 60-second window at `ixpN`, the
Gorilla and IRC failures reflect population-dependent chat fan-out. Adding a
second generator also adds a recipient. Summing observations from two isolated
single-generator runs cannot reproduce traffic delivered between those clients.
These are valid `fail` outcomes, distinct from the earlier Mastodon/MinIO false
inactivity caused by missing network-server actors.

Both profiles register clients in the same rooms during initialization. A client
can receive a broadcast even if it sends no chat message within the observation
window. The Gorilla server's `serverBroadcast`/`mkBroadcast` rules deliver to all
registered room members, including the sender; IRC's
`server-handle-incoming-chat`/`createIrcMsg` rules forward to other members and
exclude the sender. These rules are in
`maude_hcs/lib/tgen/maude/gorillachat/gorilla-protocol.maude`,
`maude_hcs/lib/irc/irc_prob-v2.maude`, and
`maude_hcs/lib/irc/common/_aux.maude` (paths relative to the repository root).

Representative packet traces show the additional delivery directly:

| Type | Single-generator run | Two-generator run with one sender active |
| --- | --- | --- |
| IRC | Six client-to-server packets. | Six client-to-server packets plus one server-to-second-client packet: seven total. |
| Gorilla | Six upload packets, an acknowledgement and a self-broadcast: eight total. | The same pattern plus a broadcast to the second client: nine total. |

These counts describe the inspected traces, not fixed counts for every run.
Payload sizes, loss and window boundaries can change packetization. In the
repeated M=100 campaign, the rate KS distance was 0.50 for Gorilla
(p-value approximately 1.00e-11) and 0.49 for IRC (approximately 2.95e-11).
The extra deliveries also change the packet-size mixture, explaining why
`tcpPktSize` fails alongside the rates; its KS distances were 0.43 and 0.48,
respectively. These results used the campaign's Bonferroni alpha=0.05/18.

The outgoing and incoming rate samples coincide in this campaign because the
current `ixpN` visibility rule accepts both directions
(`maude_hcs/lib/common/maude/visibility.maude`). Their identical failures should
therefore not be interpreted as independent evidence.

The conclusion is that the current isolated-run composition recipe fails for
these aggregate network observables. It does not establish dependence between
the generators' random choices: independent sending behavior can still produce
population-dependent network traffic through server fan-out. Keep these cases
as failures. A future decomposition would need to preserve the recipient
population or explicitly reconstruct broadcast deliveries and their transport
behavior, then test that revised composition rule separately.
