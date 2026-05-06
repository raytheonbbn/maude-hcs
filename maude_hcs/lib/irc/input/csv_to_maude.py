import csv
import sys
import os

def process_csv(input_csv, module_name, op_name, output_file):
    with open(input_csv, 'r') as f:
        lines = f.readlines()
        
    messages = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split(',', 2)
        if len(parts) == 3:
            time_str, room, msg = parts
            room = room.replace('#', '')
            messages.append(f'({time_str} ~> ("{msg}", makeIrcChannelName("{room}")))')
            
    with open(output_file, 'w') as f:
        f.write(f"mod {module_name} is\n")
        f.write("  pr APP_CHATS .\n")
        f.write(f"  op {op_name} : -> AppChatsMap .\n")
        f.write(f"  eq {op_name} = \n")
        if messages:
            f.write("    " + "\n    : ".join(messages) + "\n  .\n")
        else:
            f.write("    emptyAppChatsMap .\n")
        f.write("endm\n")

if __name__ == '__main__':
    input_csv = sys.argv[1]
    output_file = sys.argv[2]
    module_name = sys.argv[3]
    op_name = sys.argv[4]
    process_csv(input_csv, module_name, op_name, output_file)
