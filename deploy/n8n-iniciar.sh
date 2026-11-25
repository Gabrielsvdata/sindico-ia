#!/bin/sh
# Inicia o n8n já com os fluxos do Síndico IA importados e o fluxo de atendimento publicado.
# Usado no Render, onde o plano gratuito não guarda disco entre reinícios.
set -e

if [ -z "$API_URL" ]; then
  echo "ERRO: defina API_URL com o endereço público da API (ex.: https://sindico-ia-api.onrender.com)" >&2
  exit 1
fi

# Endereço público do próprio n8n (o Render informa em RENDER_EXTERNAL_URL)
export WEBHOOK_URL="${WEBHOOK_URL:-${RENDER_EXTERNAL_URL}/}"

# Os fluxos do repositório chamam http://api:8000 (nome do serviço no docker-compose).
# Aqui trocamos pelo endereço público da API.
ORIGEM="${FLUXOS_DIR:-/fluxos}"
mkdir -p /tmp/fluxos
for arquivo in "$ORIGEM"/*.json; do
  sed "s#http://api:8000#${API_URL%/}#g" "$arquivo" > "/tmp/fluxos/$(basename "$arquivo")"
done

n8n import:workflow --separate --input=/tmp/fluxos
n8n publish:workflow --id=SindicoIaAtend01

exec n8n start
