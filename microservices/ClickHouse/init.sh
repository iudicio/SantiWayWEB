#!/usr/bin/env bash
set -euo pipefail

: "${APP_USER:?}"
: "${APP_PASSWORD:?}"
: "${APP_ALLOWED_IPS:?}"

# --- собираем HOST IP '...' ---
HOSTS=""
IFS=',' read -ra IPS <<< "$APP_ALLOWED_IPS"
for ip in "${IPS[@]}"; do
  ip="$(echo "$ip" | xargs)"
  [ -z "$ip" ] && continue
  if [ -z "$HOSTS" ]; then
    HOSTS="HOST IP '$ip'"
  else
    HOSTS="$HOSTS, IP '$ip'"
  fi
done

# --- экранируем значения ---
USER_ESC="\\\`${APP_USER}\\\`"
PASS_ESC="'${APP_PASSWORD//\'/\'\'}'"

# --- рендерим SQL ---
sed \
  -e "s|{{USER}}|${USER_ESC}|g" \
  -e "s|{{PASSWORD}}|${PASS_ESC}|g" \
  -e "s|{{HOSTS}}|${HOSTS}|g" \
  /schema.sql > /tmp/schema.rendered.sql

# --- выполняем ---
clickhouse-client --host=clickhouse --user=default --multiquery < /tmp/schema.rendered.sql
