I’d start with **one TGEN type, one profile, one vantage, one fixed window, and two instances**. The test would compare the observable from two jointly simulated TGENs with the observable reconstructed from two independent single-TGEN simulations.

This tests whether independent composition reproduces the observable’s distribution. A pass provides scoped statistical evidence for decomposition; it does not prove independence for every observable or configuration.

**1. First concrete case**

Use DNS TGENs and the aggregate DNS query rate:

| Setting | Initial choice |
|---|---|
| TGEN type | DNS |
| Profile | One existing scenario-1 DNS profile, identical for both instances |
| Network | `client_net_mastodon`, preserving scenario-1 network parameters |
| Vantage | `cl[1]` |
| Observable | `dnsQueryRate`, aggregated across all flows |
| Observation window | First 60 seconds after TGEN startup |
| Populations | 1 and 2 |
| HCS clients | None |

Retain the DNS infrastructure needed to serve the traffic. In particular, **do not replace shared DNS infrastructure with independent copies inside the two-TGEN configuration**: any coupling through that infrastructure is something the experiment should detect.

Use the existing aggregate feature calculation, rather than the per-flow ECDF or KS detector output.

**2. Two configurations, generated through the existing build**

Add a small context such as:

```text
tests/contexts/tgen_independence/
    scenario.yaml
    build_cfgs/
    tgen_user_models/
    ...
```

The base YAML would contain scenario-1 networking, no HCS nodes, and only the chosen TGEN type/profile.

The test would create two temporary variants differing only in TGEN quantity:

- **Single:** one instance.
- **Joint:** two instances.

Reuse `build()` and the current generator for both. Keep the variant creation local to this test initially; there is no need for a general parameter-sweep framework.

As an initial build check, verify that generation supports empty HCS nodes and that the two outputs contain the intended TGEN populations.

**3. Supply one scalar QuaTEx query**

The standard generated queries target performance and detection metrics. This experiment needs one scalar measurement of background traffic.

Use a small test-local adapter to:

- Write a `test.quatex` containing the aggregate `dnsQueryRate` query for the chosen vantage/window.
- Retain the adversary’s traffic observations until that query is evaluated.
- Disable baseline/KS processing that could prune those observations.

The last point matters: **“baseline” here means a TGEN-only experiment, not necessarily the existing baseline-calibration execution mode.** We should avoid running calibration work that the independence test does not need.

The adapter should preserve normal TGEN, DNS, and network behavior. It should only change observation/query setup.

**4. Reuse the SMC runner and compose fresh samples**

For \(M\) comparison samples:

1. Run the single-instance configuration for **\(2M\) simulations**.
2. Run the two-instance configuration for **\(M\) simulations**.
3. Group the single-instance samples into disjoint pairs:

\[
R_j = X_{2j} + X_{2j+1}.
\]

4. Compare those \(M\) reconstructed rates with the \(M\) jointly simulated rates \(Q_j\).

Because both rates use the same window duration, addition is the correct composition rule.

Use independent simulation draws and recorded seed settings. Do not reuse a small sample bank repeatedly or multiply one sample by two.

The existing runner already provides sample rows, provenance, timeouts, and retained diagnostics, so most execution infrastructure can remain unchanged.

**5. Use the existing statistical comparison calculation**

Compare \(Q\) against \(R\) using the KS-distance upper confidence bound already introduced into the framework:

- **Pass:** upper bound is below the declared tolerance.
- **Failure:** the distributions demonstrably exceed the tolerance.
- **Inconclusive:** the available samples cannot establish equivalence.

Both failure and inconclusive should make the pytest assertion fail, with different diagnostic messages.

Reuse the numerical comparison logic, but **not the entire snapshot checker**: these configurations intentionally differ in population, so their provenance cannot be identical. Instead, explicitly verify that their controlled settings match except for population and sampling settings.

Start with a small execution-smoke sample budget. Select the statistical sample budget separately; a tiny successful run should not be reported as evidence of independence.

**6. Minimal framework integration**

Add one dedicated pytest test, for example:

```text
tests/test_tgen_independence.py
```

It would orchestrate:

```text
prepare variants
    → build both configurations
    → install scalar query
    → run existing SMC runner twice
    → compose single-instance samples
    → compare against joint samples
```

Mark it `statistical`. Initially, use one small experiment configuration containing type/profile, vantage, window, population, sample count, seed settings, and tolerance. Avoid adding a new runner enum or generalized experiment language.

Save a report containing sample counts, means, variances, KS distance, confidence bound, outcome, and paths to both builds. Require nonzero observed traffic so an accidentally inactive configuration cannot silently pass.

**7. Keep the first implementation narrow**

Implement and validate DNS query rate first. Add unit tests for sample pairing, rate composition, insufficient evidence, and a deliberately incorrect “multiply one sample by two” implementation.

For a later mean-packet-size case, collect paired packet counts and byte totals and reconstruct:

\[
\frac{\sum_i B_i}{\sum_i C_i}.
\]

That extension can use the same orchestration, but the first test does not need to support it yet.