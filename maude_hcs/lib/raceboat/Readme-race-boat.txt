This directory contains Maude specifications of Raceboat (RB)
client and server actors and a mastodon stub (plus files
used by TGEN and other actors) and test file integrated the parts.
To run the tests, you need to fix paths to apmaude-default.maude.
Then (in this directory) 
>   maude rb-integrated.maude
and copy paste commands from rb-integrated.maude

An RB client has 4 actors
    user-model-actor --- executes a markov model
    content-manager-client --- fragments files and executes
                           user actions
    enc-dec-actor --- destini
    mastodon-client --- for testing represented by a fake
  
An RB server has 4 actors
    user-model-actor --- executes a markov model
    content-manager-server ---  executes user actions and
                     assembles fragments 
    enc-dec-actor --- destini
    mastodon-client (FMA)--- for testing represented by a fake

The user-action-model, destini, and mastadon model specifications are the same for client and server.
Specification file:

    markov-action-model.maude --- data structure
    user-action-actor.maude  ---  interpreter
    mas-mamodel.maude       --- one example for mastodon
    fake-mastodon.maude  
    enc-dec-actor.maude --- destini    

Interfaces for RB actors are specfied in
    cp2-interfaces.maude              

The RB content managers are specified in
    cm-aux.maude              
    rb-cm-client.maude        
    rb-cm-server.maude        
including single actor tests exercising all the rules

RB client, server and client-server test configurations
are defined in 
    rb-integration.maude
along with sample commands for executing test scenarios.  

  RB client (rbc) with one or two files to exfil
  RB server (rbs) with one or two weird hashtags
    FMA with no toots or FMA primed with toots from the 
       rbc two file scenario
   A rule is added to receive and report message to bob
   (owise execution halts)
!!!!
  RB client + RB server sharing the FMA -- succeeds in
    exfilling a one fragment file and a 2 fragment file.

Note: the experiment were mainly run without any link data,
thus link delay defaults to a small noise factor.
Adding link delay between RB and MASTODON has no observable
effect,  the timing is controlled by the user model here.

The directory RB-Runs contains results of runs of scenarios in rb-integration (after set-print-attribute on).
The beginning of the file has the command used.

Useful  search strings:

rbc-rcv-file  -- to see events where the rb client receives a file
wHashTag(0) --- to see events involving weird hashtag 0
wHashTag(1) ---  ditto for 1
rbs-rcv-hashtag --- RB server gets hashtag for fetches
bob-rcv-efile --- RB server has assembled file and sent to bob

The RaceBoat directory also includes data structure
specifications used elsewhere. To integrate one will need to
decide where these files live, and fix the sload commands
accordingly
    byteseq.maude             
    json.maude  
    my-sampler.maude 
NB byteseq has some additional definitions from previous version    

Additional documentation
toc-X.txt -- intended to aid integration
   toc-common.txt  -- shared modules
   toc-dns-tgen.txt --- DNS traffic generation
   toc-rb.txt --- Raceboat specific

   for each maude file listed the toc file lists
      the files loaded, 
      the modules defined 
        (the module's inclusions)
      
rb-cm-msgs.txt --- a summary of the lables  of rules
   for receiving each receivable message

Readme.txt

