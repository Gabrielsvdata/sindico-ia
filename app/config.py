import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

AI_PROVIDER = os.getenv("AI_PROVIDER", "gemini").lower()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
DATABASE_PATH = os.getenv("DATABASE_PATH", str(BASE_DIR / "sindico.db"))
REGIMENTO_PATH = Path(os.getenv("REGIMENTO_PATH", str(BASE_DIR / "data" / "regimento.md")))

# Quantas vezes pedir de novo à IA quando ela devolve um JSON inválido
AI_MAX_TENTATIVAS = int(os.getenv("AI_MAX_TENTATIVAS", "3"))
