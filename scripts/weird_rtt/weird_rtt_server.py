import argparse
import socket
import weird_rtt_embed
import signal
import logging
import sys

running = True
server_socket = None

def sigint_handler(sig, frame):
   print(f"Server: caught SIGINT, closing ports...")
   global running 
   running = False
   if server_socket is not None:
      server_socket.close()

def start_server(args):
    expname = args.expname

    logger = logging.getLogger('SERVER')
    logger.setLevel(logging.INFO)
    outFormatter = logging.Formatter('[%(asctime)s.%(msecs)03d] : %(name)s : %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(outFormatter)
    logger.addHandler(console)

    if expname is not None:
        try:
            file_log = logging.FileHandler(f'server-{expname}.log', mode='x', encoding='utf-8')
        except FileExistsError:
            logger.error(f"Refusing to overwrite existing file server-{expname}.log")
            sys.exit(1)
        file_log.setLevel(logging.INFO)
        file_log.setFormatter(outFormatter)
        logger.addHandler(file_log)

    listen_port = args.port
    # Create a TCP/IP socket
    global server_socket
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    # Bind the socket to the address and port
    server_socket.bind(("0.0.0.0", listen_port))
    server_socket.listen(1)
    logger.info("Server is listening for a connection...")

    
    count = args.initcount
    global running
    returncode = 0
    conn,addr = None,None
    try:
      conn, addr = server_socket.accept()
      logger.info(f"Connected by {addr}")
    except OSError as e:
       logger.info(f"Socket likely closed before client connected: {e}")
    try:
      while running:
        # Receive the client's timestamp
        client_timestamp = conn.recv(1024).decode()
        try:
          extracted_data = weird_rtt_embed.rtt_extract(int(client_timestamp), count)
        except ValueError as e:
            logger.info(f"Unable to extract string '{client_timestamp}' (probably client stopped)")
            running = False
            continue

        count = (count + 1)
        logger.info(f"Received from client: {client_timestamp}, extracted data: {extracted_data} with count: {count}")
        
        # Send the server's timestamp back
        server_timestamp = str(weird_rtt_embed.time64b())
        response = f"{client_timestamp},{server_timestamp}"
        conn.sendall(response.encode())
        logger.info(f"Sent to client: {response}")
          
    except Exception as e:
      logger.exception(f"Error! {e}")
      returncode = 1
    
    finally:
        logger.info("Stopping server")
        if conn is not None:
          conn.close()
        
        server_socket.close()
        logger.info("Server stopped")
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
        '-e', '--expname',
        type=str,
        default=None,
        help='Output to a file with the given name as a suffix. Refuses to overwrite existing log file with same name. File output disabled without this flag.'
    )

    parser.add_argument(
        '-i', '--initcount',
        type=int,
        default=0,
        help='Starting value of message counter used to seed the salt RNG Must match client initcount. (default:0)'
    )
    args = parser.parse_args()

    # Catch SIGINT
    signal.signal(signal.SIGINT, sigint_handler)

    start_server(args)
