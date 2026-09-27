"""Seletor de perguntas — regra determinística com sorteio ponderado.

prioridade(dimensão) = amplitude_log(dimensão) × boost_fator_risco(dimensão)
                       × PENALIDADE_REPETICAO ^ (nº de perguntas já feitas na dimensão)
                       × [dimensão ainda tem faceta não perguntada]

- boost = 2,0 se a dimensão está no mapa do fator de risco principal, 1,3 se está no
  do secundário, 1,0 caso contrário.
- Cobertura suave: a penalidade por repetição faz as perguntas preferirem dimensões
  diferentes, sem proibir repetir uma dimensão do fator de risco. Aumentar BOOST_PRINCIPAL
  ou PENALIDADE_REPETICAO concentra mais nas dimensões do fator de risco.
- Dentro da dimensão sorteada, a faceta é escolhida uniformemente entre as não perguntadas.

Módulo substituível: qualquer objeto com `proxima_pergunta(...)` compatível serve
(ex.: um agente LLM que escolha a próxima pergunta de forma mais adaptativa).
"""
from collections import Counter
from typing import Protocol, Sequence

import numpy as np

from .banco_perguntas import DIMENSOES, Banco, Pergunta, carregar_banco

TOTAL_PERGUNTAS = 3

MAPA_FATOR_DIMENSOES = {
    "valor_atipico": ["P2", "P5"],
    "destinatario_novo_ou_desconhecido": ["P5", "P6", "P3"],
    "dispositivo_nao_reconhecido": ["P7", "P1"],
    "velocidade_digitacao_atipica": ["P2", "P7"],
    "horario_incomum": ["P4", "P1"],
    "chave_pix_recente": ["P3", "P6"],
    "volume_transacoes_24h_alto": ["P2", "P4"],
}
FATORES_RISCO = list(MAPA_FATOR_DIMENSOES)

BOOST_PRINCIPAL = 2.0
BOOST_SECUNDARIO = 1.3
PENALIDADE_REPETICAO = 0.6


class SeletorPerguntas(Protocol):
    def proxima_pergunta(
        self,
        ja_perguntadas: Sequence[str],
        fator_principal: str,
        fator_secundario: str | None,
    ) -> Pergunta | None: ...


def boost(dimensao: str, fator_principal: str, fator_secundario: str | None) -> float:
    if dimensao in MAPA_FATOR_DIMENSOES.get(fator_principal, []):
        return BOOST_PRINCIPAL
    if fator_secundario and dimensao in MAPA_FATOR_DIMENSOES.get(fator_secundario, []):
        return BOOST_SECUNDARIO
    return 1.0


class SeletorPonderado:
    def __init__(self, banco: Banco | None = None, rng: np.random.Generator | None = None):
        self.banco = banco or carregar_banco()
        self.rng = rng or np.random.default_rng()

    def pesos(self, ja_perguntadas, fator_principal, fator_secundario) -> dict[str, float]:
        feitas = set(ja_perguntadas)
        repeticoes = Counter(self.banco.por_id[p].dimensao for p in feitas)
        return {
            d: self.banco.amplitude_log(d)
            * boost(d, fator_principal, fator_secundario)
            * PENALIDADE_REPETICAO ** repeticoes[d]
            for d in DIMENSOES
            if any(p.id not in feitas for p in self.banco.da_dimensao(d))
        }

    def proxima_pergunta(self, ja_perguntadas, fator_principal, fator_secundario=None):
        if len(ja_perguntadas) >= TOTAL_PERGUNTAS:
            return None
        pesos = self.pesos(ja_perguntadas, fator_principal, fator_secundario)
        if not pesos:
            return None
        dims = sorted(pesos)
        p = np.array([pesos[d] for d in dims])
        dimensao = dims[self.rng.choice(len(dims), p=p / p.sum())]
        opcoes = [q for q in self.banco.da_dimensao(dimensao) if q.id not in set(ja_perguntadas)]
        return opcoes[self.rng.integers(len(opcoes))]
