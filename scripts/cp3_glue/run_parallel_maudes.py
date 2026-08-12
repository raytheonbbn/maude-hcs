import sys
import os
import subprocess
from concurrent.futures import ProcessPoolExecutor

def run_maude_file(maude_file, log_file):
    """Runs a single maude file and pipes stdout to a log file."""
    try:
        with open(log_file, 'w') as f:
            # Run the maude command. 
            # We use subprocess.run and redirect stdout to the log file.
            # stderr is also redirected to the same log file to capture all output.
            subprocess.run(['maude', maude_file], stdout=f, stderr=subprocess.STDOUT, check=False)
    except Exception as e:
        print(f"Error running {maude_file}: {e}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python run_parallel_maudes.py <directory_of_maude_files>")
        sys.exit(1)

    maude_dir = sys.argv[1]
    if not os.path.isdir(maude_dir):
        print(f"Error: {maude_dir} is not a directory.")
        sys.exit(1)

    # Create logs directory
    logs_dir = os.path.join(maude_dir, 'logs')
    os.makedirs(logs_dir, exist_ok=True)

    # Find all .maude files in the directory
    maude_files = [f for f in os.listdir(maude_dir) if f.endswith('.maude')]
    
    if not maude_files:
        print("No .maude files found in the directory.")
        sys.exit(0)

    print(f"Found {len(maude_files)} maude files. Running in parallel...")

    # Prepare the list of (maude_file_path, log_file_path)
    tasks = []
    for f in maude_files:
        maude_path = os.path.join(maude_dir, f)
        log_name = f + '.log'
        log_path = os.path.join(logs_dir, log_name)
        tasks.append((maude_path, log_path))

    # Use ProcessPoolExecutor to run the maude files in parallel
    with ProcessPoolExecutor() as executor:
        # Submit each task to the executor
        futures = [executor.submit(run_maude_file, maude_path, log_path) for maude_path, log_path in tasks]
        # Wait for all tasks to complete and handle potential exceptions
        for future in futures:
            future.result()

    print("Done.")