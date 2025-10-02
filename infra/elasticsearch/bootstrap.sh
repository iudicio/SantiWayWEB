#!/usr/bin/bash
set -euo pipefail
ES_URL="${ES_URL:-http://elasticsearch:9200}"

echo "→ wait for ES at $ES_URL ..."
until curl -fsS "$ES_URL" >/dev/null; do sleep 1; done

echo "→ apply ILM policy"
curl -fsS -X PUT "$ES_URL/_ilm/policy/way-rollover-100m" \
  -H 'Content-Type: application/json' \
  --data-binary @infra/elasticsearch/ilm/way-100m.policy.json

echo "→ put ingest pipeline"
curl -fsS -X PUT "$ES_URL/_ingest/pipeline/way-normalize" \
  -H 'Content-Type: application/json' \
  --data-binary @infra/elasticsearch/pipelines/way.normalize.json

echo "→ apply index template"
curl -fsS -X PUT "$ES_URL/_index_template/way-template" \
  -H 'Content-Type: application/json' \
  --data-binary @infra/elasticsearch/templates/way.index-template.json

echo "→ create initial index + write alias (idempotent)"
if ! curl -fsS "$ES_URL/way-000001" >/dev/null; then
  curl -fsS -X PUT "$ES_URL/way-000001" \
    -H 'Content-Type: application/json' \
    -d '{"aliases":{"way":{"is_write_index":true}}}'
fi

echo "✓ done. Write to alias '\''way'\''"
