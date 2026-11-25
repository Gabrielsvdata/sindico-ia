# 📸 Roteiro de prints

Salve cada imagem em `docs/prints/` **com exatamente este nome**. O README já aponta para eles.

Antes de começar: `docker compose up -d`, importe os fluxos, **ative/publique** o fluxo 1 e envie mensagens pelo painel (http://localhost:8000) no modo **via n8n**, ou rode `./exemplos/testar.sh`. Envie também uma dúvida frequente (ex.: piscina) duas vezes para aparecer a economia de IA.

| # | Arquivo | O que mostrar | Onde no n8n |
|---|---|---|---|
| 01 | `01-fluxo-atendimento.png` | Fluxo 1 inteiro, todos os nodes visíveis | Abra o fluxo → atalho `Shift+1` (ajustar zoom) |
| 02 | `02-fluxo-escalonamento.png` | Fluxo 2 inteiro | idem |
| 03 | `03-fluxo-resumo.png` | Fluxo 3 inteiro | idem |
| 04 | `04-execucao-sucesso.png` | Uma execução com todos os nodes em verde | Aba **Executions** → clique em uma execução |
| 05 | `05-node-webhook.png` | Método POST, path `sindico`, Respond: "Using Respond to Webhook node" | Duplo clique no node |
| 06 | `06-node-edit-fields.png` | Os 4 campos e as expressões | Duplo clique, de preferência com o INPUT/OUTPUT de uma execução |
| 07 | `07-node-http-request.png` | URL, método POST e o JSON body | idem, mostrando o OUTPUT com a resposta da IA |
| 08 | `08-node-switch.png` | As 3 regras (emergencia / abrir_chamado / responder_automaticamente) | idem |
| 09 | `09-node-ramos.png` | Um dos 3 nodes de ramo (ex.: Emergência) com os campos | idem |
| 10 | `10-node-respond.png` | Respond With: JSON | idem |
| 11 | `11-resultado-emergencia.png` | Saída da mensagem "cheiro de gás" (prioridade crítica) | Execução → node final |
| 12 | `12-resultado-chamado.png` | Saída da mensagem "vazamento na garagem" | idem |
| 13 | `13-resultado-regimento.png` | Saída de "mudança no domingo" mostrando `trecho_regimento` | idem |
| 14 | `14-resultado-resumo.png` | Fluxo 3 executado (botão **Execute workflow**) com o relatório | Fluxo 3 → Execute |
| 15 | `15-painel.png` | Central com a fila cheia e um chamado aberto mostrando a conversa (mensagem, análise, avisos e ações da equipe) | http://localhost:8000 (use **Simular morador** pelo n8n, depois assuma, responda e resolva um chamado) |
| 16 | `16-metricas.png` | JSON de métricas mostrando `por_origem` e `chamadas_ia_economizadas` | http://localhost:8000/metricas |

**Dicas**
- Mostre o painel **INPUT | OUTPUT** aberto nos nodes: é isso que comprova que os dados passaram por cada etapa.
- Use a visualização **JSON** ou **Table** no OUTPUT para ficar legível.
- Bônus: um print do Swagger (`http://localhost:8000/docs`) e do `pytest -q` passando.
