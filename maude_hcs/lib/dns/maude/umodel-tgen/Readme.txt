Initial version of User Model specification and DNS traffic generator

put this folder at the same level as the CP1 test or probablistic
folders

user-model-aux.maude  
   ---- sorts shared by user model and traffic generators

user-model.maude  
   ---- formalization of T&E user model 
   ---- actor type UM,  model sort MModel
   
dnsTask.maude     
   ---- dns traffic generator   

test-um-dns.maude   
   ---- basic test modules for testing all rules fire as expected
   ---- uses fakeRSV and some DNS modules for scheduling  
   ---- see example rewrite after the eof
   
test-um-dns-cp1.maude 
   ---- cp1 configuration modified to have only dns actors
        and the dns traffic generator (user model + task actors)
   ---- see example rewrite after the eof
        
 