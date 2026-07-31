
baseline.maude 

defines the modules 
  BASELINE -- the basic function for producing
  a basline monitor object

  RUN-BASELINE --- sets up the parameters for the
    feature computations and defines the vantage
    points and fetures of interest.
    I used a small set to test.
    Redefine as desired.
    
  TEST-BASELINE --- a `unit test' module
    not loaded without fiddling eofs

Its currently configured to use the ftp/mastodon
scenario I made for Minyoung.

To run a different scenario    
change the line

  sload test_skyhook_irc_net-only-tgen.maude

to load the scenario of choice.

CAVEATS

 The scenario should define the module HCS_TEST
 The scenario should declare a constant
   op hcsDelay : -> Float .
   eq hcsDelay = <the desired delay> [owise] .
 The HCS start messages should use delays of the form
    hcsDelay + offset
    The slimit constant should be defined with an [owise] .
 Then in RUN-BASELINE if you set
   slimit = <desired stop time> 
   hcsDelay = slimit + slimit 

If following endm of RUN-BASELINE you put
  rew initConfig
  q
  eof

and on the command line do

maude baseline > <fileName>.txt

The hcs computation will not start 
  and tgen baseline will appear afer the
  Maude banner and statistics in <fileName>.txt

The file bbb.txt has a sample output for a small set
of features.

I think the can also be used to produce the
analogous data for a run with hcs by suitable defining
hcsDelay.

You can also get hcs alone by simply commenting out
the start messages for tgen actors.


  

