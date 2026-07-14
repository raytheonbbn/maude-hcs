import os
import re

def process_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # sload modifications
    content = content.replace("sload ../../irc/irc_prob.maude", "sload ../../irc/irc_prob-v2.maude\nsload ../../irc/irc-mamodel-v2.maude\nsload ../../common/maude/irc-action-actor-v2.maude")
    content = content.replace("sload ../../irc/irc_prob", "sload ../../irc/irc_prob-v2\nsload ../../irc/irc-mamodel-v2\nsload ../../common/maude/irc-action-actor-v2")
    content = content.replace("sload ../../irc/irc_monitor", "sload ../../irc/ircMonitor")
    
    # inc modifications
    content = content.replace("inc IRC .", "inc IRC-V2 .\n  inc IRC-USER-ACTION-ACTOR-V2 .\n  inc IRC-MAMODEL-V2 .")
    
    # mkIrcClient modifications
    # Match mkIrcClient(ircAddr, ifaceAddr, ...)
    def replace_client(match):
        args = match.group(1).split(',')
        ircAddr = args[0].strip()
        ifaceAddr = args[1].strip()
        userId = '"irc_user"'
        if len(args) > 2:
            userId = args[2].strip()
        return f"mkIrcClient-v2({ircAddr}, {ifaceAddr}, {userId})"
    
    content = re.sub(r'mkIrcClient\s*\(([^)]+)\)', replace_client, content)
    
    with open(filepath, 'w') as f:
        f.write(content)

for root, dirs, files in os.walk('maude_hcs/lib/cp3-tests'):
    for file in files:
        if file.endswith('.maude'):
            filepath = os.path.join(root, file)
            with open(filepath, 'r') as f:
                if 'mkIrcClient' in f.read():
                    print(f"Processing {filepath}")
                    process_file(filepath)
