"""Carrega e valida o banco de perguntas (dados/perguntas.json)."""
import json
import math
from dataclasses import dataclass, field
from functools import lru_cache

from .config import ARQUIVO_PERGUNTAS

DIMENSOES = ["P1", "P2", "P3", "P4", "P5", "P6", "P7"]


@dataclass(frozen=True)
class Alternativa:
    id: str
    texto: str
    multiplicador: float
    protetora: bool
    coacao: bool
    tipos: tuple[str, ...] = ()


@dataclass(frozen=True)
class Pergunta:
    id: str
    dimensao: str
    faceta: str
    texto_didatico: str
    pergunta: str
    alternativas: tuple[Alternativa, ...]

    def alternativa(self, alternativa_id: str) -> Alternativa:
        for alt in self.alternativas:
            if alt.id == alternativa_id:
                return alt
        raise KeyError(alternativa_id)

    def publica(self) -> dict:
        """Representação enviada ao cliente (sem multiplicadores nem flags internas)."""
        return {
            "id": self.id,
            "dimensao": self.dimensao,
            "faceta": self.faceta,
            "texto_didatico": self.texto_didatico,
            "pergunta": self.pergunta,
            "alternativas": [{"id": a.id, "texto": a.texto} for a in self.alternativas],
        }


@dataclass(frozen=True)
class Banco:
    versao: str
    dimensoes: dict
    perguntas: tuple[Pergunta, ...]
    por_id: dict = field(repr=False)

    def amplitude_log(self, dimensao: str) -> float:
        d = self.dimensoes[dimensao]
        return math.log(d["mult_max"] / d["mult_min"])

    def da_dimensao(self, dimensao: str) -> list[Pergunta]:
        return [p for p in self.perguntas if p.dimensao == dimensao]


def _validar(banco: Banco) -> None:
    assert 28 <= len(banco.perguntas) <= 35, "banco deve ter entre 28 e 35 perguntas"
    assert len(banco.por_id) == len(banco.perguntas), "ids de pergunta duplicados"
    for p in banco.perguntas:
        faixa = banco.dimensoes[p.dimensao]
        assert 3 <= len(p.alternativas) <= 6, f"{p.id}: precisa de 3 a 6 alternativas"
        for a in p.alternativas:
            assert faixa["mult_min"] <= a.multiplicador <= faixa["mult_max"], (
                f"{p.id}/{a.id}: multiplicador {a.multiplicador} fora da faixa de {p.dimensao}"
            )


@lru_cache(maxsize=1)
def carregar_banco() -> Banco:
    bruto = json.loads(ARQUIVO_PERGUNTAS.read_text(encoding="utf-8"))
    perguntas = tuple(
        Pergunta(
            id=p["id"],
            dimensao=p["dimensao"],
            faceta=p["faceta"],
            texto_didatico=p["texto_didatico"],
            pergunta=p["pergunta"],
            alternativas=tuple(
                Alternativa(
                    id=a["id"],
                    texto=a["texto"],
                    multiplicador=float(a["multiplicador"]),
                    protetora=bool(a["protetora"]),
                    coacao=bool(a["coacao"]),
                    tipos=tuple(a.get("tipos", [])),
                )
                for a in p["alternativas"]
            ),
        )
        for p in bruto["perguntas"]
    )
    banco = Banco(
        versao=bruto["versao"],
        dimensoes=bruto["dimensoes"],
        perguntas=perguntas,
        por_id={p.id: p for p in perguntas},
    )
    _validar(banco)
    return banco
