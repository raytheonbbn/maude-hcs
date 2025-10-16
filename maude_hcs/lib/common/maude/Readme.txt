This directory prototypes CP1 extended by a router and
and the collection/obervation part of an adversary.

case1_sim_config_cp1-adversary.maude 
and
case3_sim_config_cp1-adversary.maude  

are the case1 and case3 files from results-m1000 modified 
to add the router and adversay to the initial configuration.

To run the case<n> extensios put this folder in lib/dns/maude
AND
in deps/dns_formaliation/Maude/src/probablistic-model
edit parameters.maude to load apmaude-default in this folder
rather than the local one. 

load apmaude
>>>
sload ../../../../../lib/dns/maude/adversary/apmaude-default

This is a first step in refactoring. I think we want to put
apmaude, sampler, and parameters in a separate folder at the
level of deps and lib as they should be shared (and possibly
extended) by all the cp models.

The modifications in the case<n> files are marked by
***!!!  

apmaude-default.maude  
  adds the owise attribute to the equations for adding
  a message to the schedule list and for releasing a
  message when the configuration has no message
  elements.  This allows us to add equations for the
  scheduler that apply when there is an adversary object
  in the configuration.  (see adversary-observer.maude)

net-aux.maude
  introduces two address constructors: X and Z where
    X(addr) is the view of the external address addr
      seen by corporate actors and 
    Z(j,iaddr) is the NAT translation of the address of
      a corporate actor seen by external actors
  these are used to define router rules, and to specify
  patterns recognizing messages observable by an adversary.
  
router.maude 
  defines the Router actor type, its attributes, 
  and two router rules.

  One rule translates 
  (to X(addr) from iaddr : c) to (to addr from Z(j,iaddr : c))
  where j is the value of a counter to model obfuscation
  by NAT.  

  The other rule does the inverse, translating
  (to Z(j,iaddr) from addr : c) to (to iaddr from X(addr) : c)
  
adversary.maude                      
  defines the Adversary actor type, a sort Obervable
  which is a set of patterns use to specify messages to
  collect, and an initial set of attributes
   sent: list of timed messages -- tm(time,msg)
            here time is the sending time
   rcvd: list of timed messages -- tm(time,msg)
            here ime is the receiving time
   ObsS: patterns specifying messages to collect at send time
   ObsR: patterns specifying messages to collect at rcv time
 Defines functions to log observed message
  logSent(attrs,t1,M1) --- for sending time
  logRcvd(attrs,t1,M1) --- for receive time

adversary-observer.maude            
     extends ADVERSARY and SCHEDULER with scheduler equations
     that log messages mathing the ObsS or ObsR patterns
     if there is an Adversay actor present.
     
case1-adversary-C.txt   
  the adversary at the end of rew, adversay observing the
    router corporate interface
case1-adversary-X.txt
  the adversary at the end of rew, adversay observing the
    router external interface
