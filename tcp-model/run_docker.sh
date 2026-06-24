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

# Capture user flags (like --cached or --tc_profile) to pass directly into the Python container script
EXTRA_PARAMS=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --cached)
            EXTRA_PARAMS="$EXTRA_PARAMS --cached"
            shift
            ;;
        --tc_profile)
            EXTRA_PARAMS="$EXTRA_PARAMS --tc_profile $2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

# Run the Docker container
# 1. --rm removes the container after it finishes
# 2. --privileged is REQUIRED for Linux network namespaces (ip netns) and tc qdisc
# 3. -v $(pwd):/app mounts the current directory so the script can write the plot and npy cache files directly to your host machine
echo "=== Running Experiment in Docker Container ==="
docker run --rm --privileged $NET_FLAG -v "$(pwd):/app" tcp-validation-env python3 tcp_validation.py $EXTRA_PARAMS

echo "=== Done ==="
echo "You should see tcp_validation_plot.png and empirical_data.npy in this folder."