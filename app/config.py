import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
# Modelos usados se o principal estiver sobrecarregado (separados por vírgula). Ex.: "outro-modelo,mais-um"
GEMINI_MODELOS_RESERVA = [m.strip() for m in os.getenv("GEMINI_MODELOS_RESERVA", "").split(",") if m.strip()]
DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "sindico.db"))
REGIMENTO_PATH = Path(os.getenv("REGIMENTO_PATH", str(BASE_DIR / "data" / "regimento.md")))
FAQ_PATH = Path(os.getenv("FAQ_PATH", str(BASE_DIR / "data" / "faq.json")))

# Respostas da IA reaproveitadas para perguntas repetidas (0 desliga o cache)
CACHE_DIAS = int(os.getenv("CACHE_DIAS", "7"))

# Quantas vezes pedir de novo à IA quando ela devolve um JSON inválido
AI_MAX_TENTATIVAS = int(os.getenv("AI_MAX_TENTATIVAS", "3"))
# Quantas vezes repetir a chamada quando o Google responde 429/500/503 (esperando 2s, 4s...)
AI_TENTATIVAS_SOBRECARGA = int(os.getenv("AI_TENTATIVAS_SOBRECARGA", "2"))
# Tempo máximo de espera por resposta do Gemini em cada tentativa
AI_TIMEOUT_SEGUNDOS = float(os.getenv("AI_TIMEOUT_SEGUNDOS", "30"))

# Máximo de chamadas à IA por dia (protege a cota da chave quando a API fica pública). 0 = sem limite.
AI_LIMITE_DIARIO = int(os.getenv("AI_LIMITE_DIARIO", "0"))

# Origens extras que podem chamar a API pelo navegador (ex.: a central publicada na Vercel).
# Expressão regular; vazio = só o mesmo endereço da API.
CORS_ORIGENS_REGEX = os.getenv("CORS_ORIGENS_REGEX", "")

# Endereço público do webhook do n8n, usado pela central (simulador) como padrão
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678/webhook/sindico")
