This directory contains s Maude timed models of a simple round
trip time protocol RTT and model WRTT of its use to carry
hidden information. There are three versions of the pair: (a)
(rtt.maude, wrtt.maude) in which A/alice sends the hidden
information, (b) (rtt.maude, wrttbob.maude) in which B/bob sends
the hidden information, and (n) (rttnoise.maude, wrttnoise.maude) like (a) but noise added to
the timestamp representing alice's clock reading.

In the base RTT protocol has two roles: A and B. A and B each
have a clock whose value has sort Time and we assume their
clocks to be synchronized. Periodically A sends to B an
rttRequest message containing the current clock reading as a
digital (64bit natural number) timestamp, the result of reading
the clock.  Upon receving the request B send an rttResponse
message to A containing the received timestamp and the timestamp
of B's current clock reading.  A records the round trip time (the current clock minus the sent timestamp) when the
response arrives.

The different protocol versions are specified as Realtime Maude
(RTM) modules. RTM provides data structures for representing
timers and rules for passing time and an abstract notion of
time and several instantiations.

To investigate the (in)distinguishability of WRTT from RTT
we introduce an oberver object modeling what an
adversary can see.  We model an adversary that uses a
notion of inforamtion content (bientropy) to compare
execution of RTT and WRTT versions.

Please refer to the [Readme.txt](https://github.com/raytheonbbn/maude-hcs/blob/cp2.eval/maude_hcs/lib/privacyScenarios/RTTExample/Readme.txt) for details. 

Below are the umaudemc SMC results. Queries 1 and 2 correspond to RTT and entropy, respectively. The ``iSrtt`` and ``iSwrtt/iSbwrtt`` correspond to the initial terms for the ordinary and weird RTT cases, respectively. 

(1) Alice embedding a byte stream -- noise added to timestamp in rttReq
    
```console
$ umaudemc scheck rtt-smc iSrtt wrtt.quatex  --assign pmaude
Number of simulations = 180
Query 1 (wrtt.quatex:3:1)
  μ = 100.79013227513225        σ = 3.2633107589237724        r = 0.47997265122538463
Query 2 (wrtt.quatex:4:1) (30 simulations)
  μ = 0.6135072604012983        σ = 0.0790158588647808        r = 0.02950500660132106
$ umaudemc scheck rtt-smc iSwrtt wrtt.quatex  --assign pmaude
Number of simulations = 180
Query 1 (wrtt.quatex:3:1)
  μ = 100.60623015873011        σ = 3.1662056469951327        r = 0.46569028541254426
Query 2 (wrtt.quatex:4:1) (30 simulations)
  μ = 0.6124656163684576        σ = 0.0722734517126548        r = 0.02698735039419551
```
(2) Bob embedding a byte stream -- no added noise

```console
$ umaudemc scheck brtt-smc iSrtt wrtt.quatex  --assign pmaude
Number of simulations = 180
Query 1 (wrtt.quatex:3:1)
  μ = 100.58477513227511        σ = 3.0287522522559365        r = 0.4454734335198795
Query 2 (wrtt.quatex:4:1) (30 simulations)
  μ = 0.6310081679412658        σ = 0.060500104655146436      r = 0.022591110352738968
$ umaudemc scheck brtt-smc iSbwrtt wrtt.quatex  --assign pmaude
Number of simulations = 150
Query 1 (wrtt.quatex:3:1)
  μ = 99.96668253968257         σ = 2.887189557689629         r = 0.46582147398339685
Query 2 (wrtt.quatex:4:1) (30 simulations)
  μ = 0.6248856139035137        σ = 0.08141326651590954       r = 0.030400213330563353
```

### Adjusting Delta

Sampling continues until either the specified number of samples is reached or all queries are answered with the desired statistical significance. In the previous example (ordinary RTT with Alice embedding), Query 2 satisfies the statistical requirements after 30 samples using the default values ``alpha=0.05`` and ``delta=0.5``, while Query 1 is answered after 180.  If we tighten the requirement for the second query by modifying ``delta=0.02`` in QuaTEx query file,
```
wrtt() = s.rval("getRttAv(getObserver(S))");
entropy() = s.rval("getEnAv(getObserver(S))");
eval E[wrtt()];                                      // Query 1 default delta = 0.5
eval E[entropy()] with delta = 0.02;                 // Query 2
```
the entropy query requires more samples to converge.  Query 2 now requires 60 samples to achieve the tighter guarantee as below:
```console
$ umaudemc scheck rtt-smc iSrtt wrtt.quatex  --assign pmaude
Number of simulations = 210
Query 1 (wrtt.quatex:3:1)
  μ = 101.36125850340137        σ = 3.612041977338102         r = 0.491375353293307
Query 2 (wrtt.quatex:4:1) (60 simulations)
  μ = 0.6160080055243717        σ = 0.07180996284128902       r = 0.018550480456728278
```
If we further reduce the bound to ``delta=0.01``, the required number of samples increases further.
```console
$ umaudemc scheck rtt-smc iSrtt wrtt.quatex  --assign pmaude
Number of simulations = 240
Query 1 (wrtt.quatex:3:1) (180 simulations)
  μ = 101.50120370370372        σ = 3.161024938498901         r = 0.46492829902023936
Query 2 (wrtt.quatex:4:1)
  μ = 0.6044756398224311        σ = 0.07507941114512935       r = 0.009547025985316458
```
