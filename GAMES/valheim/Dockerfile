FROM cm2network/steamcmd

RUN apt-get update && apt-get install -y --no-install-recommends \
    libatomic1 \
    libpulse-dev \
    libpulse0

RUN mkdir -p /home/steam/server   /home/steam/steamcmd

RUN curl -sL "https://steamcdn-a.akamaihd.net/client/installer/steamcmd_linux.tar.gz" \
    | tar zxvf - -C /home/steam/steamcmd

COPY scripts /home/steam/server/scripts
RUN chmod +x home/steam/server/scripts/*.sh

ENV BEPINEX_VERSION=5.4.2202
RUN WGET -q0 /tmp/BenInExPack.zip \
    "https://gcdn.thunderstore.io/live/repository/packages/denikson-BepInExPack_Valheim-${BEPINEX_VERSION}.zip" && \
    unzip -q /tmp/BenInExPack.zip  -d /home/steam/server/BeniEx && \
    rm /tmp/BenInExPack.zip

