# Como o Síndico IA funciona

## O problema

Em um condomínio, as mensagens dos moradores chegam misturadas: dúvidas repetidas ("a piscina abre segunda?"), reclamações (barulho, cobrança errada), pedidos de manutenção e, às vezes, emergências (cheiro de gás, alguém preso no elevador). Hoje alguém precisa ler tudo, entender o assunto, decidir a urgência e avisar a pessoa certa. As emergências se perdem no meio das dúvidas, e o síndico gasta horas respondendo as mesmas perguntas.

O Síndico IA faz essa triagem automaticamente: entende a mensagem, classifica, prioriza, responde o que pode ser respondido e avisa o setor responsável pelo resto.

## Visão geral

O projeto tem três partes, cada uma com um papel:

| Parte | Papel |
|---|---|
| **n8n** (automação) | Recebe a mensagem pelo webhook, chama a API e, conforme a resposta, decide o caminho: emergência, chamado para um setor ou resposta automática. Também roda as tarefas agendadas (escalonamento e resumo diário). |
| **API em FastAPI** (inteligência e dados) | Analisa a mensagem com IA, valida a resposta, aplica as regras de segurança, grava o chamado e guarda o histórico. |
| **Central de atendimento** (tela) | Onde o síndico e a equipe acompanham os chamados, conversam com o morador e resolvem. |

A IA fica na API, e não no n8n, de propósito: o n8n cuida do **fluxo** (receber, distribuir, avisar, agendar) e a API cuida da **inteligência** (IA, busca na base de conhecimento, validação e testes automáticos).

## O caminho de uma mensagem

**1. A mensagem chega.** O morador escreve, por exemplo: *"Tem água vazando do teto da garagem"*. O webhook do n8n recebe o texto, o nome, o apartamento e o canal (WhatsApp, Telegram, e-mail) e envia tudo para a API (`POST /mensagens`).

**2. Primeiro, tentar responder sem IA.** Antes de gastar uma chamada de IA, a API verifica duas coisas:
- **Perguntas frequentes:** 17 dúvidas comuns (horário da piscina, mudança, boleto, visitantes…) são reconhecidas por palavras-chave e respondidas na hora, com a regra oficial do regimento.
- **Respostas já dadas:** se a IA já respondeu a mesma dúvida nos últimos 7 dias, a resposta é reaproveitada.

Reclamações, mensagens que citam vizinhos e **qualquer emergência** nunca usam esses atalhos: vão sempre para a IA.

**3. RAG: buscar o que a IA pode usar.** Se a mensagem precisa da IA, a API busca na base de perguntas frequentes as **3 entradas mais parecidas** com a mensagem (busca BM25, a mesma técnica de motores de busca). Só essas 3 entradas vão para a IA, e não o regimento inteiro. Essa é a única fonte que a IA pode usar para responder dúvidas.

**4. A IA analisa.** O Gemini recebe um prompt estruturado com as regras de classificação, as 3 entradas da base e a mensagem. Ele devolve **somente um JSON** com: categoria, prioridade (baixa, média, alta, crítica), setor responsável, tom da mensagem, um resumo, a resposta para o morador, as fontes da base que usou e a confiança.

**5. Validar a resposta da IA.** A IA pode errar, então a API não confia cegamente:
- **Formato:** o JSON é validado (Pydantic). Se vier errado, o erro é devolvido à IA, que tenta de novo.
- **Contra alucinação:** a IA só pode citar entradas da base que ela recebeu. Citações inventadas são descartadas. Se ela diz que respondeu a dúvida, mas não cita nenhuma fonte válida, o chamado **não** é encerrado e vai para um humano.
- **Regra de segurança:** se a mensagem tiver termos como "cheiro de gás", "fumaça" ou "preso no elevador", a prioridade vira **crítica**, mesmo que a IA tenha classificado diferente.
- **Instabilidade do Gemini:** se o modelo estiver lento ou sobrecarregado, a API tenta de novo e passa para modelos reserva.

**6. A IA interpreta, o código decide.** A ação final é decidida por regras fixas no código, e não pela IA:
- prioridade crítica → **emergência**;
- dúvida respondida pela base, com fonte válida → **resposta automática** (o chamado já nasce resolvido);
- todo o resto → **chamado aberto** para o setor.

**7. Registrar tudo.** O chamado é gravado com um prazo conforme a prioridade (crítica 30 min, alta 4 h, média 24 h, baixa 72 h) e um histórico completo: a mensagem, a análise (com a fonte e o modelo usados), a resposta enviada ao morador e os avisos para cada setor.

**8. O n8n distribui.** A API devolve o resultado, e o **Switch** do n8n escolhe o caminho:
- **Emergência:** avisa portaria, zelador de plantão e síndico.
- **Chamado:** avisa o setor responsável (zeladoria, portaria, administração ou síndico).
- **Resposta automática:** só responde ao morador.

No fim, o morador recebe a resposta.

## A central de atendimento

A equipe trabalha pela central:
- **Caixas por setor**, com quantos chamados estão pendentes e quantos estão fora do prazo.
- **Fila** ordenada por urgência: primeiro os fora do prazo, depois por prioridade, depois os mais antigos.
- **Conversa de cada chamado:** os balões mostram a conversa com o morador, e o "livro de ocorrências" mostra o que o sistema e a equipe fizeram, com horário. Também aparece de onde veio cada informação: o canal, quem analisou (IA, perguntas frequentes ou cache) e o que a IA consultou na base.
- **Formas de resolução:** assumir, responder ao morador (com respostas prontas), anotar só para a equipe, encaminhar para outro setor, mudar a prioridade, resolver (é obrigatório descrever o que foi feito) e reabrir. Se o morador responder um chamado resolvido, ele reabre sozinho.

## A automação no n8n

| Fluxo | Quando roda | O que faz |
|---|---|---|
| **1. Atendimento** | A cada mensagem (webhook) | Recebe, chama a API, distribui pelo Switch e responde ao morador |
| **2. Escalonamento** | A cada 10 minutos | Procura chamados críticos abertos há mais de 30 minutos e alerta o síndico |
| **3. Resumo diário** | Todo dia às 18h | Pede à IA um resumo dos chamados do dia e monta o relatório do síndico |

## Decisões importantes

- **Economia de IA:** perguntas frequentes e respostas repetidas não chamam a IA, e o painel mostra quantas chamadas foram economizadas.
- **Segurança da cota:** um limite diário de análises com IA impede que alguém gaste toda a cota da chave enviando mensagens em massa.
- **Acessibilidade:** a central segue o padrão WCAG 2.2 AA, verificado automaticamente (contraste, teclado, leitor de tela).
- **Testes:** 56 testes automáticos da API e um teste no navegador com 13 passos, que inclui a auditoria de acessibilidade.

## Versão online e versão local

- **Online:** a API e a central estão no Render, e uma cópia da central está na Vercel. O n8n precisa de cerca de 550 MB de memória e o plano gratuito oferece 512 MB, então, na versão online, a central envia as mensagens **direto para a API**, com a mesma IA, o mesmo RAG e os mesmos chamados.
- **Local (Docker):** `docker compose up` sobe a API e o n8n juntos, com o fluxo completo. Os prints do n8n no README foram feitos nessa versão.

## Tecnologias

Python 3.12 com FastAPI, Google Gemini (com modelos reserva), Pydantic, SQLite, n8n, HTML/CSS/JavaScript puros na central, Docker Compose, pytest e Playwright.
