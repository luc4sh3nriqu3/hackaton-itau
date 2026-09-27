"""Gerador do dataset sintético de sessões de triagem (esquema.COLUNAS).

Uso:  python -m triagem.gerador_dataset --n 12000 --semente 42

Processo gerador ("verdade" que o classificador vai aprender a aproximar):
1. Sorteia uma situação latente: legítima ou um tipo de golpe, com proporções
   inspiradas nas fontes (Pizzolato et al. 2025; Observatório Lupa, "A Jornada dos
   Golpes": WhatsApp ~65%, marca/instituição conhecida 74%, promessa de vantagem 71%).
2. Gera o Bloco 1 (sinais da transação) condicionado à situação: valores altos e
   redondos, madrugada, chave recente, dispositivo não reconhecido na mão fantasma etc.
   O "modelo base" é simulado somando contribuições por fator de risco; o maior vira
   `fator_risco_principal`, o segundo `fator_risco_secundario`.
3. Escolhe as 3 perguntas com o MESMO seletor usado em produção e amostra as respostas
   condicionadas à situação latente e à consciência de risco do usuário.
4. Rótulo: logit(p) = A·logit(score_base) + B·Σ log(multiplicador) + ruído + C → Bernoulli.
   Os multiplicadores do banco só entram aqui, nunca no classificador de produção.
5. Veredito do usuário: mais acurado quanto maior a consciência de risco (que também
   gera as respostas "protetoras" → pontuacao_reconhecimento_padroes).
"""
import argparse
import uuid
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .banco_perguntas import carregar_banco
from .config import DADOS_DIR
from .esquema import COLUNAS, TIPOS_CHAVE
from .seletor import FATORES_RISCO, TOTAL_PERGUNTAS, SeletorPonderado

PROB_GOLPE_LATENTE = 0.34
DIST_TIPOS = {
    "falsa_central": 0.21,
    "whatsapp_clonado": 0.22,
    "venda_falsa": 0.19,
    "mao_fantasma": 0.12,
    "falsa_taxa": 0.13,
    "outro": 0.10,
    "sequestro_pix": 0.03,
}
# Coeficientes do rótulo (ajustados para ~30% de golpe e separabilidade realista).
A_SCORE, B_MULT, C_INTERCEPTO, RUIDO = 1.0, 0.8, -2.3, 1.2

VALORES_REDONDOS = np.array([200, 300, 500, 800, 1000, 1500, 2000, 3000, 5000])
DESCRICAO_FATOR = {
    "valor_atipico": "valor acima do padrão do cliente",
    "destinatario_novo_ou_desconhecido": "destinatário novo",
    "dispositivo_nao_reconhecido": "dispositivo não reconhecido",
    "velocidade_digitacao_atipica": "digitação atípica (possível acesso remoto)",
    "horario_incomum": "horário incomum",
    "chave_pix_recente": "chave Pix cadastrada recentemente",
    "volume_transacoes_24h_alto": "muitas transações nas últimas 24h",
}


def _sigmoid(x):
    return 1 / (1 + np.exp(-x))


def _logit(p):
    return np.log(p / (1 - p))


def contribuicoes_risco(
    valor, valor_medio, destinatario_novo, dispositivo_reconhecido,
    velocidade_atipica, horario_incomum, idade_chave, n_24h,
) -> dict[str, float]:
    """Simulação do 'modelo base': quanto cada fator pesa no alerta."""
    razao = valor / valor_medio
    redondo = float(valor >= 200 and valor % 100 == 0)
    return {
        "valor_atipico": max(0.0, np.log(razao)) * 0.8 + 0.3 * redondo,
        "destinatario_novo_ou_desconhecido": 0.9 * destinatario_novo,
        "dispositivo_nao_reconhecido": 1.4 * (not dispositivo_reconhecido),
        "velocidade_digitacao_atipica": 1.2 * velocidade_atipica,
        "horario_incomum": 0.9 * horario_incomum,
        "chave_pix_recente": 1.0 * (idade_chave < 30) + 0.3 * (idade_chave < 7),
        "volume_transacoes_24h_alto": 0.3 * max(0, n_24h - 3),
    }


def fatores_e_motivo(contrib: dict[str, float], rng) -> tuple[str, str | None, str]:
    ordenados = sorted(contrib, key=lambda f: contrib[f] + rng.normal(0, 0.01), reverse=True)
    principal = ordenados[0]
    secundario = ordenados[1] if contrib[ordenados[1]] > 0.3 else None
    motivo = DESCRICAO_FATOR[principal] + (f" + {DESCRICAO_FATOR[secundario]}" if secundario else "")
    return principal, secundario, motivo


def _gerar_bloco1(tipo: str | None, rng, inicio: datetime) -> dict:
    golpe = tipo is not None
    valor_medio = float(np.clip(np.exp(rng.normal(np.log(250), 0.9)), 50, 5000))
    if golpe and rng.random() < 0.6:
        alvo = valor_medio * np.exp(rng.normal(1.1, 0.7))
        valor = float(VALORES_REDONDOS[np.abs(VALORES_REDONDOS - alvo).argmin()])
    elif golpe:
        valor = valor_medio * np.exp(rng.normal(0.9, 0.9))
    else:
        valor = valor_medio * np.exp(rng.normal(-0.3, 0.9))
        if rng.random() < 0.15:
            valor = float(round(valor, -2)) or 100.0
    valor = float(np.clip(round(valor, 2), 5, 50000))

    madrugada = rng.random() < (0.25 if golpe else 0.06)
    hora = int(rng.integers(0, 6)) if madrugada else int(np.clip(rng.normal(14, 3.5), 6, 23))
    ts = inicio + timedelta(days=int(rng.integers(0, 365)), hours=hora, minutes=int(rng.integers(0, 60)))
    horario_incomum = bool(hora < 6 or hora >= 22 or rng.random() < 0.03)

    if golpe:
        p_chave = [0.25, 0.10, 0.25, 0.40]
    else:
        p_chave = [0.35, 0.15, 0.30, 0.20]
    tipo_chave = TIPOS_CHAVE[rng.choice(4, p=p_chave)]

    p_novo = {None: 0.45, "whatsapp_clonado": 0.8}.get(tipo, 0.92)
    destinatario_novo = bool(rng.random() < p_novo)
    idade_chave = int(np.clip(np.exp(rng.normal(np.log(20 if golpe else 400), 1.3)), 0, 4000))

    p_disp = {None: 0.95, "mao_fantasma": 0.35, "sequestro_pix": 0.85}.get(tipo, 0.9)
    dispositivo_reconhecido = bool(rng.random() < p_disp)
    p_vel = {None: 0.06, "mao_fantasma": 0.7, "sequestro_pix": 0.4}.get(tipo, 0.12)
    velocidade_atipica = bool(rng.random() < p_vel)
    lam = {None: 2, "mao_fantasma": 6, "sequestro_pix": 7, "falsa_taxa": 4}.get(tipo, 3)
    n_24h = int(rng.poisson(lam))
    canal = "internet_banking" if rng.random() < (0.3 if tipo == "mao_fantasma" else 0.15) else "app"

    contrib = contribuicoes_risco(
        valor, valor_medio, destinatario_novo, dispositivo_reconhecido,
        velocidade_atipica, horario_incomum, idade_chave, n_24h,
    )
    principal, secundario, motivo = fatores_e_motivo(contrib, rng)
    score = float(np.clip(0.55 + 0.35 * _sigmoid(sum(contrib.values()) - 2.2 + rng.normal(0, 0.6)), 0.5, 0.95))

    return {
        "id_transacao": str(uuid.UUID(int=int(rng.integers(0, 2**63)) << 64 | int(rng.integers(0, 2**63)))),
        "timestamp_transacao": ts.isoformat(),
        "valor_transacao": valor,
        "valor_medio_historico_usuario": round(valor_medio, 2),
        "desvio_valor_padrao": round((valor - valor_medio) / valor_medio, 4),
        "destinatario_chave_pix_hash": uuid.UUID(int=int(rng.integers(0, 2**63))).hex,
        "tipo_chave_pix": tipo_chave,
        "destinatario_novo": destinatario_novo,
        "idade_chave_pix_destinatario": idade_chave,
        "horario_transacao_incomum": horario_incomum,
        "dispositivo_reconhecido": dispositivo_reconhecido,
        "velocidade_digitacao_atipica": velocidade_atipica,
        "numero_transacoes_conta_24h": n_24h,
        "canal_transacao": canal,
        "motivo_alerta_modelo_base": motivo,
        "fator_risco_principal": principal,
        "fator_risco_secundario": secundario,
        "score_inicial_modelo_base": round(score, 4),
    }


def _amostrar_resposta(pergunta, tipo, consciencia, rng):
    pesos = []
    for alt in pergunta.alternativas:
        if alt.coacao:
            w = 12.0 if tipo == "sequestro_pix" else 0.0
        elif tipo is None:
            w = alt.multiplicador ** -1.0
        else:
            afinidade = 4.0 if tipo in alt.tipos else (0.5 if alt.tipos else 1.0)
            w = alt.multiplicador ** 0.8 * afinidade
        if alt.protetora:
            w *= 0.25 + 2.0 * consciencia
        pesos.append(w)
    pesos = np.array(pesos)
    return pergunta.alternativas[rng.choice(len(pesos), p=pesos / pesos.sum())]


def gerar_sessao(rng, seletor, inicio) -> dict:
    tipo = rng.choice(list(DIST_TIPOS), p=list(DIST_TIPOS.values())) if rng.random() < PROB_GOLPE_LATENTE else None
    linha = _gerar_bloco1(tipo, rng, inicio)
    consciencia = float(rng.beta(2, 2))

    feitas, soma_log, protetoras, coacao = [], 0.0, 0, False
    for n in range(1, TOTAL_PERGUNTAS + 1):
        linha.update({f"pergunta_{n}_{c}": None for c in ("id", "dimensao", "resposta", "multiplicador")})
    for n in range(1, TOTAL_PERGUNTAS + 1):
        pergunta = seletor.proxima_pergunta(feitas, linha["fator_risco_principal"], linha["fator_risco_secundario"])
        alt = _amostrar_resposta(pergunta, tipo, consciencia, rng)
        feitas.append(pergunta.id)
        linha[f"pergunta_{n}_id"] = pergunta.id
        linha[f"pergunta_{n}_dimensao"] = pergunta.dimensao
        linha[f"pergunta_{n}_resposta"] = alt.id
        linha[f"pergunta_{n}_multiplicador"] = alt.multiplicador
        soma_log += np.log(alt.multiplicador)
        protetoras += alt.protetora
        if alt.coacao:
            coacao = True  # fluxo educativo interrompido, como na API
            break
    linha["sinalizador_coacao_fisica"] = coacao

    if coacao:
        rotulo = True
    else:
        z = A_SCORE * _logit(linha["score_inicial_modelo_base"]) + B_MULT * soma_log + C_INTERCEPTO
        rotulo = bool(rng.random() < _sigmoid(z + rng.normal(0, RUIDO)))
    tipo_rotulo = (tipo or "outro") if rotulo else None

    p_incerto = 0.08 + 0.35 * (1 - consciencia)
    if rng.random() < p_incerto:
        veredito = "nao_tenho_certeza"
    else:
        acerta = rng.random() < 0.5 + 0.45 * consciencia
        veredito = "golpe" if rotulo == acerta else "nao_e_golpe"

    linha.update({
        "veredito_usuario": veredito,
        "pontuacao_reconhecimento_padroes": int(protetoras),
        "score_refinado": None,  # preenchido por treino.py (predição out-of-fold)
        "rotulo_real_golpe": rotulo,
        "rotulo_tipo_golpe": tipo_rotulo,
        "explicacao_gerada": None,
        "usuario_seguiu_recomendacao": None,
    })
    return linha


def gerar(n: int, semente: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(semente)
    seletor = SeletorPonderado(carregar_banco(), rng=rng)
    inicio = datetime(2025, 7, 1)
    return pd.DataFrame([gerar_sessao(rng, seletor, inicio) for _ in range(n)], columns=COLUNAS)


def salvar_splits(df: pd.DataFrame, semente: int = 42) -> dict[str, pd.DataFrame]:
    idx = np.random.default_rng(semente + 1).permutation(len(df))
    n_tr, n_va = int(0.8 * len(df)), int(0.9 * len(df))
    splits = {
        "treino": df.iloc[idx[:n_tr]],
        "validacao": df.iloc[idx[n_tr:n_va]],
        "teste": df.iloc[idx[n_va:]],
    }
    destino = DADOS_DIR / "sintetico"
    destino.mkdir(parents=True, exist_ok=True)
    for nome, parte in splits.items():
        parte.to_csv(destino / f"{nome}.csv", index=False)
    return splits


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=12000, help="nº de sessões (8.000 a 20.000)")
    ap.add_argument("--semente", type=int, default=42)
    args = ap.parse_args()
    if not 8000 <= args.n <= 20000:
        ap.error("--n deve estar entre 8000 e 20000")
    df = gerar(args.n, args.semente)
    splits = salvar_splits(df, args.semente)
    print(f"{len(df)} sessões, {len(df.columns)} colunas, golpe={df.rotulo_real_golpe.mean():.1%}, "
          f"coação={df.sinalizador_coacao_fisica.mean():.1%}")
    for nome, parte in splits.items():
        print(f"  {nome}: {len(parte)} ({parte.rotulo_real_golpe.mean():.1%} golpe)")
    print(df.rotulo_tipo_golpe.value_counts(normalize=True).round(3).to_string())


if __name__ == "__main__":
    main()
