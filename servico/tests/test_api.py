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
}


def _primeira_nao_coacao(pergunta, indice=0):
    from triagem.banco_perguntas import carregar_banco

    alts = [a for a in carregar_banco().por_id[pergunta["id"]].alternativas if not a.coacao]
    return alts[indice % len(alts)].id


def test_sem_chave_api(cliente):
    r = cliente.post("/v1/sessoes", json=SITUACAO, headers={"X-API-Key": "errada"})
    assert r.status_code == 401


def test_fluxo_completo(cliente):
    r = cliente.post("/v1/sessoes", json=SITUACAO)
    assert r.status_code == 201, r.text
    corpo = r.json()
    sid = corpo["sessao_id"]
    assert "multiplicador" not in str(corpo["pergunta"])  # nada interno vaza

    for n in range(1, 4):
        assert corpo["progresso"]["atual"] == n
        r = cliente.post(f"/v1/sessoes/{sid}/respostas", json={
            "pergunta_id": corpo["pergunta"]["id"], "alternativa_id": _primeira_nao_coacao(corpo["pergunta"]),
        })
        assert r.status_code == 200, r.text
        corpo = r.json()
    assert corpo["status"] == "aguardando_veredito"

    assert cliente.get(f"/v1/sessoes/{sid}/resultado").status_code == 409
    r = cliente.post(f"/v1/sessoes/{sid}/veredito", json={"veredito_usuario": "nao_tenho_certeza"})
    assert r.status_code == 200, r.text

    res = cliente.get(f"/v1/sessoes/{sid}/resultado").json()
    assert 0.15 <= res["score_refinado"] <= 0.98
    assert res["nivel_risco"] in ("baixo", "moderado", "alto")
    assert res["fonte_explicacao"] == "template"
    assert res["explicacao_gerada"]
    assert cliente.post(f"/v1/sessoes/{sid}/decisao", json={"usuario_seguiu_recomendacao": True}).status_code == 204


def test_respostas_arriscadas_aumentam_score(cliente):
    from triagem.banco_perguntas import carregar_banco

    banco = carregar_banco()

    def rodar(escolha):
        corpo = cliente.post("/v1/sessoes", json=SITUACAO).json()
        sid = corpo["sessao_id"]
        while corpo["status"] == "em_andamento":
            alts = [a for a in banco.por_id[corpo["pergunta"]["id"]].alternativas if not a.coacao]
            alt = escolha(alts, key=lambda a: a.multiplicador)
            corpo = cliente.post(f"/v1/sessoes/{sid}/respostas", json={
                "pergunta_id": corpo["pergunta"]["id"], "alternativa_id": alt.id}).json()
        return cliente.post(f"/v1/sessoes/{sid}/veredito", json={"veredito_usuario": "nao_e_golpe"}).json()

    arriscado, seguro = rodar(max), rodar(min)
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
