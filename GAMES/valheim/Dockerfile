FROM cm2network/steamcmd:latest

# Switch to root to install additional dependencies
USER root

# Install additional runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libatomic1 \
        libpulse-dev \
        wget \
        unzip \
        libpulse0 && \
    rm -rf /var/lib/apt/lists/*

# Create server directory
RUN mkdir -p /home/steam/server /valheim

# Copy and make scripts executable
COPY scripts /home/steam/server/scripts
RUN chmod +x /home/steam/server/scripts/*.sh

# Download and unpack BepInEx mod-loader pack
ENV BEPINEX_VERSION=5.4.2202
RUN wget -qO /tmp/BepInExPack.zip \
      "https://gcdn.thunderstore.io/live/repository/packages/denikson-BepInExPack_Valheim-${BEPINEX_VERSION}.zip" && \
    unzip -q /tmp/BepInExPack.zip -d /home/steam/server/BepInEx && \
    rm /tmp/BepInExPack.zip

# Move the inner BepInEx directory into the Valheim root
RUN mv /home/steam/server/BepInEx/BepInExPack_Valheim/BepInEx /valheim/BepInEx

# Set correct permissions
RUN chown -R steam:steam /home/steam
RUN chown -R steam:steam /valheim

# Switch to steam user for installation
USER steam

# Run the install script
RUN /home/steam/server/scripts/install.sh

# Default startup command
CMD ["/bin/bash", "-c", "/home/steam/server/scripts/start.sh"]
