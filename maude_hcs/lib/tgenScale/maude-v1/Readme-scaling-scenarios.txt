**********************************************
Equational tgan specifiation files

Note that actor specificaton files have unit test examples.

----------------- common files
delay-x.maude                   
 --- version of delayParamd the uses an explicit
 --- random index rather than the counter object
 --- subsumed by common/maude/delay-drop-x.maude

ua-actor-eq.maude 
  -- equational version of user-model actor
  -- parameterized by a stop time -- the time that
  -- alice sets the doneFlag      
  -- this is in addition to the nsteps termination
  -- condition
  
------------------- dns tgen files
dnsQgen-actor-eq.maude 
  --- equational version of the dnsQgen 
     (query generator) actor 
     
dnsObs-actor-eq.maude  
  --- observer pattern instantiated to DNS
  --- logs time stamped dnsqueries in the dnsQuery: attribute

TODO  fix the dnsObs delay computation

multi-dns-tgen-aux.maude
  --- declares the tgen configuration constructor,
  --- tgenConfig, parameterized by a random index
  --- and a stop time.  
  --- defines the finalize function that evaluatis
  --- the tgen configuration

multi-dns-scenario.maude
 --- defines a two tgen scenario for testing
 --- multi-tgen-run.txt has ouput from
   Maude> load multi-dns-scenario.maude
   Maude> red run(iCtwo(1,30.),100.) .

--------------------- mastodon tgen files
masTGen-actor-eq.maude  
  --- equational version of the masQgen 
     (query generator) actor 

masObs-actor-eq.maude                   
  --- observer pattern instantiated to Mastodon
  --- logs time stamped mastodon requests in the masSent: attribute
  
mastodon-eq.maude               
  --- equational versions of the mastodon client 
  --- and server from
  --- lib/mastodon/maude/probablistic/mastodon.maude

multi-mas-tgen-aux.maude
  --- mastodon version of tgen config evaluation
  --- (see multi-dns-tgen-aux.mauded above)

TODO --- the two aux files differ by the tgens loaded, the 
added definitions are identical.  Need to seoarate these  outl

multi-mas-tgen-scenario.maude
 --- defines a two tgen scenario for testing
 --- multi-mas-tgen-scenario-run.txt contains sample output

--------------------- Test scenarios
TestsDNS/TestsMAS contain versions of cp2 scenarios
k in 1,5,6 modified to use only <protocol> in
{dns,mas}S tgen actors.

  cp2_scenario_<k>-<protocol>tgen-<mode>.maude

<mode> = eq indicates equational tgen actors
<mode> = orig indicates rule based tgen actors

--------------- test results
The files qqq<k><protocol>.txt are the output
from executing mode eq versions

The files ooo<k><protocol>.txt are the output
from executing mode orig versions

eq-test-summary.txt   
 --- summarized timing, rewrites, and message number info
 --- from the output files.
 --- TODO update using current versions of output files

----------------------------------
The integration section below describes the
transformation of the cp2 scenario files
to test the equational tgens.

*************************************************  
******************** repo change   ************  
Moved
  op ma2HashstrMap : MAModel -> Map{Nat,String} .
  op ma2HashstrLen : MAModel -> Nat .
  op jhashstrl2HashstrMap : JVL Nat Map{Nat,String} 
     ->  Map{Nat,String} .
  and associated eqns
from CONTENT-MANAGER in cm-aux
to common/maude/markov-action-model.maude

Should be transparent as must inc
MARKOV-ACTION-MODEL to use
  
**********************************************
Integration

To replace rule based TGens by the equational 
version we  assume a function 
      tgenConfig(j:Nat,T:Float)
that defines an equational tgen configuration.
j is the initial rCtr index for the tgen configuration.
T is the stop time used by the user models.
(tgenConfig corresponds to the tgen actors in the
initConfig for a scenario, including the um actor start times)

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

This has no effect if there are no additional equations defining
finalize behavior.

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
**** More details
****************************************************
Modifying CP2  scenarios to use equational  dns tgen

replace sload of dnsTgen-actor-uniqueId
by
sload ../../../lib/tgenScale/maude-v1/multi-dns-tgen-aux

 inc DNS-TGEN . >>   inc MULTI-DNS-TGEN-AUX  .

sload the equational tgen actor definitions vis the -aux file.
TODO -- figure out where the finalize equations should go.

Remove the tgen actor constructions from the initState construction.
Add a definition of tgenConfig(j:Nat) using modified
versions of the removed constructions

The template for defining tgenConfig for n dns generators 

eq tgenConfig(j,GT) =
   rCtr(j + n)
   {0.0 | nil}
**** DNS tgens   
(for i < n)
   [Tstart + genRandomX(j + i,0.0, 0.0001),
    (to umdA-i from umdA-i : actionR("ok")),0]
    mkUMactor (umdA-i,dns-config-i,dnsQA0-i,GT)
    mkDnsQgenEqA(dnsQA-i,dnsOA,1000,
                 'internet . 'com . root) 
 )              
   mkDNSObs(dnsOA,rsvA) 
.

When additional types of tgen are available there
should be a section for each type


Make sure initState has a counter argument j:Nat and
initial rCtr value rCtr(j:Nat).  I.e.

op initState : Nat -> Config .
eq initState(j:Nat) =
....
rCtr(j:Nat)
....
.

To run, use counter to set the value of j:Nat.
I.e.

eq initConfig = ... initState ...
>>
rl[init]: initConfig => ... initState(counter) ...



