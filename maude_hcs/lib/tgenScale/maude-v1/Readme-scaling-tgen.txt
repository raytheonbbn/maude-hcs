Traffic generators do not interact with the weird
traffic other than the load a shared resource such
as the mastodon server.  So we propose to genearte
the data for statistical analysis independently.
In paraticular thus data can be generate 
equationally at the end of the execution of a
weird traffic scenario.  This is expected to be
a big win since (1) equational rewriting is much faster
that rule rewriting and (2) the statistical model checker
doesn't see all these rewrites.

We obtain the equational system to generate traffic
data  basically by replacing rules by equations in the
actor theory for traffic generation and adapting
the mechanism for logging data.

In the case of DNS traffic generation the 
equational versiono is composed of three
actors: equational user-model, equational
contentGenerator, and an observer (also) equational.
It is executed in the context of an adversary object 
where data is collected, and the random counter object
used for sampling delay and drop distributions.
We take advantage of the fact that the maude HCS
SCHEDULER is equational -- adding delayed messages to the
Schedule object and releasing messages to be
delivered are implemented as equations.

The equational user-model and content generators
are obtained from the origian TGEN actors 
by the following transformation 
 
    crl becomes ceq, => becomes =, 

The observer actor is new. In the DNS case,
it simulates sending a request (query) and receiving
a response using a model of the response time
of the DNS network rather than executing the
DNS network (which would not be fun to make equational).
The observer logs these messages with 
time stamps. The sending time is the time the
observer received the request, the receiving time
uses a latency and loss model to approximate the
message timestamps.

The DNS case is straight forward: one query gets
one response, so we need to model the time a query
bounces around the DNS network, and the effect of
possible drops.

NB: a place-holder model is used for debugging,
need to develop a proper model.

For Mastodon, the current design is
an actor system consisting of equational
versions of : a user model, the masTGen actor,
a mastodon client  and an observer that
monitors communications of the mastodon client.
There will be an equational mastodon server
shared by all mastodon  tgen clients.
We reuse/refine the http overhead mechanism
to model effects of loss and message size ...



**********************************************
Integration

To replace rule based TGens by the equational 
version we  assume a function 
      tgenConfig(j:Nat,T:Float)
is defined that defines an equational tgen configuration.
j is the initial rCtr index for the tgen configuration.
T is the stop time used by the user models.
(tgenConfig is an analog to initConfig for a scenario)

We add a hook 

    op finalize : Config -> Config .
    eq finalize(conf) = conf [owise] .

to SCHEDULER in apmaude.maude and

  ceq run(AC {GT | SL}, LIMIT)
   = (if (GT <= LIMIT and SL =/= nil
         and not(exeDone(AC)) ) 
        then run(step(AC {GT | SL}), LIMIT)
        else AC {GT | SL}
      fi)
    if not eagerEnabled(AC) .

is modified to call finalize when it terminates execution

  ceq run(AC {GT | SL}, LIMIT)
   = (if (GT <= LIMIT and SL =/= nil
         and not(exeDone(AC)) ) 
        then run(step(AC {GT | SL}), LIMIT)
        else finalize(AC {GT | SL})
      fi)
    if not eagerEnabled(AC) .

For the equational tgen execution finalize
runs a configuration containing tgenConfig(j,GT)
and the  adversary object of AC and 
returns AC' {GT | SL} where AC' is AC with
the adversary object updated with tgen messages.

NB:  running a configuration C means reducing
run(schedule C,limit) which is going to call
finalize when it is done!  So finalize in this
case need to know it has already been called.


**********************************************
Correctness

Equational execution is well defined as a consequence
of the AND property of PMaude.

There is work to do to be assured that this
factoring of the execution give measured 
indistinguisable from the original actor system.

Step one is executing big examples with 
original and equational traffic generation
to confirm scaling.

Step two is doing the statistical analyis in
both cases and confirm we get equivalent results.

Step 3  (need Jose and maybe Peter here)
Once convinced we should figure out the scenario and
transform requirements that guarantee scale and
indistiguishabilty.   For example if we consider
congestion in the network or at servers how can
that be accounted for.
