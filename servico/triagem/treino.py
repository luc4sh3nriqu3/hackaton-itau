"""Treina o classificador final a partir do dataset sintético.

Uso:  python -m triagem.treino

- Baseline: regressão logística (padronizada). Principal: LightGBM.
- Escolhe o de maior AUC na validação; calibra com Platt (sigmoide) na validação.
- Limiar de decisão: o maior que mantém recall >= 0,90 na validação (falso negativo custa caro),
  sobre a probabilidade calibrada sem corte (o teto/piso 0,15–0,98 vale só para exibição).
- Avalia no teste: AUC-ROC, precisão/recall/F1 no limiar, Brier (bruto e calibrado),
  curva de calibração, comparação com o score base sozinho e concordância humano-modelo.
- Sessões com coação física ficam fora (tratadas por override de segurança, não por score).
- Preenche `score_refinado` nos CSVs (out-of-fold no treino) e salva modelos/.
"""
import json
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.calibration import calibration_curve
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .banco_perguntas import carregar_banco
from .classificador import PISO, TETO, CalibradorPlatt, ModeloCalibrado
from .config import ARQUIVO_METRICAS, ARQUIVO_MODELO, DADOS_DIR, MODELOS_DIR
from .features import colunas_features, vetorizar

RECALL_ALVO = 0.90
SPLITS = ["treino", "validacao", "teste"]


def _rotulo(df):
    return df["rotulo_real_golpe"].astype(str).str.lower().eq("true").astype(int).to_numpy()


def _sem_coacao(df):
    return df[~df["sinalizador_coacao_fisica"].astype(str).str.lower().eq("true")]


def _modelos():
    return {
        "regressao_logistica": make_pipeline(StandardScaler(), LogisticRegression(C=0.3, max_iter=2000)),
        "lightgbm": LGBMClassifier(
            n_estimators=400, learning_rate=0.03, num_leaves=15, min_child_samples=30,
            subsample=0.8, subsample_freq=1, colsample_bytree=0.7, reg_lambda=1.0, verbose=-1, random_state=42,
        ),
    }


def _limiar_para_recall(y, p, alvo):
    for t in np.sort(np.unique(p))[::-1]:
        if recall_score(y, p >= t) >= alvo:
            return float(t)
    return 0.0


def _metricas(y, p, limiar):
    pred = p >= limiar
    frac_pos, media_pred = calibration_curve(y, p, n_bins=10, strategy="quantile")
    return {
        "auc_roc": round(roc_auc_score(y, p), 4),
        "brier": round(brier_score_loss(y, p), 4),
        "precisao": round(precision_score(y, pred), 4),
        "recall": round(recall_score(y, pred), 4),
        "f1": round(f1_score(y, pred), 4),
        "curva_calibracao": [
            {"prob_media_prevista": round(float(m), 3), "fracao_golpe_real": round(float(f), 3)}
            for m, f in zip(media_pred, frac_pos)
        ],
    }


def _concordancia(df, p, limiar):
    modelo_golpe = p >= limiar
    out = {}
    for veredito, grupo in df.assign(_m=modelo_golpe).groupby("veredito_usuario"):
        out[veredito] = {
            "n": int(len(grupo)),
            "modelo_diz_golpe": round(float(grupo["_m"].mean()), 3),
            "golpe_real": round(float(_rotulo(grupo).mean()), 3),
        }
    return out


def main():
    dfs = {s: pd.read_csv(DADOS_DIR / "sintetico" / f"{s}.csv") for s in SPLITS}
    limpos = {s: _sem_coacao(d) for s, d in dfs.items()}
    X = {s: vetorizar(d) for s, d in limpos.items()}
    y = {s: _rotulo(d) for s, d in limpos.items()}
    colunas = colunas_features()

    comparacao, treinados = {}, {}
    for nome, modelo in _modelos().items():
        modelo.fit(X["treino"][colunas], y["treino"])
        treinados[nome] = modelo
        p_val = modelo.predict_proba(X["validacao"][colunas])[:, 1]
        p_te = modelo.predict_proba(X["teste"][colunas])[:, 1]
        comparacao[nome] = {
            "auc_validacao": round(roc_auc_score(y["validacao"], p_val), 4),
            "auc_teste": round(roc_auc_score(y["teste"], p_te), 4),
            "brier_teste_bruto": round(brier_score_loss(y["teste"], p_te), 4),
        }
    escolhido = max(comparacao, key=lambda n: comparacao[n]["auc_validacao"])
    estimador = treinados[escolhido]

    calibrador = CalibradorPlatt().fit(estimador.predict_proba(X["validacao"][colunas])[:, 1], y["validacao"])
    modelo = ModeloCalibrado(
        estimador=estimador, calibrador=calibrador, colunas=colunas, limiar=0.5,
        versao=datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S"), nome_modelo=escolhido,
    )
    # Decisões usam a probabilidade calibrada sem corte; teto/piso só no score exibido.
    p_val_cal = modelo.prob_calibrada(X["validacao"])
    modelo.limiar = _limiar_para_recall(y["validacao"], p_val_cal, RECALL_ALVO)

    p_te_cal = modelo.prob_calibrada(X["teste"])
    score_base_te = limpos["teste"]["score_inicial_modelo_base"].to_numpy()
    metricas = {
        "versao_modelo": modelo.versao,
        "versao_banco_perguntas": carregar_banco().versao,
        "modelo_escolhido": escolhido,
        "comparacao_modelos": comparacao,
        "limiar_decisao": round(modelo.limiar, 4),
        "recall_alvo": RECALL_ALVO,
        "teste": _metricas(y["teste"], p_te_cal, modelo.limiar),
        "teste_score_exibido_com_teto_piso": {
            "piso": PISO, "teto": TETO,
            "auc_roc": round(roc_auc_score(y["teste"], np.clip(p_te_cal, PISO, TETO)), 4),
            "brier": round(brier_score_loss(y["teste"], np.clip(p_te_cal, PISO, TETO)), 4),
        },
        "teste_score_base_sozinho": {"auc_roc": round(roc_auc_score(y["teste"], score_base_te), 4)},
        "concordancia_humano_modelo_teste": _concordancia(limpos["teste"], p_te_cal, modelo.limiar),
        "tamanhos": {s: int(len(d)) for s, d in limpos.items()},
        "prevalencia_golpe_treino": round(float(y["treino"].mean()), 4),
    }
    modelo.metricas = metricas

    MODELOS_DIR.mkdir(exist_ok=True)
    joblib.dump(modelo, ARQUIVO_MODELO)
    ARQUIVO_METRICAS.write_text(json.dumps(metricas, indent=2, ensure_ascii=False), encoding="utf-8")

    # score_refinado nos CSVs: out-of-fold no treino, modelo final em validação/teste.
    oof = cross_val_predict(
        _modelos()[escolhido], X["treino"][colunas], y["treino"],
        cv=StratifiedKFold(5, shuffle=True, random_state=42), method="predict_proba",
    )[:, 1]
    refinado = {
        "treino": np.clip(calibrador.predict(oof), PISO, TETO),
        "validacao": np.clip(p_val_cal, PISO, TETO),
        "teste": np.clip(p_te_cal, PISO, TETO),
    }
    for s in SPLITS:
        df = dfs[s]
        df["score_refinado"] = np.nan
        df.loc[limpos[s].index, "score_refinado"] = np.round(refinado[s], 4)
        df.to_csv(DADOS_DIR / "sintetico" / f"{s}.csv", index=False)

    t = metricas["teste"]
    print(f"Modelo: {escolhido}  (comparação: {comparacao})")
    print(f"Teste: AUC={t['auc_roc']}  Brier={t['brier']}  limiar={modelo.limiar:.3f}  "
          f"precisão={t['precisao']}  recall={t['recall']}  F1={t['f1']}")
    print(f"AUC do score base sozinho: {metricas['teste_score_base_sozinho']['auc_roc']}")
    print(f"Salvo em {ARQUIVO_MODELO} e {ARQUIVO_METRICAS}")


if __name__ == "__main__":
    main()
