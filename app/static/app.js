// Central de atendimento do Síndico IA.
// Caixas por setor -> fila de chamados -> conversa com o morador e ações para resolver.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const SETORES = {
  portaria: { nome: "Portaria", sub: "Encomendas, visitas, segurança" },
  zeladoria: { nome: "Zeladoria", sub: "Manutenção e limpeza" },
  administracao: { nome: "Administração", sub: "Boletos, reservas, mudanças" },
  sindico: { nome: "Síndico", sub: "Conflitos e decisões" },
};
const PRIORIDADES = { critica: "Crítica", alta: "Alta", media: "Média", baixa: "Baixa" };
const ORDEM_PRIORIDADE = { critica: 0, alta: 1, media: 2, baixa: 3 };
const STATUS = { aberto: "Aberto", em_andamento: "Em andamento", resolvido: "Resolvido" };
const CATEGORIAS = {
  manutencao: "Manutenção", barulho: "Barulho", duvida: "Dúvida", encomenda: "Encomenda",
  financeiro: "Financeiro", seguranca: "Segurança", reclamacao: "Reclamação", outros: "Outros",
};
const CANAIS = { whatsapp: "WhatsApp", telegram: "Telegram", email: "E-mail", portaria: "Interfone", painel: "Painel", webhook: "Webhook" };

// Respostas prontas para o morador, por assunto
const RESPOSTAS_PRONTAS = {
  manutencao: ["O zelador já está a caminho.", "Chamamos uma empresa especializada e retornamos com o prazo ainda hoje.", "Pode nos mandar uma foto do local?"],
  seguranca: ["A portaria e o zelador já estão no local.", "Situação controlada. Obrigado por avisar tão rápido."],
  barulho: ["Entramos em contato com a unidade e pedimos silêncio.", "Registramos a ocorrência. Se repetir, a unidade recebe advertência conforme o regimento."],
  financeiro: ["Conferimos e o valor será corrigido no próximo boleto.", "Enviamos a segunda via corrigida para o seu e-mail."],
  encomenda: ["Sua encomenda está na portaria, pode retirar.", "Ainda não chegou nada no seu nome. Avisamos assim que chegar."],
  padrao: ["Recebemos e já estamos verificando.", "Pode nos dar mais detalhes?"],
};
const NOTAS_RESOLUCAO = {
  manutencao: ["Conserto feito pelo zelador.", "Empresa terceirizada fez o serviço.", "Peça trocada e local limpo."],
  seguranca: ["Situação verificada e controlada pela portaria.", "Bombeiros acionados e área liberada."],
  barulho: ["Unidade advertida, barulho cessou.", "Advertência formal enviada à unidade."],
  financeiro: ["Valor corrigido e boleto reemitido.", "Cobrança estava correta, morador orientado."],
  padrao: ["Morador orientado conforme o regimento.", "Problema resolvido."],
};

const guardar = {
  ler(k, p) { try { return localStorage.getItem(k) ?? p; } catch { return p; } },
  gravar(k, v) { try { localStorage.setItem(k, v); } catch { /* sem armazenamento */ } },
};

const estado = {
  caixa: "todas",
  filtro: "pendentes",
  selecionado: null,
  chamados: [],
  idsVistos: null,
  urlN8n: guardar.ler("urlN8n", null),
  tipoComposicao: "resposta_morador",
};

// ------------------------------------------------------------------ utilidades
function esc(t) { const d = document.createElement("div"); d.textContent = t ?? ""; return d.innerHTML; }
const autor = () => $("#atuando").value;

async function api(caminho, opcoes = {}) {
  const r = await fetch(caminho, { headers: { "Content-Type": "application/json" }, ...opcoes });
  const corpo = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = corpo.detail;
    throw new Error(typeof d === "string" ? d : d ? d.map((x) => x.msg).join("; ") : `Erro ${r.status}`);
  }
  return corpo;
}
const post = (c, dados, metodo = "POST") => api(c, { method: metodo, body: JSON.stringify(dados) });

function relativo(iso) {
  const min = Math.round((Date.now() - new Date(iso)) / 60000);
  if (min < 1) return "agora";
  if (min < 60) return `há ${min} min`;
  const h = Math.floor(min / 60);
  if (h < 24) return `há ${h} h`;
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}
function hora(iso) { return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }); }
function duracao(min) {
  min = Math.abs(Math.round(min));
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60), m = min % 60;
  return h < 24 ? `${h} h${m ? ` ${m} min` : ""}` : `${Math.floor(h / 24)} d ${h % 24} h`;
}
function placa(apto, grande = false) {
  return apto
    ? `<span class="placa${grande ? " placa-grande" : ""}" title="Apartamento">${esc(apto)}</span>`
    : `<span class="placa placa-sem${grande ? " placa-grande" : ""}" title="Apartamento não informado">s/ apto</span>`;
}
function tempo(iso, classe = "") {
  const completo = new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
  return `<time class="${classe}" datetime="${esc(iso)}" title="${completo}">${relativo(iso)}</time>`;
}
function anunciar(texto) { $("#anuncio").textContent = ""; setTimeout(() => { $("#anuncio").textContent = texto; }, 50); }
function avisar(texto) {
  const el = $("#aviso");
  el.textContent = texto;
  el.hidden = false;
  anunciar(texto);
  clearTimeout(avisar.t);
  avisar.t = setTimeout(() => { el.hidden = true; }, 3200);
}

// ------------------------------------------------------------------ caixas e indicadores
async function carregarCaixas() {
  const [caixas, m] = await Promise.all([api("/caixas"), api("/metricas")]);
  const pendTotal = Object.values(caixas).reduce((s, c) => s + c.pendentes, 0);
  const atrasTotal = Object.values(caixas).reduce((s, c) => s + c.atrasados, 0);
  const linhas = [["todas", { nome: "Todos os setores", sub: "Visão do síndico" }, pendTotal, atrasTotal]]
    .concat(Object.entries(SETORES).map(([k, s]) => [k, s, caixas[k].pendentes, caixas[k].atrasados]));

  $("#lista-caixas").innerHTML = linhas.map(([k, s, pend, atras]) => `
    <li><button class="caixa${estado.caixa === k ? " ativa" : ""}" data-caixa="${k}" aria-pressed="${estado.caixa === k}">
      <span><span class="nome">${s.nome}</span>${atras ? `<span class="sub">${atras} fora do prazo</span>` : ""}</span>
      <span class="contador${atras ? " alerta" : ""}"><span class="sr-only">, </span>${pend}<span class="sr-only"> pendentes</span></span>
    </button></li>`).join("");

  $("#i-sem-ia").textContent = `${m.percentual_sem_ia ?? 0}%`;
  $("#i-tempo").textContent = m.tempo_medio_resolucao_min == null ? "–" : duracao(m.tempo_medio_resolucao_min);
  $("#i-total").textContent = m.total;
}

$("#lista-caixas").addEventListener("click", (e) => {
  const b = e.target.closest("[data-caixa]");
  if (!b) return;
  estado.caixa = b.dataset.caixa;
  $("#t-fila").textContent = estado.caixa === "todas" ? "Todos os setores" : SETORES[estado.caixa].nome;
  atualizar();
});

// ------------------------------------------------------------------ fila
$$(".aba").forEach((b) => b.addEventListener("click", () => {
  estado.filtro = b.dataset.filtro;
  $$(".aba").forEach((x) => { x.classList.toggle("ativa", x === b); x.setAttribute("aria-pressed", x === b); });
  carregarFila();
}));

async function carregarFila() {
  const p = new URLSearchParams({ limite: "200" });
  if (estado.caixa !== "todas") p.set("setor", estado.caixa);
  if (estado.filtro === "resolvidos") p.set("status", "resolvido");
  let lista = await api(`/chamados?${p}`);
  if (estado.filtro === "pendentes") lista = lista.filter((c) => c.status !== "resolvido");

  // Fila de atendimento: atrasados, depois prioridade, depois o mais antigo primeiro
  if (estado.filtro !== "resolvidos") {
    lista.sort((a, b) => (b.atrasado - a.atrasado) || (ORDEM_PRIORIDADE[a.prioridade] - ORDEM_PRIORIDADE[b.prioridade])
      || (new Date(a.criado_em) - new Date(b.criado_em)));
  }

  const novos = estado.idsVistos ? new Set(lista.filter((c) => !estado.idsVistos.has(c.id)).map((c) => c.id)) : new Set();
  estado.idsVistos = new Set([...(estado.idsVistos || []), ...lista.map((c) => c.id)]);
  estado.chamados = lista;

  const focado = document.activeElement?.closest?.("#lista [data-id]")?.dataset.id;
  $("#lista").innerHTML = lista.map((c) => `
    <li><button class="item pr-${c.prioridade}${novos.has(c.id) ? " novo" : ""}" data-id="${c.id}"
        aria-current="${estado.selecionado === c.id}">
      ${placa(c.apartamento)}
      <span class="item-linha1"><span class="item-nome">${esc(c.morador)}</span>${tempo(c.criado_em, "item-tempo")}</span>
      <span class="item-resumo">${esc(c.analise.resumo)}</span>
      <span class="item-tags">
        <span class="tag pr-${c.prioridade}"><span class="sr-only">Prioridade </span>${PRIORIDADES[c.prioridade]}</span>
        ${c.atrasado ? '<span class="tag atrasado">Fora do prazo</span>' : ""}
        ${c.status === "em_andamento" ? `<span class="tag st-em_andamento">${STATUS[c.status]}</span>` : ""}
      </span>
    </button></li>`).join("");

  if (focado) $(`#lista [data-id="${focado}"]`)?.focus();
  if (novos.size) anunciar(novos.size === 1 ? "Chegou 1 chamado novo." : `Chegaram ${novos.size} chamados novos.`);

  const vazio = $("#fila-vazia");
  vazio.hidden = lista.length > 0;
  if (!lista.length) {
    vazio.innerHTML = estado.filtro === "pendentes"
      ? `<p>Nada pendente${estado.caixa !== "todas" ? ` para ${SETORES[estado.caixa].nome}` : ""}.</p>
         <button class="btn btn-latao" type="button" data-simular>Simular mensagem de morador</button>`
      : "<p>Nenhum chamado aqui.</p>";
  }
}

$("#lista").addEventListener("click", (e) => {
  const b = e.target.closest("[data-id]");
  if (b) abrirChamado(Number(b.dataset.id));
});
$("#fila-vazia").addEventListener("click", (e) => { if (e.target.closest("[data-simular]")) abrirSimulador(); });

// ------------------------------------------------------------------ detalhe do chamado
async function abrirChamado(id, { rolar = true, forcar = true } = {}) {
  const trocou = estado.selecionado !== id;
  estado.selecionado = id;
  $$(".item").forEach((el) => el.setAttribute("aria-current", Number(el.dataset.id) === id));
  $("#central").classList.add("vendo-detalhe");
  const [c, eventos] = await Promise.all([api(`/chamados/${id}`), api(`/chamados/${id}/eventos`)]);
  // Só redesenha se algo mudou, para não tirar o foco de quem navega pelo teclado
  const versao = `${c.atualizado_em}|${c.status}|${eventos.length}`;
  if (!forcar && !trocou && versao === estado.versaoDetalhe) return;
  estado.versaoDetalhe = versao;
  renderizarDetalhe(c, eventos, rolar);
  if (trocou && forcar) $("#det-titulo")?.focus();
}

function renderizarDetalhe(c, eventos, rolar) {
  $("#detalhe-vazio").hidden = true;
  const el = $("#detalhe-conteudo");
  const textoDigitado = $("#comp-texto")?.value || "";
  el.hidden = false;

  const analise = eventos.find((e) => e.tipo === "analise")?.dados || {};
  const minRestantes = (new Date(c.prazo_em) - Date.now()) / 60000;
  const prazoHtml = c.status === "resolvido"
    ? `<div class="prazo">Resolvido<strong>${c.resolvido_em ? relativo(c.resolvido_em) : ""}</strong></div>`
    : `<div class="prazo${c.atrasado ? " estourado" : ""}">${c.atrasado ? "Fora do prazo há" : "Prazo termina em"}<strong>${duracao(minRestantes)}</strong></div>`;

  const quem = c.origem === "ia"
    ? `pela IA (${esc(analise.modelo || "modelo")}, confiança de ${Math.round((c.analise.confianca || 0) * 100)}%)`
    : c.origem === "faq" ? "pelas perguntas frequentes, sem usar IA" : "com uma resposta já dada antes, sem usar IA";
  const usadas = new Set((analise.fontes || []).map((f) => f.id));
  const base = analise.base_consultada || [];
  const baseHtml = base.length
    ? `<ul class="base-lista">${base.map((b) => `<li class="${usadas.has(b.id) ? "usada" : ""}">
        <span class="pontos">${b.score == null ? "exata" : `${b.score} pts`}</span>
        <span>${esc(b.pergunta)}${usadas.has(b.id) ? " (usada na resposta)" : ""}</span></li>`).join("")}</ul>`
    : "<p>Nenhuma pergunta frequente tinha relação com a mensagem.</p>";
  const descartadas = (analise.fontes_descartadas || []).length
    ? `<p>A IA citou ${analise.fontes_descartadas.length} fonte(s) que não recebeu. Elas foram ignoradas.</p>` : "";

  el.innerHTML = `
    <div class="det-cabeca">
      <button class="btn btn-contorno voltar" type="button" id="voltar" aria-label="Voltar para a fila">Voltar</button>
      ${placa(c.apartamento, true)}
      <div class="det-quem">
        <h2 id="det-titulo" tabindex="-1">${esc(c.morador)}</h2>
        <p>Chamado ${c.id}, aberto ${tempo(c.criado_em)}${c.responsavel ? `, com ${esc(c.responsavel)}` : ""}</p>
        <div class="det-tags">
          <span class="tag pr-${c.prioridade}">${PRIORIDADES[c.prioridade]}</span>
          <span class="tag">${CATEGORIAS[c.analise.categoria] || c.analise.categoria}</span>
          <span class="tag">${SETORES[c.setor].nome}</span>
          <span class="tag st-${c.status}">${STATUS[c.status]}</span>
          ${c.regra_seguranca_aplicada ? '<span class="tag pr-critica" title="Palavras de emergência forçaram a prioridade crítica">Regra de segurança aplicada</span>' : ""}
        </div>
      </div>
      ${prazoHtml}
    </div>

    <div class="origem-linha">
      <p>Chegou por <strong>${esc(CANAIS[c.canal] || c.canal)}</strong>${c.canal === "painel" ? " direto na API" : " pelo n8n"} e foi analisado <strong>${quem}</strong>.
      ${usadas.size ? `Resposta baseada em <strong>${esc((analise.fontes || []).map((f) => f.pergunta).join("; "))}</strong>.` : "A resposta não usou a base de perguntas frequentes."}</p>
      <details><summary>Ver o que a IA consultou</summary>
        <p>A IA só pode responder com a base de perguntas frequentes. Estas foram as entradas mais parecidas com a mensagem:</p>
        ${baseHtml}${descartadas}
      </details>
    </div>

    <div class="conversa" id="conversa">${eventos.map((e) => eventoHtml(e, c)).join("")}</div>

    <div class="acoes">
      <div class="acoes-botoes">${botoesHtml(c)}</div>
      <div class="compositor${estado.tipoComposicao === "nota_interna" ? " nota" : ""}" id="compositor">
        <div class="comp-abas" role="group" aria-label="Tipo de mensagem">
          <button type="button" class="comp-aba${estado.tipoComposicao === "resposta_morador" ? " ativa" : ""}" data-tipo="resposta_morador" aria-pressed="${estado.tipoComposicao === "resposta_morador"}">Responder ao morador</button>
          <button type="button" class="comp-aba${estado.tipoComposicao === "nota_interna" ? " ativa" : ""}" data-tipo="nota_interna" aria-pressed="${estado.tipoComposicao === "nota_interna"}">Nota interna</button>
        </div>
        <label for="comp-texto" class="sr-only" id="comp-rotulo">Mensagem</label>
        <textarea id="comp-texto" rows="2" maxlength="2000"></textarea>
        <div class="comp-rodape">
          <div class="exemplos" id="prontas"></div>
          <button class="btn btn-verde" type="button" id="comp-enviar">Enviar</button>
        </div>
      </div>
    </div>`;

  $("#comp-texto").value = textoDigitado;
  atualizarCompositor(c);
  ligarAcoes(c);
  if (rolar) $("#detalhe").scrollTop = $("#detalhe").scrollHeight;
}

function eventoHtml(e, c) {
  const h = hora(e.criado_em);
  switch (e.tipo) {
    case "mensagem_morador":
      return `<div class="ev ev-morador"><span class="ev-autor">${esc(e.autor)}${e.dados.canal ? `, por ${esc(CANAIS[e.dados.canal] || e.dados.canal)}` : ""} às ${h}</span><div class="ev-balao">${esc(e.texto)}</div></div>`;
    case "resposta_morador": {
      const auto = e.autor.startsWith("Síndico IA");
      return `<div class="ev ev-resposta${auto ? " automatica" : ""}"><span class="ev-autor">${esc(e.autor)} para o morador às ${h}</span><div class="ev-balao">${esc(e.texto)}</div></div>`;
    }
    case "nota_interna":
      return `<div class="ev ev-nota"><span class="ev-autor">Nota interna de ${esc(e.autor)} às ${h}, o morador não vê</span><div class="ev-balao">${esc(e.texto)}</div></div>`;
    case "analise": {
      const d = e.dados;
      const extras = [
        d.fonte ? `Fonte: ${esc(d.fonte)}.` : "",
        d.sentimento ? `Tom da mensagem: ${esc(d.sentimento)}.` : "",
        d.guarda_corpo ? "<strong>Regra de segurança aplicada:</strong> palavras de emergência forçaram a prioridade crítica." : "",
      ].filter(Boolean).join(" ");
      return `<div class="ev ev-sistema ev-analise"><span class="icone" aria-hidden="true">✦</span>
        <div><strong>${esc(e.texto)}</strong><br>${extras}
        ${d.transcricao_anexo ? `<div class="trecho">Anexo: ${esc(d.transcricao_anexo)}</div>` : ""}
        ${(d.fontes || []).length ? `<div class="trecho">Base usada: ${esc(d.fontes.map((f) => f.pergunta).join("; "))}${d.trecho_regimento ? `<br>Regimento: “${esc(d.trecho_regimento)}”` : ""}</div>` : ""}</div>
        <span class="ev-hora">${h}</span></div>`;
    }
    case "alerta_setor":
      return `<div class="ev ev-sistema"><span class="icone" aria-hidden="true">🔔</span>
        <div class="ev-alerta"><details><summary><strong>${esc(e.destino)}</strong> foi avisado pelo n8n</summary><pre>${esc(e.texto)}</pre></details></div>
        <span class="ev-hora">${h}</span></div>`;
    case "status": {
      const icone = e.dados.para === "resolvido" ? "✓" : e.dados.para === "em_andamento" ? "▶" : "↺";
      return `<div class="ev ev-sistema"><span class="icone" aria-hidden="true">${icone}</span><div>${esc(e.texto)}</div><span class="ev-hora">${h}</span></div>`;
    }
    case "encaminhamento":
      return `<div class="ev ev-sistema"><span class="icone" aria-hidden="true">⇄</span><div><strong>${esc(e.autor)}</strong>: ${esc(e.texto)}</div><span class="ev-hora">${h}</span></div>`;
    case "prioridade":
      return `<div class="ev ev-sistema"><span class="icone" aria-hidden="true">!</span><div><strong>${esc(e.autor)}</strong>: ${esc(e.texto)}</div><span class="ev-hora">${h}</span></div>`;
    default:
      return `<div class="ev ev-sistema"><div>${esc(e.texto)}</div></div>`;
  }
}

function botoesHtml(c) {
  const b = [];
  if (c.status === "aberto") b.push('<button class="btn btn-verde" data-acao="assumir">Assumir</button>');
  if (c.status !== "resolvido") {
    b.push('<button class="btn btn-contorno" data-acao="encaminhar">Encaminhar</button>');
    b.push('<button class="btn btn-contorno" data-acao="prioridade">Mudar prioridade</button>');
    b.push('<button class="btn btn-latao direita" data-acao="resolver">Resolver</button>');
  } else {
    b.push('<button class="btn btn-contorno" data-acao="reabrir">Reabrir</button>');
  }
  return b.join("");
}

function atualizarCompositor(c) {
  const tipo = estado.tipoComposicao;
  $("#compositor").classList.toggle("nota", tipo === "nota_interna");
  $("#comp-texto").placeholder = tipo === "nota_interna" ? "Anotação para a equipe (o morador não vê)" : `Mensagem para ${c.morador}`;
  $("#comp-rotulo").textContent = tipo === "nota_interna" ? "Nota interna" : `Mensagem para ${c.morador}`;
  $("#comp-enviar").textContent = tipo === "nota_interna" ? "Salvar nota" : "Enviar ao morador";
  const prontas = tipo === "resposta_morador" ? (RESPOSTAS_PRONTAS[c.analise.categoria] || RESPOSTAS_PRONTAS.padrao) : [];
  $("#prontas").innerHTML = prontas.map((t) => `<button type="button" class="chip" data-pronta="${esc(t)}">${esc(t)}</button>`).join("");
}

function ligarAcoes(c) {
  $("#voltar").addEventListener("click", () => { $("#central").classList.remove("vendo-detalhe"); estado.selecionado = null; });
  $$(".comp-aba").forEach((b) => b.addEventListener("click", () => {
    estado.tipoComposicao = b.dataset.tipo;
    $$(".comp-aba").forEach((x) => { x.classList.toggle("ativa", x === b); x.setAttribute("aria-pressed", x === b); });
    atualizarCompositor(c);
    $("#comp-texto").focus();
  }));
  $("#prontas").addEventListener("click", (e) => {
    const p = e.target.closest("[data-pronta]");
    if (p) { $("#comp-texto").value = p.dataset.pronta; $("#comp-texto").focus(); }
  });
  $("#comp-enviar").addEventListener("click", () => executar(async () => {
    const texto = $("#comp-texto").value.trim();
    if (!texto) { $("#comp-texto").focus(); throw new Error("Escreva a mensagem antes de enviar."); }
    await post(`/chamados/${c.id}/interacoes`, { tipo: estado.tipoComposicao, autor: autor(), texto });
    $("#comp-texto").value = "";
    return estado.tipoComposicao === "nota_interna" ? "Nota salva." : "Resposta enviada ao morador.";
  }));

  $$("[data-acao]").forEach((b) => b.addEventListener("click", () => {
    const acao = b.dataset.acao;
    if (acao === "assumir") executar(async () => { await post(`/chamados/${c.id}`, { status: "em_andamento", responsavel: autor() }, "PATCH"); return `Chamado assumido por ${autor()}.`; });
    if (acao === "reabrir") executar(async () => { await post(`/chamados/${c.id}`, { status: "em_andamento", responsavel: autor() }, "PATCH"); return "Chamado reaberto."; });
    if (acao === "resolver") abrirResolver(c);
    if (acao === "encaminhar") abrirMudar(c, "setor");
    if (acao === "prioridade") abrirMudar(c, "prioridade");
  }));
}

async function executar(fn) {
  try {
    const msg = await fn();
    if (msg) avisar(msg);
    await atualizar({ rolar: true });
  } catch (err) {
    avisar(err.message);
  }
}

// Resolver: exige dizer o que foi feito
function abrirResolver(c) {
  const dlg = $("#dlg-resolver");
  $("#nota-resolucao").value = "";
  $("#avisar-morador").checked = true;
  const notas = NOTAS_RESOLUCAO[c.analise.categoria] || NOTAS_RESOLUCAO.padrao;
  $("#notas-prontas").innerHTML = notas.map((t) => `<button type="button" class="chip" data-nota="${esc(t)}">${esc(t)}</button>`).join("");
  $("#notas-prontas").onclick = (e) => { const n = e.target.closest("[data-nota]"); if (n) $("#nota-resolucao").value = n.dataset.nota; };
  $("#form-resolver").onsubmit = (e) => {
    e.preventDefault();
    const nota = $("#nota-resolucao").value.trim();
    if (!nota) return;
    dlg.close();
    executar(async () => {
      await post(`/chamados/${c.id}`, { status: "resolvido", responsavel: autor(), nota }, "PATCH");
      if ($("#avisar-morador").checked) {
        await post(`/chamados/${c.id}/interacoes`, { tipo: "resposta_morador", autor: autor(), texto: `Seu chamado foi resolvido: ${nota}` });
      }
      return "Chamado resolvido.";
    });
  };
  dlg.showModal();
  $("#nota-resolucao").focus();
}

// Encaminhar para outro setor ou mudar prioridade
function abrirMudar(c, campo) {
  const dlg = $("#dlg-mudar");
  const opcoes = campo === "setor" ? Object.fromEntries(Object.entries(SETORES).map(([k, v]) => [k, v.nome])) : PRIORIDADES;
  const atual = c[campo];
  let escolhido = null;
  $("#t-mudar").textContent = campo === "setor" ? "Encaminhar para outro setor" : "Mudar prioridade";
  $("#btn-mudar").textContent = campo === "setor" ? "Encaminhar" : "Mudar prioridade";
  $("#motivo-mudar").value = "";
  $("#opcoes-mudar").innerHTML = Object.entries(opcoes).map(([k, nome]) =>
    `<button type="button" class="opcao" role="radio" aria-checked="false" data-valor="${k}" ${k === atual ? "disabled title=\"Atual\"" : ""}>${nome}${k === atual ? " (atual)" : ""}</button>`).join("");
  $("#opcoes-mudar").onclick = (e) => {
    const o = e.target.closest("[data-valor]:not(:disabled)");
    if (!o) return;
    escolhido = o.dataset.valor;
    $$(".opcao").forEach((x) => x.setAttribute("aria-checked", x === o));
  };
  $("#form-mudar").onsubmit = (e) => {
    e.preventDefault();
    if (!escolhido) { avisar("Escolha uma opção."); return; }
    dlg.close();
    const motivo = $("#motivo-mudar").value.trim() || null;
    executar(async () => {
      if (campo === "setor") {
        await post(`/chamados/${c.id}/encaminhar`, { setor: escolhido, autor: autor(), motivo });
        return `Encaminhado para ${opcoes[escolhido]}.`;
      }
      await post(`/chamados/${c.id}/prioridade`, { prioridade: escolhido, autor: autor(), motivo });
      return `Prioridade alterada para ${opcoes[escolhido]}.`;
    });
  };
  dlg.showModal();
}

// ------------------------------------------------------------------ simulador do morador
async function abrirSimulador() {
  $("#sim-resultado").hidden = true;
  // Inclui resolvidos: se o morador responder um chamado encerrado, ele reabre
  const recentes = await api("/chamados?limite=50").catch(() => []);
  $("#chamado-existente").innerHTML = '<option value="">Não, é uma mensagem nova</option>' + recentes
    .map((c) => `<option value="${c.id}">Chamado ${c.id}: ${esc(c.morador)}${c.apartamento ? ` (${esc(c.apartamento)})` : ""}, ${STATUS[c.status].toLowerCase()}</option>`).join("");
  $("#simulador").showModal();
  $("#texto").focus();
}
$("#abrir-simulador").addEventListener("click", abrirSimulador);
$$("#simulador .chip").forEach((c) => c.addEventListener("click", () => { $("#texto").value = c.dataset.txt; $("#texto").focus(); }));
$$('input[name="modo"]').forEach((r) => {
  r.checked = r.value === guardar.ler("modo", "n8n");
  r.addEventListener("change", () => guardar.gravar("modo", r.value));
});
$("#trocar-url").addEventListener("click", () => {
  $("#url-n8n").value = estado.urlN8n || "";
  const dlg = $("#dlg-n8n");
  dlg.showModal();
  dlg.addEventListener("close", () => {
    if (dlg.returnValue === "ok" && $("#url-n8n").value) { estado.urlN8n = $("#url-n8n").value.trim(); guardar.gravar("urlN8n", estado.urlN8n); }
  }, { once: true });
});

async function enviarPeloN8n(dados) {
  let r;
  try {
    r = await fetch(estado.urlN8n, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados) });
  } catch {
    throw new Error(`O n8n não respondeu em ${estado.urlN8n}. Abra o fluxo "1. Atendimento de mensagens" no n8n e clique em Publish. Para testar sem o n8n, escolha "Direto na API".`);
  }
  const corpo = await r.json().catch(() => ({}));
  if (r.status === 404) throw new Error('O webhook do n8n não está ativo. Abra o fluxo "1. Atendimento de mensagens" e clique em Publish.');
  if (!r.ok) throw new Error(corpo.message || `O n8n respondeu com erro ${r.status}. Veja a aba Executions do n8n.`);
  return corpo.chamado_id;
}

$("#form-msg").addEventListener("submit", async (e) => {
  e.preventDefault();
  const modo = $('input[name="modo"]:checked').value;
  const dados = {
    texto: $("#texto").value.trim(),
    morador: $("#morador").value.trim() || "Morador",
    apartamento: $("#apartamento").value.trim() || null,
    canal: modo === "api" ? "painel" : $("#canal").value,
  };
  if (!dados.texto) return;

  const btn = $("#btn-enviar");
  const res = $("#sim-resultado");
  btn.disabled = true;
  btn.textContent = "Enviando…";
  res.hidden = false;
  res.innerHTML = `<div class="ev ev-morador"><span class="ev-autor">Você</span><div class="ev-balao">${esc(dados.texto)}</div></div>
    <p class="dica">${modo === "n8n" ? "O n8n recebeu e chamou a API." : "A API recebeu."} Se precisar da IA, a resposta pode levar alguns segundos.</p>`;
  const inicio = performance.now();
  try {
    const existente = Number($("#chamado-existente").value);
    if (existente) {
      await post(`/chamados/${existente}/interacoes`, { tipo: "mensagem_morador", autor: dados.morador, texto: dados.texto });
      res.innerHTML = `<p class="dica">Mensagem adicionada à conversa do chamado ${existente}.
        <button class="link" type="button" id="ver-chamado">Ver na central</button></p>`;
      $("#ver-chamado").addEventListener("click", () => { $("#simulador").close(); abrirChamado(existente); });
      $("#texto").value = "";
      await atualizar({ rolar: false });
      return;
    }
    const id = modo === "n8n" ? await enviarPeloN8n(dados) : (await post("/mensagens", dados)).id;
    const c = await api(`/chamados/${id}`);
    const seg = ((performance.now() - inicio) / 1000).toFixed(1);
    res.innerHTML = `
      <div class="ev ev-morador"><span class="ev-autor">Você</span><div class="ev-balao">${esc(dados.texto)}</div></div>
      <div class="ev ev-resposta automatica"><span class="ev-autor">Síndico IA respondeu em ${seg} s</span><div class="ev-balao">${esc(c.analise.resposta_morador)}</div></div>
      <p class="dica">Virou o chamado ${c.id}: ${PRIORIDADES[c.prioridade].toLowerCase()}, para ${SETORES[c.setor].nome}${c.origem !== "ia" ? ", respondido sem IA" : ""}.
        <button class="link" type="button" id="ver-chamado">Ver na central</button></p>`;
    $("#ver-chamado").addEventListener("click", () => { $("#simulador").close(); abrirChamado(c.id); });
    $("#texto").value = "";
    await atualizar({ rolar: false });
  } catch (err) {
    res.innerHTML = `<div class="erro" role="alert"><strong>A mensagem não foi processada.</strong>${esc(err.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Enviar mensagem";
  }
});

// ------------------------------------------------------------------ resumo do dia
$("#abrir-resumo").addEventListener("click", async () => {
  const dlg = $("#dlg-resumo");
  $("#resumo-conteudo").innerHTML = '<p class="dica">Gerando o resumo…</p>';
  dlg.showModal();
  try {
    const r = await api("/resumo-diario");
    $("#resumo-conteudo").innerHTML = `
      <div class="det-tags"><span class="tag">${r.total_chamados} chamados hoje</span>
      <span class="tag ${r.pendencias_criticas ? "pr-critica" : "pr-baixa"}">${r.pendencias_criticas} críticos pendentes</span></div>
      <p style="margin-top:12px">${esc(r.resumo)}</p>
      ${r.destaques.length ? `<ul>${r.destaques.map((d) => `<li>${esc(d)}</li>`).join("")}</ul>` : ""}`;
  } catch (err) {
    $("#resumo-conteudo").innerHTML = `<div class="erro"><strong>Não foi possível gerar o resumo.</strong>${esc(err.message)}</div>`;
  }
});

// Fechar diálogos
document.addEventListener("click", (e) => { if (e.target.closest("[data-fechar]")) e.target.closest("dialog").close(); });

// ------------------------------------------------------------------ ciclo
$("#atuando").value = guardar.ler("atuando", "Síndico");
$("#atuando").addEventListener("change", () => guardar.gravar("atuando", autor()));

async function verificarApi() {
  const el = $("#status-api");
  try {
    const h = await api("/health");
    // Em produção, a API informa o endereço público do webhook do n8n
    if (!estado.urlN8n) estado.urlN8n = h.n8n_webhook_url || "http://localhost:5678/webhook/sindico";
    el.className = "conexao ok";
    el.textContent = h.provedor_ia === "mock" ? "Online, IA simulada" : `Online, ${h.modelo}`;
  } catch {
    el.className = "conexao erro";
    el.textContent = "API fora do ar";
  }
}

async function atualizar({ rolar = false } = {}) {
  try {
    await Promise.all([carregarCaixas(), carregarFila()]);
    // Não redesenha a conversa enquanto alguém digita ou usa uma janela
    const digitando = document.activeElement?.id === "comp-texto";
    const focoNoDetalhe = $("#detalhe").contains(document.activeElement);
    if (estado.selecionado && !$("dialog[open]") && (rolar || (!digitando && !focoNoDetalhe))) {
      await abrirChamado(estado.selecionado, { rolar, forcar: rolar });
    }
  } catch (err) {
    console.error(err);
  }
}

verificarApi();
atualizar();
// Mensagens que chegam pelo n8n (de qualquer canal) aparecem sozinhas
setInterval(() => { if (document.visibilityState === "visible") atualizar(); }, 8000);
