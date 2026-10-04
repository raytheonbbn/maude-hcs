# Generalized TGEN observable composition experiments

Status: implemented 2026-10-04. The version-2 experiment file selects all 18
cases below. See README.md for commands, report layout and validation results.
The implementation reuses the existing generator, build and SMC execution paths.

The implementation also fixes shared Mastodon/S3 TCP server generation for
TGEN-only and multi-client configurations. Local regression SMC rejects stuck
states and unresolved observations, preserving diagnostic states with the report.
The earlier Mastodon/MinIO inactivity results are invalidated; see README.md for
the repeated campaign and regression coverage.

## Objective and scope

For each explicitly configured combination `{tgen_type, feature, vantage}`, compare
jointly simulated contributions with independently composed contributions. Produce
one uniquely named result per combination, including its decision method, outcome,
statistics and CDF plot. Use only `ixpN` in the expanded suite, including the DNS
case `{dnsTgen, dnsQueryRate, ixpN}`. The earlier client-vantage experiment remains
historical validation, not an additional selected case.

Cover all six traffic-producing kinds supported by `generate_cp3.py`: `dnsTgen`,
`masTgen`, `ftpTgen`, `minTgen`, `gorTgen`, and `ircTgen`. Mastodon/MinIO monitors
are supporting actors, not additional source kinds; the generator excludes monitor
entries when interpreting TGEN populations. Keep required monitors and shared
servers as appropriate for each source kind.

Start with one fixed profile, one placement network, populations 1 and 2, and a
configurable observation duration per suite (60 seconds by default). No HCS clients. Keep the scenario-1 network and
shared services intact: coupling through DNS, application servers, subscriptions,
queues, loss or shared state is part of the experiment, not something to remove.
Passing one observable does not imply independence or composability of another,
or of another profile, population, topology or time window.

## Experiment file: explicit features and vantage points

Migrate `experiment.json` to a versioned suite description. Selection lives entirely
in this file. Registries describe how to execute a selected feature/type; they must
not silently add features, vantages or kinds. No wildcard or inferred-route selection.

`window_size` is a positive integer duration in seconds, not a hard-coded constant.
The example retains 60; setting it to 30 or 120 changes the observation window to
[0, 30] or [0, 120]. Keep `window_start` at zero for this iteration. Use this single
configured duration for both arms' generated scenario/run limits, analysis window,
QuaTEx expressions and query identities, count-to-rate conversions, composition,
report metadata and plot labels. Reject conflicting run-time overrides. Freeze the
duration before sampling and compare only results with matching windows. Test a
non-default duration end to end and reject zero, negative or non-integer values.

Configured starting matrix (profile files copied from scenario 1 into this context):

```json
{
  "schema_version": 2,
  "scenario": "scenario1",
  "scenario_file": "scenario.yaml",
  "window_start": 0,
  "window_size": 60,
  "population": 2,
  "samples": 5000,
  "method": "p-value",
  "alpha": 0.05,
  "delta": 0.05,
  "multiplicity": "none",
  "experiments": [
    {
      "id": "dns-normal1",
      "tgen_type": "dnsTgen",
      "profile": "normal_1",
      "network": "client_net_mastodon",
      "single_seed": 105,
      "joint_seed": 106,
      "features": ["dnsQueryRate", "dnsQuerySize", "dnsRespSize"],
      "vantage_points": ["ixpN"]
    },
    {
      "id": "mastodon-normal1",
      "tgen_type": "masTgen",
      "profile": "normal_1",
      "network": "client_net_mastodon",
      "single_seed": 205,
      "joint_seed": 206,
      "features": ["tcpOutPktRate", "tcpInPktRate", "tcpPktSize"],
      "vantage_points": ["ixpN"]
    },
    {
      "id": "ftp-medium",
      "tgen_type": "ftpTgen",
      "profile": "medium",
      "network": "client_net_mastodon",
      "single_seed": 305,
      "joint_seed": 306,
      "features": ["tcpOutPktRate", "tcpInPktRate", "tcpPktSize"],
      "vantage_points": ["ixpN"]
    },
    {
      "id": "minio-medium",
      "tgen_type": "minTgen",
      "profile": "medium",
      "network": "client_net_mastodon",
      "single_seed": 405,
      "joint_seed": 406,
      "features": ["tcpOutPktRate", "tcpInPktRate", "tcpPktSize"],
      "vantage_points": ["ixpN"]
    },
    {
      "id": "gorilla-irc1",
      "tgen_type": "gorTgen",
      "profile": "irc_1",
      "network": "client_net_mastodon",
      "single_seed": 505,
      "joint_seed": 506,
      "features": ["tcpOutPktRate", "tcpInPktRate", "tcpPktSize"],
      "vantage_points": ["ixpN"]
    },
    {
      "id": "irc-irc1",
      "tgen_type": "ircTgen",
      "profile": "irc_1",
      "network": "client_net_mastodon",
      "single_seed": 605,
      "joint_seed": 606,
      "features": ["tcpOutPktRate", "tcpInPktRate", "tcpPktSize"],
      "vantage_points": ["ixpN"]
    }
  ]
}
```

Each entry expands to its explicit `features × vantage_points` Cartesian product.
This matrix has 18 observable cases: three DNS and three for each of the five TCP
kinds. DNS retains `dnsQueryRate`, `dnsQuerySize`, and `dnsRespSize`. TCP uses only
`tcpOutPktRate`, `tcpInPktRate`, and `tcpPktSize`. Every entry
explicitly selects `["ixpN"]`; no client or service-network vantage is selected.
Reject duplicate full case identities rather than running or overwriting them twice.

Validate the special `ixpN` against the generated model's actual visibility rules
for each TGEN. Keep the placement network (`client_net_mastodon`) unchanged: where
a TGEN runs is distinct from where traffic is observed. Do not substitute another
vantage if IXP observations are inactive, or reinterpret packet direction.

During migration, accept the old single-DNS JSON through a small normalization
adapter for explicitly requested legacy runs, or migrate it and its tests atomically.
Do not append the legacy vantage to the new IXP-only matrix. Keep one normalized
internal representation. Omitted `method` continues to default to `p-value`.

## Stable names and result identity

Use the readable combination name `dnsTgen__dnsQueryRate__ixpN` for the DNS
query-rate triple. Report `tgen_type`, `feature`, and `vantage` separately as structured fields.
For additional profiles/placements, define the full case ID as
`<experiment-id>__<tgen-type>__<feature>__<vantage>`, for example
`dns-normal1__dnsTgen__dnsQueryRate__ixpN`.

Validate unique experiment IDs and unique `(type, profile, network, window,
population, feature, vantage)` configurations. Use the full ID as the report key
and pytest display ID where practical. Store window, profile, network, population,
model/input hashes and method in the record; the readable name alone is not a
certificate for other settings. Keep stable case IDs separate from execution UUIDs.
For filenames use an unambiguous escaped case ID plus UUID; check escaping collisions.

## Composition rules: reuse sufficient statistics

Use the existing aggregate `compObsFeatureX` semantics, not the per-flow ECDF
pipeline. A feature registry declares observation source, required query columns,
units, reconstruction rule and validity/activity checks.

| Features | Required single-run summary | Composition for N sources |
|---|---|---|
| `dnsQueryRate` | DNS query count | Sum counts, divide by window duration |
| `tcpOutPktRate`, `tcpInPktRate` | Corresponding visible packet count | Sum counts, divide by duration |
| `dnsQuerySize`, `dnsRespSize` | Paired DNS byte total and matching message count | Sum bytes / sum counts |
| `tcpPktSize` | Paired TCP byte total and packet count using the model's exact selector | Sum bytes / sum counts |

Select `getTsML(getAdversary(C))` for DNS and `getTsPL(getAdversary(C))` for TCP.
Reuse the model's count/size operators where available. Verify TCP mean-size packet
selection against `meanPktSize`; do not assume an arbitrary upload/download sum
has identical semantics. Preserve existing zero-denominator conventions and record
empty-window counts. Never average source means.

Keep DNS rate rounding through integer counts using the configured duration. Apply
integer reconstruction only to actual count/byte summaries, not arbitrary floats.
Do not extend the current blanket nonnegative check to observables whose valid
domain might differ. Every recipe should declare its domain explicitly.

`tcpPktInterarrival` is out of scope for this iteration.
Defer `tcpPktSizeStdDev` until matching count/sum/sum-of-squares semantics are
verified. Defer `tcpDirectionChange` until ordered event composition is supported. Defer `tcpActiveFlow` and `tcpNewCnx` until cross-source
flow identity, address renaming, deduplication and lifetime semantics are checked.
Selecting these before support exists must produce `unsupported`, never use an
additive fallback. The proposed first matrix intentionally excludes them.

## Shared execution pipeline

Refactor the experiment helper rather than adding a new runner or changing ordinary
regression comparison rules:

1. Normalize and validate the file; enumerate and name all requested cases before
   expensive work. Freeze the fixture and resolve each chosen profile and dependency.
2. A small TGEN adapter registry maps kind to YAML key, profile directory/converter,
   expected actor family and required supporting assets. DNS and Mastodon use v1
   profiles; FTP, MinIO, Gorilla and IRC use v2. Reuse `BuildConfig` conversion.
3. Generalize `prepare_arm()` to replace the fixture's TGEN block with exactly the
   requested kind/profile/network and quantity. Preserve `nodes: {}` and common
   infrastructure. Build one single-source and one joint configuration per distinct
   kind/profile/network/window/population group, not once per observable.
4. Generalize `install_observation()` to emit all requested query columns for that
   group, including deduplicated sufficient statistics and activity counts. Retain
   the guarded no-baseline/passive-observer adapter for both DNS and TCP logging.
5. Reuse the framework's existing isolated `run()` and SMC runner. For N-source
   composition run NM single-source simulations and M joint simulations. Start at
   N=2; validate N rather than keeping implicit hard-coded pairs.
6. Generalize `read_rates()` to a raw-row reader validating the exact expected row
   and column counts. Read `dumps/all_dumps`, not the runner's sorted marginals.
   Use a deterministic query-column manifest, saved with the report. Group disjoint
   N-row blocks and apply the same grouping across every column of a run.
7. For each named observable, reconstruct a joint-arm scalar and a composed scalar
   with the same recipe. Where possible also query the direct model feature and
   verify that joint-summary reconstruction matches it run by run.
8. Reuse `ks_equivalence()` once per case, then generalize `plot_cdfs()` labels to
   show kind, feature, vantage, units, window, sample counts and method. Retain the
   p-value, statistic, location, marked gap, tight layout and unique filename.
9. Save every case result and plot, then evaluate test assertions. A failed first
   case must not prevent later case reports or subsequent TGEN groups from running.

The current scalar query comment names omit vantage. Multi-query generation must
use the already-supported five-field `ConfidentialityQuery` comment format
(`cumulative <feature> <start> <end> <vantage>`) so result dictionaries cannot
collapse distinct vantages. Give internal summary columns distinct stable names
and save their expressions in the manifest; validate parser round trips and unique
names before invoking SMC. A generic query-parser rewrite is unnecessary.

Use one shared Python orchestration function for smoke and statistical runs.
Initially parametrize pytest by experiment group, executing both arms once and
asserting on its named case results afterward. If separate pytest items per triple
are later needed, use a fixture scoped to the execution group; do not accidentally
rerun SMC for every feature. Reuse across entries with identical execution inputs
through an explicit per-session group key, never an unversioned sample bank.

## Decisions, activity and multiplicity

Preserve both existing comparison modes. In `p-value` mode a pass means that the
KS equality null was not rejected, not demonstrated equivalence. In `bound` mode
only a distance upper bound below delta passes. The usual SciPy KS p-value has
continuous-distribution assumptions; these rates have ties, so retain that caveat
in the report/documentation rather than presenting p-value mode as a soundness proof.

Multiple observables share sample rows. Keep those correlations; no independence
across feature/vantage tests is assumed. Freeze the selected statistical family
before seeing results. The default `none` policy uses alpha for every case and
supports per-case conclusions only. Optional `bonferroni` gives each of K configured
cases alpha/K. For bound mode this gives simultaneous confidence coverage;
for p-value mode it controls family-wise false rejections only to the extent the
underlying p-values are valid. Record global alpha, effective per-case alpha, K,
method and delta. Do not redistribute alpha when cases are inactive or fail to run.
The larger family will require more samples for useful bound-mode precision; the
old M=5000 is a starting budget, not a power guarantee for this matrix.

Use explicit outcomes with reasons:

- `pass` / `fail`: the selected statistical decision.
- `inconclusive`: bound interval overlaps delta.
- `inactive`: insufficient observed activity to make the selected case meaningful.
- `unsupported`: no valid composition/query recipe is implemented.
- `error`: invalid configuration, build, execution, parse or plot failure.
- `smoke-only` / `build-only`: plumbing checks, never statistical evidence.

Activity is checked per observable using a relevant count summary, not simply
whether its final scalar is positive. Preserve legitimate zero samples; flag a
wholly unobserved case in either arm. If there are supporting/monitor actors that
can emit autonomous traffic, establish source attribution or report the fixture as
unsupported: composing N isolated runs must not multiply unrelated background
traffic that appears only once in the joint configuration.

A group execution error yields an error record for every affected named case.
Other independent groups continue. Statistical pytest succeeds only if all selected
supported cases pass; inactive/unsupported cases remain visible and require an
explicit selection change, not an automatic skip that makes the suite look complete.

## Reports and file layout

Write a suite manifest/report with input configuration, execution UUID, group build
paths, generation/SMC settings, seeds, source/model hashes, query manifest and raw
row artifacts. Keep raw rows once per group; avoid duplicating them in every case.
The report contains a result mapping keyed by full case ID. Each case records:

- Combination name and structured kind/feature/vantage/profile/network/window/N.
- Composition recipe, observed activity and sample counts, moments and comparison
  diagnostics, method, effective alpha, tolerance, outcome and reason.
- References to the group's raw samples, composed samples and UUID-named CDF PNG.

Every completed comparison gets a plot, including fail/inconclusive outcomes.
For inactive cases a diagnostic plot can be included, clearly labeled inactive.
Build/error/unsupported outcomes should explain absent plots. Keep plots beside
`report.json` and use relative filenames. Extend the existing `--results-dir`
copying to include all referenced artifacts so exported reports remain usable.

## Delivery sequence and validation

1. **Schema, naming, adapters:** add the six-type registry and v2 config validation;
   migrate the DNS selection to `ixpN`, keeping legacy normalization separate. Test duplicate IDs/pairs,
   bad types/features/vantages, absent profiles and incompatible window overrides.
2. **Rate matrix across all kinds:** implement multi-column queries, row manifests,
   shared runs and additive packet-count recipes. Build and smoke-test both populations
   for all six kinds, validating visibility and nonempty activity per requested case.
3. **Packet sizes:** add paired count/byte recipes for DNS and TCP means. Verify
   each against the direct model calculation, then enable every selected feature.
   Until then, selected recipes report `unsupported` explicitly. Rates and packet
   sizes complete the 18-case matrix; interarrival support is not required.
4. **Suite reporting and statistics:** reuse both decision modes and plotting,
   implement the configured multiplicity policy and test report/export references.
5. **Fixed-budget statistical campaign:** choose and record the budget before
   execution, run all supported entries, and report the complete named result table
   including failures, inactivity and inconclusive cases. Do not tune the selection,
   profiles, alpha or budget after seeing outcomes to produce an all-pass suite.

Unit tests must cover disjoint row grouping, unsorted multi-column samples, unequal
packet counts for weighted means, empty windows, zero denominators, count/rate
rounding, both KS
modes, multiplicity, query-name uniqueness and distinct per-case plots. Include a
synthetic dependent-contribution control (replicated samples) with a known aggregate
distribution mismatch and a correctly independent control. Verify that one case's
failure does not suppress other results or corrupt a shared group's rows.

Reuse the existing test runner and generator throughout. Limit production changes
to any demonstrably missing observation-summary accessor, with a direct semantic
check; do not turn this work into a general regression-framework refactor. Completion
means every explicitly selected triple has a reproducible named result, not that
all TGEN types must pass or that a 100x rewriting speedup has been established.
