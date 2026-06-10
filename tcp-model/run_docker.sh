#!/bin/bash
set -e

# Build the Docker image
echo "=== Building Docker image ==="
docker build -t tcp-validation-env .

# Run the Docker container
# 1. --rm removes the container after it finishes
# 2. --privileged is REQUIRED for Linux network namespaces (ip netns) and tc qdisc
# 3. -v $(pwd):/app mounts the current directory so the script can write the plot and pcap files directly to your host machine
echo "=== Running Experiment in Docker Container ==="
docker run --rm --privileged -v "$(pwd):/app" tcp-validation-env python3 tcp_validation.py

echo "=== Done ==="
echo "You should see tcp_validation_plot.png and capture.pcap in this folder."
