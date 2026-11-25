// Onde a central encontra a API.
// Servida pela própria API (localhost, Docker ou Render): mesmo endereço, nada a configurar.
// Publicada na Vercel: a central é só a tela, e a API continua no Render.
window.SINDICO_API_URL = location.hostname.endsWith(".vercel.app")
  ? "https://sindico-ia-api.onrender.com"
  : "";
