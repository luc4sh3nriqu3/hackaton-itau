"""Modo demo: perguntas fixas e texto final mockado (TRIAGEM_MODO_DEMO=1).

Usado nas apresentações. Em vez de sortear 3 perguntas do banco e calcular o score com o
classificador + Gemini, a sessão segue sempre as 3 perguntas de dados/perguntas_demo.json,
na ordem, e o resultado é montado a partir das respostas:
- cada alternativa tem um tópico pronto (tom + texto), então o texto final fica coerente
  com o que o cliente respondeu;
- qualquer resposta de risco → nível "alto" (mensagem de repensar); nenhuma → "baixo".

O resto do fluxo (decisão, pop-up de feedback, base) é o mesmo do modo real. As sessões
ficam marcadas com modo = "demo" e versao_modelo = "demo" para não se misturarem com dados reais.
"""
import json
from functools import lru_cache

from .config import DADOS_DIR

ARQUIVO_PERGUNTAS_DEMO = DADOS_DIR / "perguntas_demo.json"
VERSAO_MODELO_DEMO = "demo"
SCORE_POR_NIVEL = {"alto": 0.90, "baixo": 0.20}
NOME_PADRAO = "o destinatário"


@lru_cache(maxsize=1)
def _dados() -> dict:
    return json.loads(ARQUIVO_PERGUNTAS_DEMO.read_text(encoding="utf-8"))


def versao() -> str:
    return _dados()["versao"]


def total() -> int:
    return len(_dados()["perguntas"])


def _pergunta_bruta(pergunta_id: str) -> dict:
    for p in _dados()["perguntas"]:
        if p["id"] == pergunta_id:
            return p
    raise KeyError(pergunta_id)


def pergunta(n: int, nome_destinatario: str | None) -> dict:
    """N-ésima pergunta (1..total) no formato público da API, com o nome do recebedor preenchido."""
    p = _dados()["perguntas"][n - 1]
    return {
        "id": p["id"],
        "dimensao": p["dimensao"],
        "faceta": p["faceta"],
        "texto_didatico": p["texto_didatico"],
        "pergunta": p["pergunta"].replace("{nome_destinatario}", nome_destinatario or NOME_PADRAO),
        "alternativas": [{"id": a["id"], "texto": a["texto"]} for a in p["alternativas"]],
    }


def alternativa(pergunta_id: str, alternativa_id: str) -> dict:
    for a in _pergunta_bruta(pergunta_id)["alternativas"]:
        if a["id"] == alternativa_id:
            return a
    raise KeyError(alternativa_id)


def resultado(respostas: list[tuple[str, str]]) -> dict:
    """Monta o resultado mockado a partir de [(pergunta_id, alternativa_id), ...]."""
    alternativas = [alternativa(pid, aid) for pid, aid in respostas]
    nivel = "alto" if any(a["risco"] for a in alternativas) else "baixo"
    # Sinais de risco primeiro, depois os bons sinais, e o tópico de ação no fim.
    topicos = [a["topico"] for a in alternativas if a["risco"]]
    topicos += [a["topico"] for a in alternativas if not a["risco"]]
    topicos.append(_dados()["topico_final"][nivel])
    return {
        "nivel_risco": nivel,
        "score_refinado": SCORE_POR_NIVEL[nivel],
        "topicos": topicos,
        "texto": "\n".join("- " + t["texto"].replace("**", "") for t in topicos),
    }
