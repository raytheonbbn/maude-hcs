The raceboate-bidir directory contains the maude
specification of bidirectional instance of raceboat
instantiated with a mastodon/destini tunnel.

A raceboat channel between two parties consists of two
bidirectional raceboat endpoints (one for each party). 

A bidirectional raceboat endpoint consisists of 7
actors: a sender content manager (CM) with associated
user model and mastodon client actors; a receiver CM
with associated user model and mastodon client actors;
and a shared encoder/decoder (destini) actor.

The user model, destini, and mastodon actor specification
are taken from CP2.

The sender/receiver CMs are adapted from CP2 client (sender) and server (receiver) CMs.  These are defined
in the files
    cm-aux.maude
    rb-cm-receiver-mas-aux.maude
    rb-cm-receiver-mas.maude
    rb-cm-sender-mas-aux.maude
    rb-cm-sender-mas.maude
    
The CM sender/receiver files contain test modules
at the end that exercise each rule.
    
The encode/decode (destini) actor is copied from 
cp2
    enc-dec-actor.maude
Mastodon actors from CP2 are reused.  

Hashtag management abstraction is specified in

    cp3-hashtag-manager.maude

It guarantees distinct sequences of unique hashtags for
bidirectional channels if properly configured.

A CM has a set of hashtag attributes that it accesses via
 getWHashtag/getBHashtag -- gets the current 
     weird/benign hashtag to use (from the attribute)
 nextWHashtag/nextBHashtag --- generates the next
     weird/benign hashtag to use, and updates 
     the hashtag attributes

The hashtag attributes are initiated with a single
string.   The CM sender at one endpoint must use
the same string as the CM receiver at the other
end point, and dually for CM receiver.
This pair of strings should be distinct and different
from the strings used by all raceboat mastodon/destini
channels.

This should be adaptable to uuid generation for MinIO

The application/user specific msg conversion is specified
in 
    user-interface.maude

For debugging I implemented a mechanism to log IRC
messages  
   --- client to/from channel, 
   --- server to/from
in
   logging.maude

It can also be used for Minyoung to experiment with
the various latency/goodput computations.

**************** SCENARIOS

A module for testing bidirectional rb is defined in
   rb-bidir-scenarios.maude
Output from a sample run is   
   irc-mastun-run.txt

The IRC over Mastodon/destini channel scenario for two
clients is defined in
   rb-bidir-mas-irc-scenario.maude
It demonstrates the actors to be created and their
connections.  Includes use of IRC message logging.

The CM Sender/Receiver user models used are
  client_config_cp2_scenario_1_new.maude
  server_config_cp2_scenario_1_new.maude
These are copied from CP2 and edited to remove unused information/clutter

The file 
   run-output-template.txt
lists sturcture of a final state in the order
of actors as printed by Maude.

The file 
   irc-scenario-run.txt
is the output from rewriting the initConfig of the
above scenario.
   irc-scenario-msglog.txt
Is the irc message log extracted from the full output.
   





