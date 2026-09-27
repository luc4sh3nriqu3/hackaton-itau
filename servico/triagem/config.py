"""Configuração lida de variáveis de ambiente e do arquivo servico/.env.

O .env é relido a cada chamada de `obter`, então colocar/alterar uma chave
(ex.: GEMINI_API_KEY) passa a valer na próxima requisição, sem reiniciar a API.
Valores no .env têm precedência sobre o ambiente do processo.
"""
import os
from pathlib import Path

from dotenv import dotenv_values

SERVICO_DIR = Path(__file__).resolve().parents[1]
ARQUIVO_ENV = SERVICO_DIR / ".env"
DADOS_DIR = SERVICO_DIR / "dados"
MODELOS_DIR = SERVICO_DIR / "modelos"
ARQUIVO_PERGUNTAS = DADOS_DIR / "perguntas.json"
ARQUIVO_MODELO = MODELOS_DIR / "classificador.joblib"
ARQUIVO_METRICAS = MODELOS_DIR / "metricas.json"

PADROES = {
    "GEMINI_MODEL": "gemini-3.8-flash",
    "GEMINI_MODELOS_RESERVA": "gemini-3.7-flash,gemini-flash-latest",
    "GEMINI_TIMEOUT_S": "20",
    "TRIAGEM_API_KEYS": "demo-mvp-key",
    "TRIAGEM_DB": str(SERVICO_DIR / "triagem.db"),
    "TRIAGEM_CORS_ORIGINS": "*",
}


def obter(nome: str, padrao: str | None = None) -> str | None:
    valores = dotenv_values(ARQUIVO_ENV) if ARQUIVO_ENV.exists() else {}
    valor = valores.get(nome) or os.environ.get(nome)
    if valor:
        return valor.strip()
    return padrao if padrao is not None else PADROES.get(nome)


def chaves_api() -> set[str]:
    return {c.strip() for c in (obter("TRIAGEM_API_KEYS") or "").split(",") if c.strip()}
