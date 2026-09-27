"""Vetorização de uma sessão (linha no esquema de esquema.COLUNAS) em features do classificador.

Compartilhada entre treino e produção para garantir o mesmo vetor nos dois lados.

- Bloco 1: numéricos (com log onde a escala é multiplicativa), booleanos, hora do dia
  e one-hot dos categóricos. `id`, hash da chave e `motivo_alerta_modelo_base` ficam de fora.
- Bloco 2: como a dimensão de cada posição (1..3) muda entre sessões, as respostas são
  codificadas por pergunta/alternativa (`resp__<pergunta>__<alternativa>`), e não por
  posição, mais a contagem de perguntas por dimensão.
  Os multiplicadores do banco NÃO entram: o modelo reaprende seus próprios pesos.
- `pontuacao_reconhecimento_padroes`. `feedback_cliente` NÃO entra: chega horas depois,
  e o modelo não deve copiar o palpite do cliente.
"""
import numpy as np
import pandas as pd

from .banco_perguntas import DIMENSOES, carregar_banco
from .esquema import CANAIS, TIPOS_CHAVE
from .seletor import FATORES_RISCO, TOTAL_PERGUNTAS


def colunas_features() -> list[str]:
    banco = carregar_banco()
    cols = [
        "log_valor", "log_valor_medio", "desvio_valor_padrao", "log_idade_chave",
        "numero_transacoes_conta_24h", "score_inicial_modelo_base", "logit_score_inicial",
        "destinatario_novo", "horario_transacao_incomum", "dispositivo_reconhecido",
        "velocidade_digitacao_atipica", "hora_sin", "hora_cos",
        "pontuacao_reconhecimento_padroes",
    ]
    cols += [f"chave__{t}" for t in TIPOS_CHAVE]
    cols += [f"canal__{c}" for c in CANAIS]
    cols += [f"fator1__{f}" for f in FATORES_RISCO]
    cols += [f"fator2__{f}" for f in FATORES_RISCO + ["nenhum"]]
    cols += [f"n_dim__{d}" for d in DIMENSOES]
    cols += [f"resp__{p.id}__{a.id}" for p in banco.perguntas for a in p.alternativas]
    return cols


def _bool(serie: pd.Series) -> np.ndarray:
    return serie.map(lambda v: str(v).lower() in ("true", "1", "1.0")).astype(float).to_numpy()


def vetorizar(df: pd.DataFrame) -> pd.DataFrame:
    cols = colunas_features()
    X = pd.DataFrame(0.0, index=df.index, columns=cols)
    score = df["score_inicial_modelo_base"].astype(float).clip(1e-4, 1 - 1e-4)
    hora = pd.to_datetime(df["timestamp_transacao"]).dt.hour + pd.to_datetime(df["timestamp_transacao"]).dt.minute / 60

    X["log_valor"] = np.log1p(df["valor_transacao"].astype(float))
    X["log_valor_medio"] = np.log1p(df["valor_medio_historico_usuario"].astype(float))
    X["desvio_valor_padrao"] = df["desvio_valor_padrao"].astype(float)
    X["log_idade_chave"] = np.log1p(df["idade_chave_pix_destinatario"].astype(float))
    X["numero_transacoes_conta_24h"] = df["numero_transacoes_conta_24h"].astype(float)
    X["score_inicial_modelo_base"] = score
    X["logit_score_inicial"] = np.log(score / (1 - score))
    for c in ["destinatario_novo", "horario_transacao_incomum", "dispositivo_reconhecido", "velocidade_digitacao_atipica"]:
        X[c] = _bool(df[c])
    X["hora_sin"] = np.sin(2 * np.pi * hora / 24)
    X["hora_cos"] = np.cos(2 * np.pi * hora / 24)
    X["pontuacao_reconhecimento_padroes"] = df["pontuacao_reconhecimento_padroes"].astype(float)

    def one_hot(prefixo, valores):
        for i, v in zip(df.index, valores):
            col = f"{prefixo}__{v}"
            if col in X.columns:
                X.at[i, col] = 1.0

    one_hot("chave", df["tipo_chave_pix"])
    one_hot("canal", df["canal_transacao"])
    one_hot("fator1", df["fator_risco_principal"])
    one_hot("fator2", df["fator_risco_secundario"].fillna("nenhum").replace("", "nenhum"))

    for n in range(1, TOTAL_PERGUNTAS + 1):
        for i, pid, dim, resp in zip(df.index, df[f"pergunta_{n}_id"], df[f"pergunta_{n}_dimensao"], df[f"pergunta_{n}_resposta"]):
            if isinstance(pid, str) and pid:
                X.at[i, f"n_dim__{dim}"] += 1
                col = f"resp__{pid}__{resp}"
                if col in X.columns:
                    X.at[i, col] = 1.0
    return X
