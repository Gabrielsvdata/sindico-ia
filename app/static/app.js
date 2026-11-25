// Painel do Síndico IA: simula o morador e mostra os chamados em tempo real.
const $ = (sel) => document.querySelector(sel);

const ROTULOS = {
  prioridade: { critica: "Crítica", alta: "Alta", media: "Média", baixa: "Baixa" },
  status: { aberto: "Aberto", em_andamento: "Em andamento", resolvido: "Resolvido" },
  acao: { emergencia: "🚨 Emergência", abrir_chamado: "📋 Chamado aberto", responder_automaticamente: "💬 Respondido automaticamente" },
  origem: { faq: "⚡ FAQ (sem IA)", cache: "⚡ Cache (sem IA)", ia: "🤖 IA" },
  setor: { zeladoria: "Zeladoria", portaria: "Portaria", administracao: "Administração", sindico: "Síndico" },
  categoria: {
    manutencao: "Manutenção", barulho: "Barulho", duvida: "Dúvida", encomenda: "Encomenda",
    financeiro: "Financeiro", seguranca: "Segurança", reclamacao: "Reclamação", outros: "Outros",
  },
};
const rot = (tipo, v) => (ROTULOS[tipo] && ROTULOS[tipo][v]) || v || "—";

const URL_N8N_PADRAO = "http://localhost:5678/webhook/sindico";
const guardar = {
  ler(chave, padrao) { try { return localStorage.getItem(chave) ?? padrao; } catch { return padrao; } },
  gravar(chave, valor) { try { localStorage.setItem(chave, valor); } catch { /* sem armazenamento: tudo bem */ } },
};

let modo = guardar.ler("modo", "n8n");
let urlN8n = guardar.ler("urlN8n", URL_N8N_PADRAO);
let ultimoIdVisto = 0;

function esc(texto) {
  const d = document.createElement("div");
  d.textContent = texto ?? "";
  return d.innerHTML;
}

async function api(caminho, opcoes = {}) {
  const r = await fetch(caminho, { headers: { "Content-Type": "application/json" }, ...opcoes });
  const corpo = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(corpo.detail ? (typeof corpo.detail === "string" ? corpo.detail : JSON.stringify(corpo.detail)) : `Erro ${r.status}`);
  return corpo;
}

// ------------------------------------------------------------ Modo de envio
function aplicarModo() {
  document.querySelectorAll(".seg").forEach((b) => {
    const ativo = b.dataset.modo === modo;
    b.classList.toggle("ativo", ativo);
    b.setAttribute("aria-checked", ativo);
  });
  $("#dica-modo").innerHTML = modo === "n8n"
    ? `A mensagem passa pelo webhook do n8n, que chama a API e decide o encaminhamento. <a href="#" id="trocar-url">Alterar endereço</a>`
    : "A mensagem vai direto para a API, sem passar pelo n8n.";
  const link = $("#trocar-url");
  if (link) link.addEventListener("click", (e) => { e.preventDefault(); abrirConfigN8n(); });
}

function abrirConfigN8n() {
  const dlg = $("#config-n8n");
  $("#url-n8n").value = urlN8n;
  dlg.showModal();
  dlg.addEventListener("close", () => {
    if (dlg.returnValue === "ok" && $("#url-n8n").value) {
      urlN8n = $("#url-n8n").value.trim();
      guardar.gravar("urlN8n", urlN8n);
    }
  }, { once: true });
}

document.querySelectorAll(".seg").forEach((b) => b.addEventListener("click", () => {
  modo = b.dataset.modo;
  guardar.gravar("modo", modo);
  aplicarModo();
}));

document.querySelectorAll(".chip").forEach((c) => c.addEventListener("click", () => {
  $("#texto").value = c.dataset.txt;
  $("#texto").focus();
}));

// ------------------------------------------------------------ Envio da mensagem
async function enviarPeloN8n(dados) {
  let r;
  try {
    r = await fetch(urlN8n, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(dados) });
  } catch {
    throw new Error(`Não foi possível falar com o n8n em ${urlN8n}. Confira se o fluxo 1 está publicado (ativo) e se o webhook permite chamadas do navegador (CORS). Enquanto isso, use "direto na API".`);
  }
  const corpo = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(corpo.message || `O n8n respondeu ${r.status}. Veja a aba Executions do n8n.`);
  // O n8n devolve um resumo; buscamos o chamado completo na API para exibir tudo
  const completo = corpo.chamado_id ? await api(`/chamados/${corpo.chamado_id}`) : {};
  return { ...completo, ...flatten(completo), n8n: corpo };
}

function flatten(c) {
  const a = c.analise || {};
  return { prioridade: a.prioridade, setor: a.setor, categoria: a.categoria, resposta_morador: a.resposta_morador };
}

$("#form-msg").addEventListener("submit", async (e) => {
  e.preventDefault();
  const dados = {
    texto: $("#texto").value.trim(),
    morador: $("#morador").value.trim() || "Morador",
    apartamento: $("#apartamento").value.trim() || null,
    canal: "painel",
  };
  if (!dados.texto) return;

  const btn = $("#btn-enviar");
  btn.disabled = true;
  btn.textContent = "Analisando…";
  const caixa = $("#resultado");
  caixa.hidden = false;
  caixa.innerHTML = `<p class="dica">Processando${modo === "n8n" ? " pelo n8n" : ""}… mensagens que vão para a IA podem levar alguns segundos.</p>`;
  const inicio = performance.now();

  try {
    const r = modo === "n8n" ? await enviarPeloN8n(dados) : await api("/mensagens", { method: "POST", body: JSON.stringify(dados) });
    mostrarResultado(r, performance.now() - inicio);
    $("#texto").value = "";
    await atualizarTudo();
  } catch (err) {
    caixa.innerHTML = `<div class="erro-box"><strong>Não deu certo.</strong><br>${esc(err.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Enviar mensagem";
  }
});

function mostrarResultado(r, ms) {
  const a = r.analise || {};
  const tempo = ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
  $("#resultado").innerHTML = `
    <h3><span>${esc(rot("acao", r.acao))} · #${esc(String(r.id ?? "?"))}</span><span class="tempo">${tempo}</span></h3>
    <div class="badges">
      <span class="badge p-${esc(a.prioridade)}">${esc(rot("prioridade", a.prioridade))}</span>
      <span class="badge">${esc(rot("categoria", a.categoria))}</span>
      <span class="badge">→ ${esc(rot("setor", a.setor))}</span>
      <span class="badge o-${esc(r.origem)}">${esc(rot("origem", r.origem))}</span>
      ${r.regra_seguranca_aplicada ? '<span class="badge p-critica">🛡️ Guarda-corpo aplicado</span>' : ""}
    </div>
    <div class="balao"><small>Resposta enviada ao morador</small>${esc(a.resposta_morador)}</div>
    ${a.trecho_regimento ? `<div class="trecho">📖 ${esc(a.trecho_regimento)}</div>` : ""}
    <details><summary>Ver JSON completo</summary><pre>${esc(JSON.stringify(r, null, 2))}</pre></details>`;
}

// ------------------------------------------------------------ Painel
async function carregarMetricas() {
  const m = await api("/metricas");
  $("#m-total").textContent = m.total;
  $("#m-abertos").textContent = m.por_status?.aberto ?? 0;
  $("#m-economia").textContent = `${m.percentual_sem_ia ?? 0}%`;
  $("#m-economia-det").textContent = `${m.chamadas_ia_economizadas ?? 0} chamadas de IA economizadas`;
  const criticos = await api("/chamados?status=aberto&prioridade=critica&limite=500");
  $("#m-criticos").textContent = criticos.length;
}

async function carregarChamados() {
  const params = new URLSearchParams({ limite: "50" });
  if ($("#f-status").value) params.set("status", $("#f-status").value);
  if ($("#f-prioridade").value) params.set("prioridade", $("#f-prioridade").value);
  const chamados = await api(`/chamados?${params}`);

  $("#vazio").hidden = chamados.length > 0;
  const maiorId = chamados.reduce((m, c) => Math.max(m, c.id), 0);
  $("#lista").innerHTML = chamados.map((c) => itemHtml(c, ultimoIdVisto && c.id > ultimoIdVisto)).join("");
  ultimoIdVisto = Math.max(ultimoIdVisto, maiorId);
}

function itemHtml(c, novo) {
  const a = c.analise;
  const quando = new Date(c.criado_em).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
  const acoes = [];
  if (c.status === "aberto") acoes.push(`<button data-id="${c.id}" data-status="em_andamento">Assumir</button>`);
  if (c.status !== "resolvido") acoes.push(`<button data-id="${c.id}" data-status="resolvido">Resolver</button>`);
  return `
    <li class="item${novo ? " novo" : ""}">
      <span class="faixa p-${esc(a.prioridade)}" aria-hidden="true"></span>
      <div class="item-corpo">
        <div class="item-titulo">#${c.id} · ${esc(a.resumo)}</div>
        <div class="badges">
          <span class="badge p-${esc(a.prioridade)}">${esc(rot("prioridade", a.prioridade))}</span>
          <span class="badge">${esc(rot("categoria", a.categoria))}</span>
          <span class="badge">→ ${esc(rot("setor", a.setor))}</span>
          <span class="badge o-${esc(c.origem)}">${esc(rot("origem", c.origem))}</span>
        </div>
        <div class="item-meta">${esc(c.morador)}${c.apartamento ? ` · apto ${esc(c.apartamento)}` : ""} · ${quando} · via ${esc(c.canal)}</div>
      </div>
      <div class="item-acoes">
        <span class="status s-${esc(c.status)}">${esc(rot("status", c.status))}</span>
        ${acoes.join("")}
      </div>
    </li>`;
}

$("#lista").addEventListener("click", async (e) => {
  const b = e.target.closest("button[data-id]");
  if (!b) return;
  b.disabled = true;
  try {
    await api(`/chamados/${b.dataset.id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: b.dataset.status, responsavel: "Painel do síndico" }),
    });
    await atualizarTudo();
  } catch (err) {
    alert(err.message);
    b.disabled = false;
  }
});

$("#f-status").addEventListener("change", carregarChamados);
$("#f-prioridade").addEventListener("change", carregarChamados);
$("#btn-atualizar").addEventListener("click", atualizarTudo);

$("#btn-resumo").addEventListener("click", async () => {
  const btn = $("#btn-resumo");
  btn.disabled = true;
  btn.textContent = "Gerando…";
  try {
    const r = await api("/resumo-diario");
    $("#resumo").innerHTML = `
      <div class="badges"><span class="badge">${r.total_chamados} chamados hoje</span>
      <span class="badge ${r.pendencias_criticas ? "p-critica" : "p-baixa"}">${r.pendencias_criticas} críticos pendentes</span></div>
      <p style="margin:0">${esc(r.resumo)}</p>
      ${r.destaques.length ? `<ul>${r.destaques.map((d) => `<li>${esc(d)}</li>`).join("")}</ul>` : ""}`;
  } catch (err) {
    $("#resumo").innerHTML = `<div class="erro-box">${esc(err.message)}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Gerar com IA";
  }
});

async function verificarApi() {
  const pill = $("#status-api");
  try {
    const h = await api("/health");
    pill.className = "pill pill-ok";
    pill.textContent = h.provedor_ia === "mock" ? "Online · modo mock" : `Online · ${h.modelo}`;
  } catch {
    pill.className = "pill pill-erro";
    pill.textContent = "API fora do ar";
  }
}

async function atualizarTudo() {
  try {
    await Promise.all([carregarMetricas(), carregarChamados()]);
  } catch (err) {
    console.error(err);
  }
}

aplicarModo();
verificarApi();
atualizarTudo();
// Atualiza sozinho: chamados que chegam pelo n8n (de outros canais) aparecem no painel
setInterval(atualizarTudo, 8000);
