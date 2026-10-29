# Independent random streams

The model uses Philox4x32-10 through `streamRandom(streamId, index)`. It needs a
Philox-enabled Maude executable or Python binding. Ordinary unary `random(j)`
retains its original Mersenne Twister behavior. The native patch is
[`patches/maude-philox.patch`](patches/maude-philox.patch), based on upstream Maude
revision `46e89557efc7791d01b3399f10df7b30d615972c`. Apply it to that source tree
and build Maude using its normal build process. GC budget selection is a separate
build setting; this patch does not change the GC target.

```bash
# From the upstream Maude source checkout, before building:
git apply /path/to/maude-hcs/maude_hcs/patches/maude-philox.patch
```

## Dependency sampler hook

The DNS dependency stays independent of local model modules. Its generic hook
has a legacy fallback, `eq samplerRandom = random(counter) [owise] .`.
Apply the small hook patch from the maude-hcs repository root:

```bash
git apply --directory=maude_hcs/deps/dns_formalization \
  maude_hcs/patches/dns-sampler-rng-hook.patch
```

Apply once, on top of the existing DNS dependency branch. If the earlier RNG
sampler patch is already installed, reverse that version first; keep other
local dependency changes. The dependency checkout is ignored by the parent
repository, so the patch is kept here for reproducible setup.

Local `SAMPLER-STREAMS` reuses the dependency's distribution formulas, declares
its own `networkCounter`, overrides the hook with Philox, and skips constant
ranges. `NETWORK_NODE` and `IODINE-PARAMETERS` import it explicitly. In composed
`IODINE_DNS`, imported DNS equations and rule right-hand sides use the local
hook too. Selecting bare dependency `DNS` retains its legacy sampler.

## Stream assignments

| Stream ID | Consumer | Index |
|---|---|---|
| 0 | Workload choices, distributions and startup | Existing allocated `rCtr` index |
| 1 | Implicit network and timer sampling | Local `networkCounter` |
| 3 | Explicit link jitter | Existing allocated `rCtr` index |
| 2^32 + actor ordinal | Iodine packet sizes | Actor-local packet counter |
| 2^33 + identifier token | Random identifier characters | Character position |

Set the run seed once using `-random-seed=N` or binding `setRandomSeed(N)`.
The seed is the Philox key, while stream ID and index form its counter. Stream
interleaving cannot rewind a shared RNG or change an indexed result. Identifiers
and indices must fit unsigned 64-bit integers; actor ordinals and identifier
tokens must remain below 2^32 to keep their namespaces disjoint. Philox here is
for simulation, not cryptographic use. The generator assigns distinct Iodine
send/receive stream ordinals; compatibility constructors retain defaults 0/1.

With seed 0, `streamRandom(0, 0)` must reduce to `1713891541`. Original
`random(0)` must still reduce to `2357136044`. Reset built-in counters between
independent trajectories if repeatability from the same seed is required; use
`set clear rules off` only when intentionally carrying counters between rewrites.
Never reset counters in the middle of one trajectory.

## Jitter and model semantics

Positive sleep delays do not evaluate a discarded jitter draw; allocated cursor
holes remain. Constant packet sizes and constant sampler ranges also avoid draws.
`trimAdapterJitter` defaults to true and removes additional constant-delay IRC
format-conversion noise, retaining `overhead + delayConst` and index allocation.
Override it with `eq trimAdapterJitter = false .` to retain those local delays.

The new streams intentionally change seeded trajectories. In particular, random
strings use a fixed identifier stream and increasing character positions instead
of using a random output as the next index. This removes the old correlations.
Exact equivalence with the previous RNG sequence or timing distribution is not
claimed; traffic statistics and protocol invariants must be validated for the
intended scenario. The sampler-hook relocation itself preserves final states and
histories compared with the initial Philox implementation.
