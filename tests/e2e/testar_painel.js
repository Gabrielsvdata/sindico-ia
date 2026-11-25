// Teste de ponta a ponta do painel: simula moradores pelo n8n e resolve chamados como a equipe.
// Uso: com a API e o n8n rodando, `node tests/e2e/testar_painel.js [pasta-dos-prints]`
// Requer: npm install playwright && npx playwright install chromium
const { chromium } = require("playwright");
const assert = require("assert");

const BASE = process.env.PAINEL_URL || "http://localhost:8000";
const PASTA = process.argv[2] || ".";
const passos = [];
const passo = async (nome, fn) => { await fn(); passos.push(nome); console.log("ok -", nome); };

(async () => {
  const navegador = await chromium.launch();
  const p = await navegador.newPage({ viewport: { width: 1440, height: 900 } });
  const erros = [];
  p.on("pageerror", (e) => erros.push(e.message));
  p.on("console", (m) => m.type() === "error" && erros.push(m.text()));
  await p.goto(BASE, { waitUntil: "networkidle" });

  const simular = async (exemplo, { modo = "n8n", canal = "whatsapp", apto = "302B", nome = "Ana Souza" } = {}) => {
    if (!(await p.$eval("#simulador", (d) => d.open))) await p.click("#abrir-simulador");
    await p.selectOption("#chamado-existente", "");
    await p.fill("#morador", nome);
    await p.fill("#apartamento", apto);
    await p.selectOption("#canal", canal);
    await p.check(`input[name="modo"][value="${modo}"]`);
    await p.click(`#simulador .chip:has-text("${exemplo}")`);
    await p.click("#btn-enviar");
    await p.waitForSelector("#sim-resultado #ver-chamado, #sim-resultado .erro", { timeout: 60000 });
    const erro = await p.$("#sim-resultado .erro");
    assert(!erro, erro && (await erro.textContent()));
  };

  await passo("moradores enviam mensagens pelo n8n (vários canais)", async () => {
    await simular("Vazamento na garagem", { apto: "104A", nome: "Carlos Lima" });
    await simular("Barulho", { apto: "302A", nome: "Marta Dias", canal: "telegram" });
    await simular("Cobrança errada", { apto: "508B", nome: "Rafael Nunes", canal: "email" });
    await simular("Horário da piscina", { apto: "205A", nome: "Pedro Alves" });
    await simular("Cheiro de gás");
    await p.screenshot({ path: `${PASTA}/01-simulador.png` });
    await p.click('#simulador [data-fechar]');
  });

  await passo("fila mostra pendentes com emergência no topo e caixas contam por setor", async () => {
    await p.waitForTimeout(300);
    const primeiro = await p.textContent("#lista li:first-child .item-resumo");
    assert(/gás/i.test(primeiro), "emergência deveria estar no topo: " + primeiro);
    const pendentes = await p.$$eval("#lista li", (l) => l.length);
    assert.strictEqual(pendentes, 4, "4 pendentes (a dúvida da piscina foi respondida sozinha)");
    const portaria = await p.textContent('[data-caixa="portaria"] .contador');
    assert.strictEqual(portaria.replace(/\D/g, ""), "1");
  });

  await passo("abrir chamado mostra a conversa e de onde vieram as informações", async () => {
    await p.click('#lista .item:has-text("vazando")');
    await p.waitForSelector("#conversa .ev-morador");
    const conversa = await p.textContent("#conversa");
    assert(/Carlos Lima \(apto 104A\), por WhatsApp/.test(conversa), "autor e canal da mensagem");
    assert(/Classificado como/.test(conversa), "análise registrada");
    assert(/Zeladoria foi avisado pelo n8n/.test(conversa), "alerta do setor");
    const origem = await p.textContent(".origem-linha");
    assert(/Chegou por WhatsApp pelo n8n e foi analisado pela IA/.test(origem), origem);
    await p.screenshot({ path: `${PASTA}/02-conversa.png` });
  });

  await passo("assumir, nota interna e resposta pronta ao morador", async () => {
    await p.selectOption("#atuando", "Zelador João");
    await p.click('[data-acao="assumir"]');
    await p.waitForSelector('.det-tags .st-em_andamento');
    await p.click('.comp-aba[data-tipo="nota_interna"]');
    await p.fill("#comp-texto", "Cano do 2º andar rompido, encanador chamado.");
    await p.click("#comp-enviar");
    await p.waitForSelector('.ev-nota:has-text("encanador chamado")');
    await p.click('.comp-aba[data-tipo="resposta_morador"]');
    await p.click('#prontas .chip:has-text("O zelador já está a caminho.")');
    await p.click("#comp-enviar");
    await p.waitForSelector('.ev-resposta:not(.automatica):has-text("O zelador já está a caminho.")');
  });

  await passo("resolver exige descrição e avisa o morador", async () => {
    await p.click('[data-acao="resolver"]');
    await p.click('#dlg-resolver button[type="submit"]');
    assert(await p.$eval("#dlg-resolver", (d) => d.open), "sem descrição não fecha");
    await p.click('#notas-prontas .chip:has-text("Peça trocada")');
    await p.click('#dlg-resolver button[type="submit"]');
    await p.waitForSelector('.det-tags .st-resolvido');
    const conversa = await p.textContent("#conversa");
    assert(/Resolvido por Zelador João\. Peça trocada/.test(conversa));
    assert(/Seu chamado foi resolvido: Peça trocada/.test(conversa));
    await p.screenshot({ path: `${PASTA}/03-resolvido.png` });
  });

  await passo("morador responde pelo simulador e o chamado reabre sozinho", async () => {
    const id = await p.$eval("#det-titulo", () => document.querySelector('.item[aria-current="true"]')?.dataset.id
      || document.querySelector(".det-quem p").textContent.match(/Chamado (\d+)/)[1]);
    await p.click("#abrir-simulador");
    await p.waitForSelector(`#chamado-existente option[value="${id}"]`, { state: "attached" });
    await p.selectOption("#chamado-existente", String(id));
    await p.fill("#texto", "Voltou a pingar perto da vaga 12.");
    await p.click("#btn-enviar");
    await p.waitForSelector("#sim-resultado #ver-chamado");
    await p.click("#sim-resultado #ver-chamado");
    await p.waitForSelector('.det-tags .tag:has-text("Aberto")');
    assert(/Reaberto: o morador enviou uma nova mensagem/.test(await p.textContent("#conversa")));
  });

  await passo("encaminhar para o síndico e mudar prioridade", async () => {
    await p.selectOption("#atuando", "Síndico");
    await p.click('#lista .item:has-text("boleto")');
    await p.waitForSelector('#conversa');
    await p.click('[data-acao="encaminhar"]');
    await p.click('#opcoes-mudar [data-valor="sindico"]');
    await p.fill("#motivo-mudar", "Cobrança duplicada precisa de aprovação");
    await p.click("#btn-mudar");
    await p.waitForSelector('.det-tags .tag:has-text("Síndico")');
    await p.click('[data-acao="prioridade"]');
    await p.click('#opcoes-mudar [data-valor="alta"]');
    await p.click("#btn-mudar");
    await p.waitForSelector('.det-tags .pr-alta');
    const conversa = await p.textContent("#conversa");
    assert(/Encaminhado de Administração para Síndico\. Motivo: Cobrança duplicada/.test(conversa));
    assert(/Síndico foi avisado pelo n8n/.test(conversa));
    assert(/Prioridade alterada de Média para Alta/.test(conversa));
  });

  await passo("caixa do síndico e aba de resolvidos", async () => {
    await p.click('[data-caixa="sindico"]');
    await p.waitForSelector('#lista .item:has-text("boleto")');
    await p.click('.aba[data-filtro="resolvidos"]');
    await p.click('[data-caixa="todas"]');
    await p.waitForSelector('#lista .item:has-text("piscina")');
    await p.click('#lista .item:has-text("piscina")');
    await p.waitForSelector('.origem-linha:has-text("pelas perguntas frequentes")');
    assert(/Regimento: “Piscina/.test(await p.textContent("#conversa")));
    await p.click('.aba[data-filtro="pendentes"]');
  });

  await passo("emergência mostra os três avisos e o prazo de 30 min", async () => {
    await p.click('#lista .item:has-text("gás")');
    await p.waitForSelector('#conversa .ev-alerta');
    const avisos = await p.$$eval(".ev-alerta summary strong", (s) => s.map((x) => x.textContent));
    assert.deepStrictEqual(avisos, ["Portaria", "Zelador de plantão", "Síndico"]);
    assert(/Prazo termina em(2\d|30) min/.test(await p.textContent(".prazo")));
    await p.screenshot({ path: `${PASTA}/04-emergencia.png` });
  });

  await passo("RAG: dúvida fora do FAQ exato é respondida pela IA citando a base", async () => {
    await simular("Mudança no domingo", {});   // garante simulador aberto
    await p.fill("#texto", "meu amigo vai vir hoje, como faço pra ele entrar?");
    await p.click("#btn-enviar");
    await p.waitForSelector("#sim-resultado #ver-chamado", { timeout: 60000 });
    await p.click("#sim-resultado #ver-chamado");
    await p.waitForSelector('.origem-linha:has-text("Resposta baseada em")');
    await p.click(".origem-linha summary");
    const base = await p.textContent(".base-lista");
    assert(/usada na resposta/.test(base), base);
    await p.screenshot({ path: `${PASTA}/07-rag.png` });
  });

  await passo("resumo do dia", async () => {
    await p.click("#abrir-resumo");
    await p.waitForSelector("#resumo-conteudo .det-tags", { timeout: 60000 });
    await p.click('#dlg-resumo [data-fechar]');
  });

  await passo("celular: fila e conversa em telas separadas, sem rolagem lateral", async () => {
    const m = await navegador.newPage({ viewport: { width: 390, height: 844 }, colorScheme: "dark" });
    m.on("pageerror", (e) => erros.push("celular: " + e.message));
    await m.goto(BASE, { waitUntil: "networkidle" });
    await m.screenshot({ path: `${PASTA}/05-celular-fila.png`, fullPage: true });
    await m.click('#lista .item:has-text("gás")');
    await m.waitForSelector("#conversa .ev-morador");
    assert(!(await m.isVisible("#lista")), "fila some ao abrir a conversa");
    await m.screenshot({ path: `${PASTA}/06-celular-conversa.png`, fullPage: true });
    const lateral = await m.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    assert(!lateral, "não pode ter rolagem lateral");
    await m.click("#voltar");
    assert(await m.isVisible("#lista"));
  });

  await passo("acessibilidade WCAG 2.2 AA (axe-core) sem violações", async () => {
    let axe;
    try { axe = require("fs").readFileSync(require.resolve("axe-core/axe.min.js"), "utf8"); }
    catch { console.log("   (axe-core não instalado: npm install axe-core para rodar este passo)"); return; }
    for (const esquema of ["light", "dark"]) {
      const a = await navegador.newPage({ viewport: { width: 1440, height: 900 }, colorScheme: esquema });
      await a.goto(BASE, { waitUntil: "networkidle" });
      await a.click("#lista .item");
      await a.waitForSelector("#conversa .ev-morador");
      await a.click(".origem-linha summary");
      for (const etapa of ["central", "simulador"]) {
        if (etapa === "simulador") await a.click("#abrir-simulador");
        await a.addScriptTag({ content: axe });
        const r = await a.evaluate(() => axe.run(document, { runOnly: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"] }));
        const v = r.violations.map((x) => `${esquema}/${etapa}: ${x.id} (${x.nodes.map((n) => n.target.join(" ")).slice(0, 3).join(", ")})`);
        assert.deepStrictEqual(v, [], v.join("\n"));
      }
      await a.close();
    }
  });

  assert.deepStrictEqual(erros, [], "erros no console: " + erros.join(" | "));
  console.log(`\n${passos.length} passos ok, nenhum erro no console`);
  await navegador.close();
})().catch((e) => { console.error("FALHOU:", e.message); process.exit(1); });
