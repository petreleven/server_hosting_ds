#!/bin/sh
set -e

cd /valheim

exec ./valheim_server.x86_64 -nographics -batchmode \
    -name       "${SERVER_NAME}" \
    -port       "${PORT}" \
    -world      "${WORLD}" \
    -password   "${PASSWORD}" \
    -public     "${PUBLIC}" \
    -savedir    "${SAVEDIR:-/valheim-saves}" \
    -logfile    "${LOGFILE:-/valheim/valheim.log}" \
    -saveinterval "${SAVEINTERVAL}" \
    -backups    "${BACKUPS}" \
    -backupshort "${BACKUPSHORT}" \
    -backuplong  "${BACKUPLONG}" \
    -crossplay  "${CROSSPLAY}" \
    -preset     "${PRESET}" \
    -modifier   "${MODIFIER}" \
    -setkey     "${SETKEY}"
