#!/bin/sh

cd /valheim

exec ./valheim_server.x86_64 -nographics -batchmode \
    -name       "${SERVER_NAME}"        \  # :contentReference[oaicite:0]{index=0}
    -port       "${PORT}"               \  # :contentReference[oaicite:1]{index=1}
    -world      "${WORLD}"              \  # :contentReference[oaicite:2]{index=2}
    -password   "${PASSWORD}"           \  # :contentReference[oaicite:3]{index=3}
    -savedir    "${SAVEDIR:-/valheim-saves}" \  # :contentReference[oaicite:4]{index=4}
    -public     "${PUBLIC}"             \  # :contentReference[oaicite:5]{index=5}
    -logFile    "${LOGFILE:-/valheim/valheim.log}" \  # :contentReference[oaicite:6]{index=6}
    -saveinterval "${SAVEINTERVAL}"     \  # :contentReference[oaicite:7]{index=7}
    -backups    "${BACKUPS}"            \  # :contentReference[oaicite:8]{index=8}
    -backupshort "${BACKUPSHORT}"       \  # :contentReference[oaicite:9]{index=9}
    -backuplong  "${BACKUPLONG}"        \  # :contentReference[oaicite:10]{index=10}
    -crossplay    "${CROSPLAY}"          \  # :contentReference[oaicite:11]{index=11}
    -preset      "${PRESET}"             \  # :contentReference[oaicite:12]{index=12}
    -modifier    "${MODIFIER}"           \  # :contentReference[oaicite:13]{index=13}
    -setkey      "${SETKEY}"                # :contentReference[oaicite:14]{index=14}
