import re
import os

files_to_fix = {
    'all/test_spotcheck1.maude': 'ircClient1Addr ; ircClient2Addr ; ircClient3Addr ; ircClient4Addr ; ircClient5Addr ; ircTgenClientAddr',
    'all/test_spotcheck1_no_tgen.maude': 'ircClient1Addr ; ircClient2Addr ; ircClient3Addr ; ircClient4Addr ; ircClient5Addr',
    'webtunnel/test_webtunnel_irc_net.maude': 'ircClient1Addr ; ircClient2Addr',
    'iodine/test_iodine_irc_net.maude': 'aliceIrcClientAddr ; bobIrcClientAddr',
    'obfs4/test_obfs4_irc_net.maude': 'aliceIrcClientAddr ; bobIrcClientAddr',
    'mastodon/test_mastodon_irc_net.maude': 'ircaAddr ; ircbAddr ; irccAddr',
    'skyhook/test_skyhook_irc_net.maude': 'ircaAddr ; ircbAddr',
    'fake-dns-test/test_skyhook_irc_net.maude': 'ircaAddr ; ircbAddr'
}

for fname, addrs in files_to_fix.items():
    if not os.path.exists(fname):
        print(f"File {fname} not found, skipping...")
        continue
        
    with open(fname, 'r') as f:
        content = f.read()
        
    if "op allClientsAddr :" in content:
        print(f"Skipping {fname}, already has allClientsAddr")
        continue
        
    # find the last 'endm'
    idx = content.rfind('\nendm\n')
    if idx == -1:
        print(f"Could not find endm in {fname}")
        continue
        
    insert = f"\n  op allClientsAddr : -> AddrList .\n  eq allClientsAddr = {addrs} .\n"
    new_content = content[:idx] + insert + content[idx:]
    
    with open(fname, 'w') as f:
        f.write(new_content)
    
    print(f"Updated {fname}")
