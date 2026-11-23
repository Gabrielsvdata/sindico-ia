#!/usr/bin/env bash
# Envia as mensagens de exemplo para o webhook do n8n (ou direto para a API com ALVO=api)
set -euo pipefail
cd "$(dirname "$0")"

if [ "${ALVO:-n8n}" = "api" ]; then
  URL="http://localhost:8000/mensagens"
else
  URL="http://localhost:5678/webhook/sindico"
fi

python3 -c 'import json,sys; [print(json.dumps(m, ensure_ascii=False)) for m in json.load(open("mensagens.json"))]' |
while read -r msg; do
  echo ">>> $msg"
  curl -s -X POST "$URL" -H "Content-Type: application/json" -d "$msg"
  echo -e "\n"
done
