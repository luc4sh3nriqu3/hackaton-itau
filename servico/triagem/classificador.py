"""Classificador final: modelo treinado (ver treino.py) + calibração de Platt + teto/piso."""
from dataclasses import dataclass, field
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from .config import ARQUIVO_MODELO
from .features import vetorizar

PISO, TETO = 0.15, 0.98


class CalibradorPlatt:
    """Regressão logística sobre o logit da probabilidade bruta (monótona: preserva a AUC)."""

    def __init__(self):
        self._lr = LogisticRegression(C=1e6)

    @staticmethod
    def _logit(p):
        p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
        return np.log(p / (1 - p)).reshape(-1, 1)

    def fit(self, p, y):
        self._lr.fit(self._logit(p), y)
        return self

    def predict(self, p):
        return self._lr.predict_proba(self._logit(p))[:, 1]


@dataclass
class ModeloCalibrado:
    estimador: object
    calibrador: CalibradorPlatt
    colunas: list[str]
    limiar: float
    versao: str
    nome_modelo: str
    metricas: dict = field(default_factory=dict)

    def prob_bruta(self, X: pd.DataFrame) -> np.ndarray:
        return self.estimador.predict_proba(X[self.colunas])[:, 1]

    def prob_calibrada(self, X: pd.DataFrame) -> np.ndarray:
        return self.calibrador.predict(self.prob_bruta(X))

    def prever_sessoes(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        """Retorna (probabilidade interna, score exibido).

        A interna (sem corte) é usada nas decisões (limiar, nível de risco); o score
        exibido ao usuário tem teto/piso para nunca comunicar certeza absoluta.
        """
        p = self.prob_calibrada(vetorizar(df))
        return p, np.clip(p, PISO, TETO)


@lru_cache(maxsize=1)
def carregar_modelo() -> ModeloCalibrado:
    if not ARQUIVO_MODELO.exists():
        raise FileNotFoundError(
            f"Modelo não encontrado em {ARQUIVO_MODELO}. Rode: python -m triagem.gerador_dataset && python -m triagem.treino"
        )
    return joblib.load(ARQUIVO_MODELO)


def nivel_risco(prob_interna: float, limiar: float) -> str:
    """Abaixo do limiar (escolhido para recall >= 90%) é baixo; acima de 0,5 é alto."""
    if prob_interna >= max(limiar, 0.5):
        return "alto"
    if prob_interna >= limiar:
        return "moderado"
    return "baixo"
