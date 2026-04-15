FROM iterare-base:latest

# Install required packages
USER root
RUN apt-get update && \
    apt-get install -y jq && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy and install custom firewall script that reads from config
COPY docker/init-firewall.sh /usr/local/bin/init-firewall.sh
RUN chmod +x /usr/local/bin/init-firewall.sh

USER node

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

# Add uv to PATH
ENV PATH="/home/node/.local/bin:${PATH}"

# Copy entrypoint script
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
USER root
RUN chmod +x /usr/local/bin/entrypoint.sh
USER node

# Set entrypoint
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
