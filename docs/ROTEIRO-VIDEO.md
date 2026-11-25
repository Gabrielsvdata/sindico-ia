# Roteiro do vídeo (cerca de 4 minutos)

## Antes de gravar

1. **Acorde o servidor:** abra a central uns 2 minutos antes e espere o status no topo ficar verde ("Online"). No plano gratuito, a API dorme depois de 15 minutos sem uso.
2. Deixe abertas três abas: a **central** (link da Vercel), o **README do GitHub** (na seção 7, com os prints do n8n) e, se quiser mostrar o n8n ao vivo, o **n8n local** (`docker compose up -d` e `http://localhost:5678`).
3. Feche notificações e abas com informações pessoais. **Não mostre o arquivo `.env`**, porque ele tem a sua chave.

**Como gravar no Windows:** `Win + Alt + R` inicia e para a gravação (Xbox Game Bar). O vídeo fica em *Vídeos → Capturas*. Para gravar a voz, ative o microfone em `Win + G`. Outra opção é o OBS Studio.

---

## Cena 1: o problema (0:00 a 0:25)
**Mostrar:** a central, ainda vazia ou com poucos chamados.

> "Este é o Síndico IA. Num condomínio, chegam mensagens misturadas: dúvidas repetidas, reclamações, pedidos de manutenção e, às vezes, emergências. Alguém precisa ler tudo e avisar a pessoa certa. O Síndico IA faz essa triagem automaticamente com inteligência artificial."

## Cena 2: dúvida frequente, sem IA (0:25 a 0:50)
**Fazer:** **Simular morador** → botão **"Horário da piscina"** → **Enviar mensagem**.

> "Quando um morador pergunta algo que já está nas perguntas frequentes, o sistema responde na hora, sem gastar chamada de IA, e cita a regra do regimento. Repare no tempo de resposta."

## Cena 3: dúvida respondida com RAG (0:50 a 1:30)
**Fazer:** no simulador, escreva *"Meu amigo vai vir hoje, como faço pra ele entrar?"* → **Enviar** → **Ver na central** → clique em **"Ver o que a IA consultou"**.

> "Essa pergunta não bate com nenhuma regra exata. Aí entra o RAG: o sistema busca as três perguntas frequentes mais parecidas e manda só elas para a IA. A IA responde usando apenas essa base e precisa dizer qual usou. Se citar algo que não recebeu, a resposta é descartada e o chamado vai para um humano. Aqui dá para ver o que ela consultou e o que usou."

## Cena 4: emergência (1:30 a 2:05)
**Fazer:** **Simular morador** → **"Cheiro de gás"** → **Enviar** → **Ver na central**.

> "Agora uma emergência. A IA classifica como crítica, e existe uma regra de segurança no código: palavras como 'cheiro de gás' forçam a prioridade crítica mesmo que a IA erre. O chamado vai para o topo da fila, com prazo de 30 minutos, e o morador recebe a orientação de ligar para a portaria e para os bombeiros."

## Cena 5: a equipe resolve (2:05 a 2:55)
**Fazer:** abra o chamado de **"Vazamento na garagem"** (envie antes, se não houver) → em **"Você é"** escolha **Zelador João** → **Assumir** → **Nota interna** (*"Cano rompido, encanador chamado"*) → **Responder ao morador** com uma resposta pronta → **Resolver** com uma descrição pronta.

> "Na central, cada setor tem a sua caixa. O zelador assume o chamado, registra uma nota que só a equipe vê, responde o morador e resolve, sendo obrigatório descrever o que foi feito. Tudo fica registrado nesse histórico, com horário e autor."

## Cena 6: o fluxo no n8n (2:55 a 3:35)
**Mostrar:** o n8n local com o fluxo **"1. Atendimento de mensagens"**, ou os prints do README (seção 7).

> "Por trás, o n8n orquestra o processo: o webhook recebe a mensagem, chama a API, e o Switch decide o caminho: emergência, chamado para o setor ou resposta automática. Também há dois fluxos agendados: um alerta o síndico quando um chamado crítico fica parado mais de 30 minutos, e outro gera um resumo do dia com IA. Na versão online, as mensagens vão direto para a API, porque o n8n precisa de mais memória do que o plano gratuito oferece. O fluxo completo roda na versão com Docker."

## Cena 7: fechamento (3:35 a 4:00)
**Mostrar:** a coluna **Situação** da central e, se quiser, o botão **Resumo do dia**.

> "Resumindo: o n8n cuida do fluxo, a API cuida da inteligência e dos dados, e a central é onde a equipe trabalha. A IA responde só com base nas perguntas frequentes, as respostas são validadas e as emergências têm uma regra de segurança extra. O código, os prints e a explicação completa estão no GitHub. Obrigado!"

---

**Dica:** se o Gemini demorar numa cena, a central mostra os segundos passando. Você pode esperar falando sobre o que está acontecendo, ou cortar a espera na edição.
