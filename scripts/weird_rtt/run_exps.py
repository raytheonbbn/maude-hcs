import argparse
import subprocess
import signal
import logging
import sys
import time

client = None
server = None
logger = None

def sigint_handler(sig, frame):
    logger.info("caught SIGINT, stopping client...")
    try:
        client.send_signal(signal.SIGINT)
        client.wait(timeout = 5)
        logger.info("Client exited")
        # Server should exit immediately after client stops, otherwise wait a little longer

        server.wait(timeout = 1)
        logger.info("Server exited")
    except subprocess.TimeoutExpired:
        logger.info("Either client or server didn't exit, shutting down forcefully")
        client.terminate()
        logger.info("Terminated client")
        server.terminate()
        logger.info("Terminated server")


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
        '-r', '--seed',
        type=int,
        default=0,
        help='Random seed to use (default: 0)'
    )
    
    parser.add_argument(
        '-n', '--num',
        type=int,
        default=None,
        help='Output to a file with the given name as a suffix'
    )

    parser.add_argument(
        '-e', '--expname',
        type=str,
        default=str(int(time.time())),
        help='Output to a file with the given name as a suffix. Refuses to overwrite existing log file with same name. File output disabled without this flag.'
    )

    parser.add_argument(
        '-i', '--initcount',
        type=int,
        default=1,
        help='Starting value of message counter used to seed the salt RNG for client and server (default:1)'
    )
    
    # You would then pass 'port' into your socket functions:
    # s.bind(('localhost', port))  # For Server
    # s.connect(('localhost', port)) # For Client
    args = parser.parse_args()

    # Catch SIGINT
    signal.signal(signal.SIGINT, sigint_handler)
    cmd_client = [sys.executable, 'weird_rtt_client.py',
                  '-p', str(args.port),
                  '-i', str(args.initcount),
                  '-r', str(args.seed)]
    
    cmd_server = [sys.executable, 'weird_rtt_server.py',
                  '-p', str(args.port),
                  '-i', str(args.initcount)]
    
    if args.num is not None:
        cmd_num = ['-n', str(args.num)]
        cmd_client += cmd_num

    if args.expname is not None:
        cmd_expname = ['-e', args.expname]
        cmd_client += cmd_expname
        cmd_server += cmd_expname
                  
    logger = logging.getLogger('MAIN')
    logger.setLevel(logging.INFO)
    outFormatter = logging.Formatter('[%(asctime)s.%(msecs)03d] : %(name)s : %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    console.setFormatter(outFormatter)
    logger.addHandler(console)

    expname = args.expname

    if expname is not None:
        try:
            file_log = logging.FileHandler(f'main-{expname}.log', mode='x', encoding='utf-8')
        except FileExistsError:
            logger.error(f"Refusing to overwrite existing file main-{expname}.log")
            sys.exit(1)
        file_log.setLevel(logging.INFO)
        file_log.setFormatter(outFormatter)
        logger.addHandler(file_log)

    server = subprocess.Popen(cmd_server, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    logger.info("Started server")
    client = subprocess.Popen(cmd_client, shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    logger.info("Started client")

    (client_stdout, client_stderr) = client.communicate()

    if client.returncode != 0:
        logger.info("Client had an error, stopping server too")
        try:
            server.send_signal(signal.SIGINT)
            server.wait(timeout = 5)
            logger.info("Server exited")
        except subprocess.TimeoutExpired:
            logger.info("Server didn't exit, shutting down forcefully")
            server.terminate()
            logger.info("Terminated server")

    (server_stdout, server_stderr) = server.communicate()
    
    logger.info("Done")


    
    
