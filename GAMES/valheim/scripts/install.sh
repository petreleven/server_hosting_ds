#!/bin/sh
set -e
echo "Installing/updating valheim server...."

INSTALL_DIR=/valheim
/home/steam/server/script.sh  +@sSteamCmdForcePlatformType linux \
    +login anonymous \
    +force_install_dir "$INSTALL_DIR" \
    +app_update 896660 validate \
    +quit

echo "Copying BepInEx into game folder..."
cp /home/steam/server/BepInEX/*  "$INSTALL_DIR"

echo "Launching Valheim server with BepInEx..."
exec /home/steam/server/scripts/start.sh
