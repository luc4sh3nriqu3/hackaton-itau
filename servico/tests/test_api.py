SITUACAO = {
    "valor_transacao": 1500.0,
    "valor_medio_historico_usuario": 180.0,
    "destinatario_chave_pix_hash": "abc123",
    "tipo_chave_pix": "aleatoria",
    "destinatario_novo": True,
    "idade_chave_pix_destinatario": 3,
    "horario_transacao_incomum": False,
    "dispositivo_reconhecido": True,
    "velocidade_digitacao_atipica": False,
    "numero_transacoes_conta_24h": 2,
    "canal_transacao": "app",
    "motivo_alerta_modelo_base": "valor acima do padrão + destinatário novo",
    "fator_risco_principal": "valor_atipico",
    "fator_risco_secundario": "destinatario_novo_ou_desconhecido",
    "score_inicial_modelo_base": 0.72,
    "cliente_id": "cliente-teste",
    "descricao_exibicao": "Pix de R$ 1.500,00 para Lucas",
}


def _primeira_nao_coacao(pergunta, indice=0):
    from triagem.banco_perguntas import carregar_banco

    alts = [a for a in carregar_banco().por_id[pergunta["id"]].alternativas if not a.coacao]
    return alts[indice % len(alts)].id


def test_sem_chave_api(cliente):
    r = cliente.post("/v1/sessoes", json=SITUACAO, headers={"X-API-Key": "errada"})
    assert r.status_code == 401


def _responder_tudo(cliente, escolha=None):
    """Responde as 3 perguntas (sem coação) e devolve (sessao_id, última etapa)."""
    from triagem.banco_perguntas import carregar_banco

    banco = carregar_banco()
    corpo = cliente.post("/v1/sessoes", json=SITUACAO).json()
    sid = corpo["sessao_id"]
    while corpo["status"] == "em_andamento":
        alts = [a for a in banco.por_id[corpo["pergunta"]["id"]].alternativas if not a.coacao]
        alt = escolha(alts, key=lambda a: a.multiplicador) if escolha else alts[0]
        r = cliente.post(f"/v1/sessoes/{sid}/respostas", json={"pergunta_id": corpo["pergunta"]["id"], "alternativa_id": alt.id})
        assert r.status_code == 200, r.text
        corpo = r.json()
    return sid, corpo


def test_fluxo_completo(cliente):
    r = cliente.post("/v1/sessoes", json=SITUACAO)
    assert r.status_code == 201, r.text
    corpo = r.json()
    sid = corpo["sessao_id"]
    assert "multiplicador" not in str(corpo["pergunta"])  # nada interno vaza
    assert cliente.get(f"/v1/sessoes/{sid}/resultado").status_code == 409

    for n in range(1, 4):
        assert corpo["progresso"]["atual"] == n
        r = cliente.post(f"/v1/sessoes/{sid}/respostas", json={
            "pergunta_id": corpo["pergunta"]["id"], "alternativa_id": _primeira_nao_coacao(corpo["pergunta"]),
        })
        assert r.status_code == 200, r.text
        corpo = r.json()
    assert corpo["status"] == "concluida"  # sem etapa de veredito: a 3ª resposta já conclui

    res = cliente.get(f"/v1/sessoes/{sid}/resultado").json()
    assert 0.15 <= res["score_refinado"] <= 0.98
    assert res["nivel_risco"] in ("baixo", "moderado", "alto")
    assert res["fonte_explicacao"] == "template"
    assert res["explicacao_gerada"] and "%" not in res["explicacao_gerada"]
    assert cliente.post(f"/v1/sessoes/{sid}/decisao", json={"decisao": "continuar"}).status_code == 204


def test_respostas_arriscadas_aumentam_score(cliente):
    sid_arriscado, _ = _responder_tudo(cliente, max)
    sid_seguro, _ = _responder_tudo(cliente, min)
    arriscado = cliente.get(f"/v1/sessoes/{sid_arriscado}/resultado").json()
    seguro = cliente.get(f"/v1/sessoes/{sid_seguro}/resultado").json()
    assert arriscado["score_refinado"] > seguro["score_refinado"]
    assert arriscado["nivel_risco"] == "alto" and seguro["nivel_risco"] == "baixo"


def test_coacao_interrompe_fluxo(cliente):
    from triagem.banco_perguntas import carregar_banco

    banco = carregar_banco()
    corpo = cliente.post("/v1/sessoes", json=SITUACAO).json()
    sid = corpo["sessao_id"]
    while True:
        pergunta = banco.por_id[corpo["pergunta"]["id"]]
        coacao = [a for a in pergunta.alternativas if a.coacao]
        alt = coacao[0] if coacao else pergunta.alternativas[-1]
        corpo = cliente.post(f"/v1/sessoes/{sid}/respostas", json={"pergunta_id": pergunta.id, "alternativa_id": alt.id}).json()
        if coacao or corpo["status"] != "em_andamento":
            break
    if corpo["status"] != "coacao":
        return  # sessão sorteada sem pergunta com alternativa de coação
    assert "190" in corpo["orientacao_seguranca"]
    assert cliente.post(f"/v1/sessoes/{sid}/respostas", json={"pergunta_id": "x", "alternativa_id": "a"}).status_code == 409
    res = cliente.get(f"/v1/sessoes/{sid}/resultado").json()
    assert res["sinalizador_coacao_fisica"] and res["score_refinado"] is None and res["fonte_explicacao"] == "seguranca"


def test_chave_gemini_lida_dinamicamente(tmp_path, monkeypatch):
    from triagem import config

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    env = tmp_path / ".env"
    monkeypatch.setattr(config, "ARQUIVO_ENV", env)
    assert not config.obter("GEMINI_API_KEY")
    env.write_text("GEMINI_API_KEY=nova-chave\n")
    assert config.obter("GEMINI_API_KEY") == "nova-chave"


def _pendentes(cliente):
    r = cliente.get("/v1/feedbacks/pendentes", params={"cliente_id": "cliente-teste"})
    assert r.status_code == 200, r.text
    return [p["sessao_id"] for p in r.json()]


def test_feedback_so_para_quem_continuou(cliente):
    sid_continuou, _ = _responder_tudo(cliente)
    sid_cancelou, _ = _responder_tudo(cliente)
    sid_sem_decisao, _ = _responder_tudo(cliente)
    cliente.post(f"/v1/sessoes/{sid_continuou}/decisao", json={"decisao": "continuar"})
    cliente.post(f"/v1/sessoes/{sid_cancelou}/decisao", json={"decisao": "cancelar"})

    assert _pendentes(cliente) == [sid_continuou]
    pendente = cliente.get("/v1/feedbacks/pendentes", params={"cliente_id": "cliente-teste"}).json()[0]
    assert pendente["descricao_exibicao"] == "Pix de R$ 1.500,00 para Lucas"
    assert cliente.get("/v1/feedbacks/pendentes", params={"cliente_id": "outro"}).json() == []


def test_feedback_exibido_e_respondido(cliente, tmp_path):
    from triagem import api

    sid, _ = _responder_tudo(cliente)
    cliente.post(f"/v1/sessoes/{sid}/decisao", json={"decisao": "continuar"})
    assert api.armazenamento().obter(sid)["feedback_cliente"] == "sem_resposta"  # padrão

    assert cliente.post(f"/v1/sessoes/{sid}/feedback/exibido").status_code == 204
    assert _pendentes(cliente) == []  # não pergunta de novo

    assert cliente.post(f"/v1/sessoes/{sid}/feedback", json={"feedback_cliente": "talvez"}).status_code == 422
    assert cliente.post(f"/v1/sessoes/{sid}/feedback", json={"feedback_cliente": "golpe"}).status_code == 204
    sessao = api.armazenamento().obter(sid)
    assert sessao["feedback_cliente"] == "golpe" and sessao["feedback_respondido_em"]


def test_feedback_respeita_atraso(cliente, monkeypatch):
    sid, _ = _responder_tudo(cliente)
    cliente.post(f"/v1/sessoes/{sid}/decisao", json={"decisao": "continuar"})
    monkeypatch.setenv("FEEDBACK_ATRASO_MINUTOS", "60")
    assert _pendentes(cliente) == []
    monkeypatch.setenv("FEEDBACK_ATRASO_MINUTOS", "0")
    assert _pendentes(cliente) == [sid]


def test_decisao_define_se_seguiu_recomendacao(cliente):
    from triagem import api

    sid, _ = _responder_tudo(cliente, max)  # risco alto
    cliente.post(f"/v1/sessoes/{sid}/decisao", json={"decisao": "cancelar"})
    assert api.armazenamento().obter(sid)["usuario_seguiu_recomendacao"] == 1
    assert cliente.post(f"/v1/sessoes/{sid}/decisao", json={"decisao": "talvez"}).status_code == 422
