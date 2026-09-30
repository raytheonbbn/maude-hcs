The experiment tests whether **two TGENs running together produce the same observable distribution as two independent, separately simulated TGENs whose contributions are added**. That is a test of observable composition. Independence is one sufficient justification for composition, but matching the aggregate distribution does not prove independence.

For this implementation, the observable is the total DNS query rate at `cl[1]` during a fixed 60-second window.

**Why compare M joint runs with 2M single-source runs?**

Let \(X\) be the rate observed in a simulation containing one TGEN:

\[
X=\frac{\text{number of visible DNS queries}}{60}.
\]

Let \(Y\) be the total rate observed when two TGENs run together.

The decomposition hypothesis predicts

\[
Y \overset{d}{=} X_1+X_2,
\qquad X_1,X_2\stackrel{\mathrm{iid}}{\sim}P,
\]

where \(P\) is the single-source distribution and \(\overset{d}{=}\) means equality in distribution. The distribution on the right is the **convolution** \(P*P\).

This prediction requires two substantive properties:

1. **Marginal preservation:** each TGEN’s contribution in the joint configuration has the same distribution as its contribution when simulated alone.
2. **Independence:** the two contributions in the joint configuration are independent.

Marginal preservation matters because adding a second TGEN could change server behavior, loss, caching, retries, or other shared state—even if the generators use identical user models.

We sample the two sides of that prediction as follows:

| Simulation arm | Simulations | Values used in the comparison |
|---|---:|---|
| Two TGENs together | \(M\) | \(Y_1,\ldots,Y_M\) |
| One TGEN alone | \(2M\) | \(Z_j=X_{2j-1}+X_{2j}\), for \(j=1,\ldots,M\) |

Thus, **the statistical comparison is between M joint values and M composed values**, not directly between samples of sizes M and 2M. Each composed value consumes two independent single-source simulations.

Disjoint pairing ensures that, assuming independent simulation runs, the \(Z_j\) are themselves independent draws from \(P*P\). Reusing individual samples across many sums would introduce dependence between the composed observations and invalidate the confidence calculation used here.

The 2:1 allocation is a simple way to obtain equally sized comparison samples. It is not a uniquely optimal allocation.

**Why not multiply each single-source rate by two?**

Multiplication reproduces the same random realization twice. Independent composition uses two different realizations.

If \(X\) has mean \(\mu\) and variance \(\sigma^2\), then

\[
\begin{aligned}
E[X_1+X_2]&=2\mu,
&\operatorname{Var}(X_1+X_2)&=2\sigma^2,\\
E[2X]&=2\mu,
&\operatorname{Var}(2X)&=4\sigma^2.
\end{aligned}
\]

Both methods produce the correct mean under independence, but doubling a sample produces the wrong variability.

Similarly, sorting the single-source samples before pairing would systematically combine small observations with small observations and large ones with large ones. The implementation therefore pairs samples in their original run order.

Rates are additive here because every contribution uses the same denominator:

\[
\frac{C_1}{60}+\frac{C_2}{60}
=\frac{C_1+C_2}{60}.
\]

This construction would not apply directly to average packet size. That observable requires combining byte totals and packet counts, then taking their ratio.

**What does the chosen statistical test measure?**

Let \(F\) be the CDF of the joint-model rate \(Y\), and \(G\) the CDF of the composed rate \(Z=X_1+X_2\). Their Kolmogorov–Smirnov distance is

\[
D=\sup_t |F(t)-G(t)|.
\]

It measures the largest difference in the probability that the rate is below any threshold. For example, \(D<0.05\) means that, at every rate threshold, the two models’ cumulative probabilities differ by less than five percentage points.

This compares the distribution rather than just its mean. It can detect changes in variability and distribution shape, although it does not directly bound mean error or every possible detector’s behavior.

From the two samples, we calculate

\[
\widehat D=\sup_t|\widehat F_M(t)-\widehat G_M(t)|.
\]

The code uses `scipy.stats.ks_2samp` to calculate this statistic. It does **not** use the returned equality-test p-value for acceptance. [SciPy documentation](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ks_2samp.html)

That distinction matters. Failing to reject “the distributions are equal” can simply mean that the sample is too small. Our intended acceptance claim is stronger and more useful:

\[
H_0:D\geq\delta
\qquad\text{versus}\qquad
H_1:D<\delta.
\]

Here, \(\delta\) is the maximum acceptable discrepancy, chosen before observing results.

**How do we account for sampling uncertainty?**

The Dvoretzky–Kiefer–Wolfowitz–Massart inequality gives a finite-sample bound for an empirical CDF based on \(n\) iid observations:

\[
\Pr\!\left(\|\widehat F_n-F\|_\infty>\epsilon\right)
\leq 2e^{-2n\epsilon^2}.
\]

It applies without assuming a Gaussian or continuous distribution, which is useful because our rates are discrete multiples of \(1/60\). [DKW–Massart background and proof](https://arxiv.org/html/2403.16651v1)

Allocate failure probability \(\alpha/2\) to each empirical CDF. Each then has error bound

\[
\epsilon_n=\sqrt{\frac{\log(4/\alpha)}{2n}}.
\]

By the union bound, both CDF bounds hold simultaneously with probability at least \(1-\alpha\). The triangle inequality then gives

\[
|D-\widehat D|\leq \epsilon_M+\epsilon_M.
\]

Consequently, the implementation constructs

\[
L=\max(0,\widehat D-r_M),\qquad
U=\min(1,\widehat D+r_M),
\]

where

\[
r_M=\sqrt{\frac{2\log(4/\alpha)}{M}}.
\]

Its decisions are:

- **Pass:** \(U<\delta\), establishing equivalence within the specified tolerance.
- **Fail:** \(L>\delta\), establishing a discrepancy beyond that tolerance.
- **Inconclusive:** the interval crosses the tolerance boundary.

Pytest treats an inconclusive statistical result as unsuccessful because equivalence has not been established.

Under the iid assumptions and a fixed sampling plan, the probability of incorrectly passing when \(D\geq\delta\) is at most \(\alpha\). This is a repeated-sampling guarantee, not a posterior probability that independence is true.

**What do our parameter choices imply?**

The defaults are \(\delta=0.05\), \(\alpha=0.05\), and \(M=5000\).

| Comparison samples \(M\) | Confidence margin \(r_M\) | Requirement for passing |
|---:|---:|---|
| 100 | 0.29604 | Impossible, even if \(\widehat D=0\) |
| 5,000 | 0.04187 | \(\widehat D<0.00813\) |

Therefore, the 100-sample run is strictly a diagnostic of execution and reporting. Its observed \(\widehat D=0.10\) gives \(U\approx0.39604\), explaining its inconclusive result.

The 5,000-sample default permits acceptance, but leaves little room for empirical sampling differences. **It is not a power-calibrated guarantee that a truly composable system will pass.** The DKW construction is conservative; its advantage is a simple, distribution-free guarantee. Sample budgets should be planned in advance, rather than increased repeatedly until a pass appears.

Finally, the statistical conclusion has a precise scope. A pass supports closeness of the **single-window aggregate rate distributions** for this fixture. Different dependent mechanisms can produce the same aggregate distribution, so it cannot identify independence itself. A failure could reflect dependence, changed single-source marginals, or another mismatch between the joint and isolated models. Neither outcome automatically extends to more TGENs, other observables, successive windows, or configurations containing HCS clients.
