// Onde a central encontra a API e se há um n8n disponível.
// Local (docker-compose): a API é o próprio endereço e o n8n roda em localhost:5678.
// Online (Render e Vercel): o n8n não roda em produção (precisa de mais memória que o plano
// gratuito oferece), então as mensagens vão direto para a API.
(function () {
  const host = location.hostname;
  const naVercel = host.endsWith(".vercel.app");
  window.SINDICO_API_URL = naVercel ? "https://sindico-ia-api-u99t.onrender.com" : "";
  window.SINDICO_SEM_N8N = naVercel || host.endsWith(".onrender.com");
})();
