Maude timed models of a simple round trip time
protocol (module RTT in rtt.maude) and a verion
(module WRTT in wrtt.maude) that carries hidden
information in the time stamp.

To run a simple instantiation of RTT 
terminalprompt> maude rtt.maude
Maude> rew {aO bO} .

To run a simple instantiation of WRTT 
terminalprompt> maude wrtt.maude
Maude> rew {aO bO} .

The file organization

time.maude --- the RTMaude time models
   includes  Time as Nat and Time as NzRat refinements
   float-time-inf.maude is the Time as Float refinement.
      should add this module to time.maude

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

Scenario files
----------------

bientropy.maude
  --- defines a notion of entropy for bit lists .
rtt-observer.maude
  ---  defines an observer object with attribute
       sent:_ : TimeMsgList 
       defines equation for rtt sendTimeAction   
         (adds rttReq messages stamped with send time
         to the sent attribute)
rtt-scenarios.maude
  ---- defines 3 scenarios
     1. RTT alone
     2. WRTT alone
     3. RTT + WRTT concurrently
  all with an observer.

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
     
    