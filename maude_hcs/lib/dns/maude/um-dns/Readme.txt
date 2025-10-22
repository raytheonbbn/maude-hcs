User action model and DNS traffic generator specification

To run (in CP1 environment) put this folder at the same level as the CP1 test or probablistic folders

toc-um-dns.txt lists the files, what each file loads
and the modules defined -- trying to keep track of
dependencies

General cp2 files
 byteseq.maude   
   defines sorts ByteSeq, ByteSeqL and constructors
    for files, encrypted files, file fragments, images,
    and images with embedded content.
            
 json.maude  
   defines a representation of JSON in Maude
     uses sort JV and injection functions
     jn/js/jl/jo from Nat/String/List{JV}/Map{String,JV}
     to JV -avoids putting many sorts in the same kind

 my-sampler.maude
   versions of some sampling functions that take an
   index to generate next random numbers rather than
   using the builtin counter object.
   Using this to support future transformations

 cp2-interfaces.maude  
   and CP2-COMMON -- a bunch of shared definitions,
   including rCtr(j) an `actor' used to share the
   current random sequence index

Actor specifications
  markov-action-model.maude 
    specifies the structure of markov-action models (MAm)
     (contents of T&E action configuration files)
  dns-mamodel.maude   
    example DNS MAm -- used to test
  user-action-actor.maude
    specifies behavior of a generic user-action model
      constructor parameterized by a MAm
      a user-action actor drives a traffic generator via
       actionQ(actionspec), actionR(code) message content
         actionspec is the (rendered) element of the
         MAm current action
         
  dnsTgen-actor.maude 
   defines DNS traffic generator actor
   includes test module and maude commands
      testing each msg receive case 

  fake-rsv.maude 
    defines a fake resolver actor (that replies with
       empty response) for basic testing

  ../test/test-um-dns.maude   
    basic test modules for testing all rules
     of user model and dns tgen fire as expected
    uses fakeRSV and DNS modules for scheduling  
    see example rewrite after the eof
   
  ../test/test-um-dns-cp1.maude 
   a cp1 configuration modified to have only dns actors
     and the dns traffic generator actors
   see example rewrite after the eof
        
 
