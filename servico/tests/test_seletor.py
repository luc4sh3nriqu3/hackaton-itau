from collections import Counter

import numpy as np

from triagem.banco_perguntas import carregar_banco
from triagem.seletor import TOTAL_PERGUNTAS, SeletorPonderado


def _sessao(seletor, fator, secundario=None):
    feitas = []
    while (p := seletor.proxima_pergunta(feitas, fator, secundario)) is not None:
        feitas.append(p.id)
    return feitas


def test_banco_valido():
    banco = carregar_banco()
    assert 28 <= len(banco.perguntas) <= 35
    assert {p.dimensao for p in banco.perguntas} == set(banco.dimensoes)


def test_dez_perguntas_distintas():
    feitas = _sessao(SeletorPonderado(rng=np.random.default_rng(0)), "valor_atipico")
    assert len(feitas) == TOTAL_PERGUNTAS == len(set(feitas))


def test_vies_pelo_fator_de_risco():
    seletor = SeletorPonderado(rng=np.random.default_rng(1))
    contagem = Counter()
    for _ in range(500):
        contagem.update(pid[:2] for pid in _sessao(seletor, "dispositivo_nao_reconhecido"))
    mais_comuns = {d for d, _ in contagem.most_common(2)}
    assert mais_comuns == {"P7", "P1"}


def test_sessoes_variam():
    seletor = SeletorPonderado(rng=np.random.default_rng(2))
    assert len({tuple(_sessao(seletor, "horario_incomum")) for _ in range(20)}) > 15
