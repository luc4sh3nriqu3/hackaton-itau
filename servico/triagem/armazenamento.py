"""Persistência das sessões em SQLite.

Uma linha por sessão com as colunas do esquema (esquema.COLUNAS) + metadados. Esse log (respostas +
score + decisão + feedback do cliente + versões de modelo/banco) é o insumo do retreino periódico:
o `feedback_cliente` do pop-up pós-transação, somado à confirmação externa do desfecho, preenche
`rotulo_real_golpe`/`rotulo_tipo_golpe`, e as linhas viram dados rotulados reais no mesmo formato
do dataset sintético, ex.:
    SELECT <esquema.COLUNAS> FROM sessoes WHERE rotulo_real_golpe IS NOT NULL
"""
import sqlite3
import threading
from datetime import datetime, timezone

from .config import obter
from .esquema import COLUNAS

METADADOS = [
    "sessao_id", "status", "criada_em", "atualizada_em", "versao_modelo",
    "versao_banco_perguntas", "prob_interna", "nivel_risco", "fonte_explicacao",
    "cliente_id", "descricao_exibicao", "decisao_cliente", "concluida_em",
    "feedback_exibido_em", "feedback_respondido_em",
]


class Armazenamento:
    def __init__(self, caminho: str | None = None):
        self.caminho = caminho or obter("TRIAGEM_DB")
        self._lock = threading.Lock()
        self._con = sqlite3.connect(self.caminho, check_same_thread=False)
        self._con.row_factory = sqlite3.Row
        colunas = ", ".join(f'"{c}"' for c in METADADOS[1:] + COLUNAS)
        with self._lock, self._con:
            self._con.execute(f'CREATE TABLE IF NOT EXISTS sessoes ("sessao_id" TEXT PRIMARY KEY, {colunas})')
            # Migração simples: bancos criados por versões anteriores ganham as colunas novas.
            existentes = {linha[1] for linha in self._con.execute("PRAGMA table_info(sessoes)")}
            for coluna in METADADOS[1:] + COLUNAS:
                if coluna not in existentes:
                    self._con.execute(f'ALTER TABLE sessoes ADD COLUMN "{coluna}"')

    @staticmethod
    def _agora():
        return datetime.now(timezone.utc).isoformat()

    def criar(self, sessao_id: str, dados: dict) -> None:
        linha = {**dados, "sessao_id": sessao_id, "criada_em": self._agora(), "atualizada_em": self._agora()}
        cols = ", ".join(f'"{c}"' for c in linha)
        with self._lock, self._con:
            self._con.execute(f"INSERT INTO sessoes ({cols}) VALUES ({', '.join('?' * len(linha))})", list(linha.values()))

    def atualizar(self, sessao_id: str, dados: dict) -> None:
        dados = {**dados, "atualizada_em": self._agora()}
        sets = ", ".join(f'"{c}" = ?' for c in dados)
        with self._lock, self._con:
            self._con.execute(f"UPDATE sessoes SET {sets} WHERE sessao_id = ?", [*dados.values(), sessao_id])

    def feedbacks_pendentes(self, cliente_id: str) -> list[dict]:
        """Sessões do cliente que seguiram com a transferência e ainda não viram o pop-up."""
        with self._lock:
            linhas = self._con.execute(
                """SELECT * FROM sessoes
                   WHERE cliente_id = ? AND status = 'concluida' AND decisao_cliente = 'continuar'
                     AND feedback_exibido_em IS NULL
                   ORDER BY concluida_em""",
                (cliente_id,),
            ).fetchall()
        return [dict(linha) for linha in linhas]

    def obter(self, sessao_id: str) -> dict | None:
        with self._lock:
            linha = self._con.execute("SELECT * FROM sessoes WHERE sessao_id = ?", (sessao_id,)).fetchone()
        return dict(linha) if linha else None
