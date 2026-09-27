import pytest

from test_api import SITUACAO

RESPOSTAS_JOSE = {"DEMO_urgencia": "sim", "DEMO_destinatario": "sim", "DEMO_motivo": "quitar_dividas"}


@pytest.fixture
def demo(cliente, monkeypatch):
    monkeypatch.setenv("TRIAGEM_MODO_DEMO", "1")
    return cliente


def _rodar(cliente, respostas, nome="Lucas Henrique Amorim Da Silva"):
    corpo = cliente.post("/v1/sessoes", json={**SITUACAO, "nome_destinatario": nome}).json()
    sid, perguntas = corpo["sessao_id"], []
    while corpo["status"] == "em_andamento":
        perguntas.append(corpo["pergunta"])
        pid = corpo["pergunta"]["id"]
        r = cliente.post(f"/v1/sessoes/{sid}/respostas", json={"pergunta_id": pid, "alternativa_id": respostas[pid]})
        assert r.status_code == 200, r.text
        corpo = r.json()
    assert corpo["status"] == "concluida"
    return sid, perguntas, cliente.get(f"/v1/sessoes/{sid}/resultado").json()


def test_perguntas_fixas_em_ordem_com_nome(demo):
    _, perguntas, _ = _rodar(demo, RESPOSTAS_JOSE)
    assert [p["id"] for p in perguntas] == ["DEMO_urgencia", "DEMO_destinatario", "DEMO_motivo"]
    assert "**Lucas Henrique Amorim Da Silva**" in perguntas[1]["pergunta"]
    assert all(p["texto_didatico"] for p in perguntas)


def test_resultado_mockado_do_jose(demo, monkeypatch):
    from triagem import gemini

    monkeypatch.setattr(gemini, "gerar_explicacao", lambda *a, **k: pytest.fail("Gemini não deve ser chamado"))
    sid, _, res = _rodar(demo, RESPOSTAS_JOSE)
    assert res["nivel_risco"] == "alto" and res["fonte_explicacao"] == "demo" and res["versao_modelo"] == "demo"
    tons = [t["tom"] for t in res["explicacao_topicos"]]
    assert tons == ["alerta", "alerta", "ok", "atencao"]  # risco primeiro, bom sinal, ação no fim
    assert "Cobrança de dívida por mensagem" in res["explicacao_topicos"][1]["texto"]
    assert res["explicacao_gerada"] and "**" not in res["explicacao_gerada"]

    # O resto do fluxo continua igual: decisão e feedback.
    assert demo.post(f"/v1/sessoes/{sid}/decisao", json={"decisao": "continuar"}).status_code == 204
    pendentes = demo.get("/v1/feedbacks/pendentes", params={"cliente_id": "cliente-teste"}).json()
    assert [p["sessao_id"] for p in pendentes] == [sid]


def test_nivel_depende_das_respostas(demo):
    # Todo motivo da pergunta 3 é um padrão de golpe, então a sessão completa sempre dá "alto".
    _, _, res = _rodar(demo, {"DEMO_urgencia": "nao", "DEMO_destinatario": "sim", "DEMO_motivo": "parente"})
    assert res["nivel_risco"] == "alto"

    from triagem import demo as modulo

    r = modulo.resultado([("DEMO_urgencia", "nao"), ("DEMO_destinatario", "sim")])
    assert r["nivel_risco"] == "baixo" and all(t["tom"] != "alerta" for t in r["topicos"])


def test_alternativa_invalida_na_demo(demo):
    corpo = demo.post("/v1/sessoes", json=SITUACAO).json()
    r = demo.post(f"/v1/sessoes/{corpo['sessao_id']}/respostas", json={"pergunta_id": "DEMO_urgencia", "alternativa_id": "talvez"})
    assert r.status_code == 422


def test_nome_padrao_sem_destinatario():
    from triagem import demo as modulo

    assert "**o destinatário**" in modulo.pergunta(2, None)["pergunta"]


def test_modo_real_continua_igual(cliente):
    corpo = cliente.post("/v1/sessoes", json=SITUACAO).json()
    assert not corpo["pergunta"]["id"].startswith("DEMO_")
