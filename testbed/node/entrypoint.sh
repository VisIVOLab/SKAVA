#!/bin/sh
# Entrypoint of a testbed node: the VisIVO backend, behind a shaped link.
#
#   NETEM_DELAY   delay added to the node's egress (e.g. 80ms); empty = none
#   NETEM_RATE    egress bandwidth (e.g. 100mbit); empty = unlimited
#   BUSY_WORKERS  CPU-bound processes started next to the backend, so the node
#                 is genuinely loaded (they share its CPU quota); 0 = idle
#
# Only egress is shaped, so every round trip to the node gains NETEM_DELAY
# once, for SKAVA's probes and for clients alike.
set -e

if [ -n "${NETEM_DELAY}${NETEM_RATE}" ]; then
    tc qdisc replace dev eth0 root netem \
        ${NETEM_DELAY:+delay "$NETEM_DELAY"} ${NETEM_RATE:+rate "$NETEM_RATE"}
    echo "netem on eth0: delay=${NETEM_DELAY:-0} rate=${NETEM_RATE:-unlimited}"
fi

i=0
while [ "$i" -lt "${BUSY_WORKERS:-0}" ]; do
    python -c 'while True: pass' &
    i=$((i + 1))
done
[ "${BUSY_WORKERS:-0}" -gt 0 ] && echo "started $BUSY_WORKERS busy workers"

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
