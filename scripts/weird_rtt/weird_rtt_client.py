import argparse
import signal
import socket
import time
import weird_rtt_embed
import random
import logging
import sys

running = True
def sigint_handler(sig, frame):
   print(f"Client: caught SIGINT")
   global running 
   running = False

def start_client(args):
    listen_port = args.port
    seed = args.seed
    expname = args.expname
    n = args.num

    # Counter used to seed the salt RNG
    count = args.initcount


    runs = 0

    logger = logging.getLogger('CLIENT')
    logger.setLevel(logging.INFO)
    outFormatter = logging.Formatter('[%(asctime)s.%(msecs)03d] : %(name)s : %(levelname)s : %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(outFormatter)
    logger.addHandler(console)
    if expname is not None:
        try:
            file_log = logging.FileHandler(f'client-{expname}.log', mode='x', encoding='utf-8')
        except FileExistsError:
            logger.error(f"Refusing to overwrite existing file client-{expname}.log")
            sys.exit(1)
        file_log.setLevel(logging.INFO)
        file_log.setFormatter(outFormatter)
        logger.addHandler(file_log)
    
    # Create a TCP/IP socket
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    returncode = 0
    try:
        # Connect to the server
        client_socket.connect((args.server_address, listen_port))
        rng = random.Random(seed)
        logger.info(f"Starting with random seed {seed}")
        while running and ((n is None) or (runs < n)):
          # Send the current timestamp
          weird_data = 0 if args.blank else  rng.getrandbits(8)
          send_timestamp = weird_rtt_embed.time64b()
          client_timestamp = str(weird_rtt_embed.rtt_embed(send_timestamp, count, weird_data))
          
          logger.info(f"timestamp_orig: {send_timestamp}; timestamp_weird: {client_timestamp}; containing encoded data: {weird_data}; count: {count}; entropy_original: {weird_rtt_embed.tsEntropy(send_timestamp, 8)}; entropy_weird: {weird_rtt_embed.tsEntropy(int(client_timestamp), 8)}")
          client_socket.sendall(client_timestamp.encode())
          
          # Receive the server's timestamp
          server_data = client_socket.recv(1024).decode()
          server_data_split = server_data.split(",")
          recvd_client_timestamp = int(server_data_split[0])
          recvd_server_timestamp = int(server_data_split[1])
          recv_time = weird_rtt_embed.time64b()
          time_send = (recv_time - recvd_server_timestamp)
          time_recv = (recvd_server_timestamp - recvd_client_timestamp)
          rtt = time_send + time_recv
          logger.info(f"Received server_timestamp: {server_data}; current_time:{recv_time/1e6} up: {time_send}us; down: {time_recv}us; RTT: {rtt}us")
          count += 1
          runs += 1

          time.sleep(1)
    except Exception as e:
        logger.exception(f"Error! {e}")
        returncode = 1
    finally:
        logger.info("Stopping client")
        client_socket.close()
        logger.info("Stopped client")
        sys.exit(returncode)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TCP Timestamp Client/Server")
    
    # Define the port argument
    # type=int ensures the input is a number
    # default=65432 provides a fallback if the user skips it
    parser.add_argument(
        '-p', '--port', 
        type=int, 
        default=65432, 
        help='Port number to use (default: 65432)'
    )

    parser.add_argument(
        '-s', '--server_address',
        type = str,
        default = "10.0.0.1",
        help = "Server address (default 10.0.0.1)"
    )

    parser.add_argument(
        '-b', '--blank',
        action = "store_true",
        default = False,
        help = "Send no weird data"
    )

    parser.add_argument(
        '-r', '--seed',
        type=int,
        default=42,
        help='Random seed to use for random data (default: 42)'
    )

    parser.add_argument(
        '-i', '--initcount',
        type=int,
        default=0,
        help='Starting value of message counter used to seed the salt RNG. Must match server initcount (default:0)'
    )

    parser.add_argument(
        '-e', '--expname',
        type=str,
        default=None,
        help='Output to a file with the given name as a suffix. Refuses to overwrite existing log file with same name. File output disabled without this flag.'
    )
    
    parser.add_argument(
        '-n', '--num',
        type=int,
        default=None,
        help='Number of experiments to run. Runs indefinitely without this flag.'
    )
    
    # You would then pass 'port' into your socket functions:
    # s.bind(('localhost', port))  # For Server
    # s.connect(('localhost', port)) # For Client
    args = parser.parse_args()

    # Catch SIGINT
    signal.signal(signal.SIGINT, sigint_handler)
    
    start_client(args)


