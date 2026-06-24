#!/bin/bash
set -e

# Build the Docker image
echo "=== Building Docker image ==="
docker build -t tcp-validation-env .

NET_FLAG=""

# Check if running on macOS
if [[ "$OSTYPE" == "$darwin"* ]]; then
    echo "--- MacOS detected ---"

    # Check if the current Docker context or socket belongs to Colima
    if docker info 2>&1 | grep -iq "colima"; then
        echo "--> Colima detected: Safely enabling --net=host for VM kernel access."
        NET_FLAG="--net=host"
    fi
fi

# Capture user flags (like --cached) to pass directly into the Python container script
CACHED_PARAM=""
if [[ "$1" == "--cached" ]]; then
    CACHED_PARAM="--cached"
fi

# Run the Docker container
# 1. --rm removes the container after it finishes
# 2. --privileged is REQUIRED for Linux network namespaces (ip netns) and tc qdisc
# 3. -v $(pwd):/app mounts the current directory so the script can write the plot and npy cache files directly to your host machine
echo "=== Running Experiment in Docker Container ==="
docker run --rm --privileged $NET_FLAG -v "$(pwd):/app" tcp-validation-env python3 tcp_validation.py $CACHED_PARAM

echo "=== Done ==="
echo "You should see tcp_validation_plot.png and empirical_data.npy in this folder."
