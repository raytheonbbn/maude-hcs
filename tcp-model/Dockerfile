FROM ubuntu:22.04

# Prevent interactive prompts from tzdata and other packages
ENV DEBIAN_FRONTEND=noninteractive

# Install required system tools for networking and python
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    iproute2 \
    tcpdump \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip3 install numpy scapy matplotlib

# Set working directory
WORKDIR /app

# The python script will be mounted into /app at runtime
# so we don't necessarily need to copy it during build
CMD ["python3", "tcp_validation.py"]
