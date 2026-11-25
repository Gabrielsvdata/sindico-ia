// Onde a central encontra a API e o n8n.
// Servida pela própria API (localhost, Docker ou Render): mesmo endereço, nada a configurar.
// Publicada na Vercel: a central é só a tela, e a API e o n8n continuam no Render.
(function () {
  const naVercel = location.hostname.endsWith(".vercel.app");
  window.SINDICO_API_URL = naVercel ? "https://sindico-ia-api-u99t.onrender.com" : "";
  window.SINDICO_N8N_WEBHOOK_URL = naVercel ? "https://sindico-ia-n8n.onrender.com/webhook/sindico" : "";
})();
