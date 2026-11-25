# n8n com os fluxos do Síndico IA embutidos (deploy no Render)
FROM n8nio/n8n:2.35.7

USER root
COPY n8n/*.json /fluxos/
COPY deploy/n8n-iniciar.sh /iniciar.sh
RUN chmod 755 /iniciar.sh && chown -R node:node /fluxos
USER node

ENV N8N_PORT=5678 \
    N8N_PROTOCOL=https \
    N8N_DIAGNOSTICS_ENABLED=false \
    N8N_PERSONALIZATION_ENABLED=false \
    GENERIC_TIMEZONE=America/Sao_Paulo \
    TZ=America/Sao_Paulo

EXPOSE 5678
ENTRYPOINT ["tini", "--", "/iniciar.sh"]
