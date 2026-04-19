#!/usr/bin/env bash
# Один прогон: ./single_run.sh <broker> <msg_size> <rate> <duration>
# broker = rabbit | redis
set -euo pipefail

BROKER="${1:-rabbit}"
MSG_SIZE="${2:-1024}"
RATE="${3:-1000}"
DURATION="${4:-30}"
GRACE="${GRACE_SEC:-5}"
WARMUP="${WARMUP_SEC:-2}"

RUN_ID="smoke_${BROKER}_${MSG_SIZE}_${RATE}"
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"

case "$BROKER" in
  rabbit) COMPOSE="$ROOT/docker-compose.rabbit.yml" ;;
  redis)  COMPOSE="$ROOT/docker-compose.redis.yml" ;;
  *) echo "unknown broker: $BROKER" >&2; exit 2 ;;
esac

PROJECT="bench_${BROKER}"

export RUN_ID MSG_SIZE RATE
export DURATION_SEC="$DURATION"
export GRACE_SEC="$GRACE"
export WARMUP_SEC="$WARMUP"

echo "=== $RUN_ID ==="
docker compose -p "$PROJECT" -f "$COMPOSE" up -d --build

CID="$(docker compose -p "$PROJECT" -f "$COMPOSE" ps -q consumer | head -n1)"
docker wait "$CID" || true

docker compose -p "$PROJECT" -f "$COMPOSE" logs --tail 50 consumer
docker compose -p "$PROJECT" -f "$COMPOSE" logs --tail 20 producer
docker compose -p "$PROJECT" -f "$COMPOSE" down -v

echo "Results in: $ROOT/results/raw/${RUN_ID}_{producer,consumer}.json"
