This directory contains s Maude timed models of a simple round
trip time protocol RTT and model WRTT of its use to carry
hiddent information. There are three versions of the pair: (a)
(rtt.maude, wrtt.maude) in which A/alice sends the hidden
information, (b) (rtt.maude,wrttbob.maude) in which B/bob sends
the hidden information, and (n) (rttnoise.maude, wrttnoise.maude) like (a) but noise added to
the timestamp representing alice's clocke reading.


In the base RTT protocol has two roles: A and B. A and B each
have a clock whose value has sort Time and we assume their
clocks to be synchronized. Periodically A sends to B an
rttRequest message containing the current clock reading as a
digital (64bit natural number) timestamp, the result of reading
the clock.  Upon receving the request B send am rttRespone
message to A containing the received timestamp and the timestamp
of B's current clock reading.  A records the round trip time (the current clock minus the sent timestamp) when the
response arrives.   

The different protocol versions are specified as Realtime Maude
(RTM) modules. RTM provides data structures for representing
timers and rules for passing time and an abstract notion of
time and several instantiations.


To run a simple instantiation of RTT 
terminalprompt> maude rtt.maude
Maude> rew {aO bO} .

To run a simple instantiation of WRTT 
terminalprompt> maude wrtt.maude
Maude> rew {aO bO} .

The file organization

time.maude --- the RTMaude time models
   includes  Time as Nat, Time as NzRat, and Time as
   Float instantiations

sampler-x.maude --- a library of distribution sampling
    functions, supporting probablistic features and analysis
    
rt-aux.maude  --- RTMaude infrastructure
   --- mte,timeEffect, time  management rules
   --- independent of choice of Time representation
   
rtt-aux.maude --- RTT specific data structures for
   --- for timestamps, and conversion operations 
   --- shared msg and attribute constructors
   
rtt.maude  --- the RTT protocol and instantiations
   to Time as Nat, NzRat, Float and Probablistic
wrtt.maude --- the WRTT protocol and instantiations
   to Time as Nat, NzRat, Float and Probablistic

The end of each time instatiation has example rewrites.
In the probablistic case there is an example
of how to do repeated runs with different initial
values of the random counter object rCtr .

--- the version where A has timestamp noise is defined in
rttnoise.maude  
wrttnoise.maude 

--- the version where B sends hidden information to A
rtt.maude -- unchanged
wrttbob.maude


---------------------------------------------
Scenario files
----------------
To investigate the (in)distinguishability of WRTT from  RTT
we introduce an oberver object modeling what an 
adversary can see.  We model an adversary that uses a
notion of inforamtion content (bientropy) to compare
execution of RTT and WRTT versions.


rtt-observer.maude
  ---  defines an observer object with attribute
       sent:_ : TimeMsgList 
       defines equation for rtt sendTimeAction   
         (adds rttReq messages stamped with send time
         to the sent attribute)
bientropy.maude
  --- defines a notion of entropy for bit lists .
  --- implements BiEntropy – The Approximate Entropy of a
      Finite Binary String by Grenville J. Croll
      arXiv 1305.0954 v2.33
tsTml2enTml.maude                
  ---- defines a function that converts  rttReq messages
  to messages with content en(biEn32,biEn8) --
  the bientropy of the low order 32/8 bits of the 
  timestamp
  --- defines a constant with the result of the rtt+wrtt
     execution and the result of the ts2bin 
     transformation  
This file is just to get an idea of what the entropies
looklike.

rtt-scenarios.maude
  ---- defines 3 scenarios for the base protocol
     1. RTT alone
     2. WRTT alone
     3. RTT + WRTT concurrently
  all with an observer.
 Each sceanrio ends with a sample execution commd
                              
rtt-wrtt-wnoise-scenarios.maude       
  ---- defines  scenarios for the base protocol with noise
     1. RTT alone
     2. WRTT alone
  each with an observer.
The commands at the end generates the output in rwnoise.txt

rtt-bwrtt-scenarios.maude       
  ---- defines 2 scenarios for the B sends protocol
     1. RTT alone
     2. WRTT alone
  each with an observer.
The commands at the end generates the output in rwbob.txt
        
---------------------------------------------
Ouput files
----------------

rwbob.txt
maude rtt-bwrtt-scenarios.maude > rwbob.txt
rewrite in  RTT-SCENARIO : iSrtt . 8x
rewrite in WRTTBOB-SCENARIO : iSbwrtt . 8x
 
----------------------------------------
rwnoise.txt
rtt-wrtt-wnoise-scenarios.maude > rwnoise.txt
rewrite in RTT-SCENARIO : iSrtt .  8x
rewrite in WRTT-SCENARIO : iSwrtt . 8x

----------------------------------------
rtt-wrtt-entropy-lists.txt   
Summary entropy lists from rwnoise.txt and rwbob.txt
8 runs each of RTT/WRTT scenarios 
(1) Alice adding noise added to timestamp in rttReq 
    Alice embedding a byte stream
(2) Bob embedding a byte stream -- no added noise

Parameters
startTime 999.
stopTime 10999.
Period 500
Link delay MEAN 50. SD 10.

----------------------------------------
rtt-wrtt-summary-en-rtt-av.txt  
Summary entropy average, rtt average from
8 runs each of RTT/WRTT scenarios 
(1) Alice adding noise added to timestamp in rttReq 
    Alice embedding a byte stream
(2) Bob embedding a byte stream -- no added noise

Parameters
startTime 999.
stopTime 10999.
Period 500
Link delay MEAN 50. SD 10.

   

     
