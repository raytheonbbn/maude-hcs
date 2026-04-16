An Equational TrafficGenerator is composed of three
actors (equational user-model, equational
contentGenerator, and an observer) plus a counter
object rCtr(j) and an adversary object where
observations are collected.

To support mulitple TGen instances, we take
advantage of the fact that the SCHEDULER is
equational -- adding delayed messages to the
Schedule object and releasing messages to be
delivered are implemented as equations.

****** From SCHEDULER
***** Send Time
  --- insert a schedule msg to the scheduler 
  eq [ t1, M1, 0 ] S = insert(S, [ t1, M1, 0 ]) [owise] .
  eq [ t1, M1, P ] { GT | SL } = { GT | SL }
     [owise print "(" GT ") Drop message " "[" t1 ", " M1  "]" ] .
  eq [ t1, M1, P ] S = S [owise] .

***** Receive Time
  eq step(AC {GT | [ t1 , M1, 0 ] ; SL}) 
   = { t1 , M1 } AC {t1 | SL} [owise] .

The equational user-model and content generators
are obtained from the origian TGEN actors as
follows ** rules are turned into equations
 
    crl becomes ceq, => becomes =, 

The observer actor is new. In the DNS case, it
simulates sending a request (query) and receiving
a response by logging these messages with suitable
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

The http case depends on the protocol and what we
want to observe. For Mastodon, propose replacing
single observer by a two actor subsystem:
equational versions of the mastodon client and
server. In this case we can refine and reuse the
http overhead mechanism.

In the case of multiple instances the equational
server should be shared.

The delays and messages to log are  parameters of the  observer traffic logging mechanism.
I think we can reuse the logging mechanism using 
the scheduler equations, but need to be careful
to be compatible the mechanism used by alice/bob.

**********************************************
Files

ua-actor-eq.maude 
  -- equational version of user-model actor
  -- parameterized by a stop time 
  -- as well as nsteps
  
dnsQgen-actor-eq.maude 
  -- equational version of the dnsQgen 
     (query generator) actor 
     
dnsObs-actor-eq.maude  
  --- observer pattern instantiated to DNS

multi-dns-scenario.maude
 --- defines a two tgen scenario 
multi-tgen-run.txt has ouput from
   Maude> load multi-dns-scenario.maude
   Maude> red run(iCtwo(1,30.),100.) .

Actor specificaton files have unit test examples.

**********************************************
Soundness
Equational execution is well defined

Under what conditions is the message distribution
sampled in CP_2 scenarios equivalent to that
sampled when when rulebased Tgens are replaced
by equational Tgens executed at the end.

A [wnet] B
 servers    observer
  Tgen

vs

A  [wnet] B
  servers  observer * equational Tgen

are the distinguishable, if so how, 
can it be corrected by augmenting ETgen  

**********************************************
Integration

To replace rule based TGens by the equational 
version we  assume a function 
      tgenConfig(j:Nat,T:Float)
is defined that defines an equational tgen configuration.
j is the initial rCtr index for the tgen configuration.
T is the stop time used by the user models.
(tgenConfig is an analog to initConfig for a scenario)

We add 

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

****************************************************
Modifying CP2 like scenarios to use equational  dns tgen

sload ../../../lib/tgenScale/maude-v1/multi-dns-tgen-aux

omit sloading dnsTgen-actor-uniqueId

 inc DNS-TGEN . >>   inc MULTI-DNS-TGEN-AUX  .

*** decide where dfn of finalize goes

remove the tgen actor constructions from initState
add a definition of tgenConfig(j:Nat) using modified
versions of the removed constructions

sload the equational tgen actors.
We could put the tgen specific finalize definition
is some tgen module, but I think its best to put
it in the scenario file in the case that we want
to add other finalization functionality.

The template for defining tgenConfig for n dns generators 
When additional types of tgen are available there
should be a section for each type
eq tgenConfig(j,GT) =
   rCtr(j + n)
   {0.0 | nil}
**** DNS tgens   
(for i < n)
   [Tstart + genRandomX(j,0.0, 0.0001),
    (to umdA-i from umdA-i : actionR("ok")),0]
    mkUMactor (umdA-i,dns-config-i,dnsQA0-i,GT)
    mkDnsQgenEqA(dnsQA-i,dnsOA,1000,
                 'internet . 'com . root) 
 )              
   mkDNSObs(dnsOA,rsvA) 
.


op initState : Nat -> Config .
eq initState(j:Nat) =
....
rCtr(1) >> rCtr(j:Nat)
....
.


at the end
eq initConfig = ... initState ...
>>
rl[init]: initConfig => ... initState(counter) ...


TODO
fix the dnsObs delay / logging
specify masTgenEq

