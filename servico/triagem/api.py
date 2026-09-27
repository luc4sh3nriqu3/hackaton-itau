"""API REST da triagem educativa de golpes do Pix.

Rodar:  uvicorn triagem.api:app --reload   (a partir de servico/)
Docs:   http://localhost:8000/docs  (OpenAPI/Swagger)

Autenticação: header `X-API-Key` com uma das chaves de TRIAGEM_API_KEYS.
"""
import json
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Literal

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from . import demo, gemini
from .armazenamento import Armazenamento
from .banco_perguntas import carregar_banco
from .classificador import carregar_modelo, nivel_risco
from .config import chaves_api, modo_demo, obter
from .esquema import COLUNAS
from .seletor import TOTAL_PERGUNTAS, SeletorPonderado

FatorRisco = Literal[
    "valor_atipico", "destinatario_novo_ou_desconhecido", "dispositivo_nao_reconhecido",
    "velocidade_digitacao_atipica", "horario_incomum", "chave_pix_recente", "volume_transacoes_24h_alto",
]

app = FastAPI(
    title="Triagem educativa de golpes do Pix",
    version="1.0.0",
    description=(
        "Recebe uma transação Pix já sinalizada por um modelo de detecção, conduz o usuário por "
        "3 perguntas educativas adaptativas e devolve um score refinado com uma explicação "
        "personalizada que convida o cliente a repensar. Depois, se o cliente seguiu com a "
        "transferência, coleta o feedback dele (era golpe ou não) para confirmar desfechos reais. "
        "Se alguma resposta indicar coação física, o fluxo é interrompido e substituído por orientação de segurança."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in obter("TRIAGEM_CORS_ORIGINS").split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)

_cabecalho_chave = APIKeyHeader(name="X-API-Key", auto_error=False)


def autenticar(chave: str | None = Security(_cabecalho_chave)) -> str:
    if not chave or chave not in chaves_api():
        raise HTTPException(401, "X-API-Key ausente ou inválida")
    return chave


@lru_cache(maxsize=1)
def armazenamento() -> Armazenamento:
    return Armazenamento()


def seletor() -> SeletorPonderado:
    return SeletorPonderado(carregar_banco())


# ---------- Schemas ----------

class SituacaoInicial(BaseModel):
    """Bloco 1: sinais da transação vindos do modelo de detecção de origem."""
    id_transacao: str | None = Field(None, description="Gerado se omitido")
    timestamp_transacao: datetime | None = Field(None, description="Agora, se omitido")
    valor_transacao: float = Field(gt=0)
    valor_medio_historico_usuario: float = Field(gt=0)
    desvio_valor_padrao: float | None = Field(None, description="(valor - média) / média; calculado se omitido")
    destinatario_chave_pix_hash: str
    tipo_chave_pix: Literal["cpf", "email", "telefone", "aleatoria"]
    destinatario_novo: bool
    idade_chave_pix_destinatario: int = Field(ge=0, description="Dias desde o cadastro da chave")
    horario_transacao_incomum: bool
    dispositivo_reconhecido: bool
    velocidade_digitacao_atipica: bool
    numero_transacoes_conta_24h: int = Field(ge=0)
    canal_transacao: Literal["app", "internet_banking"]
    motivo_alerta_modelo_base: str | None = Field(None, max_length=300)
    fator_risco_principal: FatorRisco
    fator_risco_secundario: FatorRisco | None = None
    score_inicial_modelo_base: float = Field(ge=0, le=1)
    cliente_id: str | None = Field(None, max_length=100, description="Quem fez o Pix; usado para buscar feedbacks pendentes")
    nome_destinatario: str | None = Field(
        None, max_length=120, description="Nome de quem recebe o Pix; aparece na pergunta de conferência do modo demo"
    )
    descricao_exibicao: str | None = Field(
        None, max_length=200, description='Texto curto para o pop-up de feedback, ex.: "Pix de R$ 1.000,00 para Lucas"'
    )


class AlternativaPublica(BaseModel):
    id: str
    texto: str


class PerguntaPublica(BaseModel):
    id: str
    dimensao: str
    faceta: str
    texto_didatico: str
    pergunta: str
    alternativas: list[AlternativaPublica]


class Progresso(BaseModel):
    atual: int
    total: int = TOTAL_PERGUNTAS


class RespostaEtapa(BaseModel):
    sessao_id: str
    status: Literal["em_andamento", "concluida", "coacao"]
    pergunta: PerguntaPublica | None = None
    progresso: Progresso
    orientacao_seguranca: str | None = None


class RespostaUsuario(BaseModel):
    pergunta_id: str
    alternativa_id: str


class Topico(BaseModel):
    tom: Literal["alerta", "atencao", "ok"] = Field(description="Define a cor: alerta (vermelho), atencao (laranja), ok (verde)")
    texto: str = Field(description="Trechos entre **asteriscos** devem ser destacados na cor do tom")


class Resultado(BaseModel):
    sessao_id: str
    status: Literal["concluida", "coacao"]
    sinalizador_coacao_fisica: bool
    score_inicial_modelo_base: float
    score_refinado: float | None = Field(None, description="Probabilidade de golpe, com piso 0,15 e teto 0,98")
    nivel_risco: Literal["baixo", "moderado", "alto"] | None = None
    pontuacao_reconhecimento_padroes: int | None = None
    explicacao_gerada: str
    explicacao_topicos: list[Topico] | None = Field(
        None, description="Texto final em tópicos (modo demo). Sem tópicos, exiba explicacao_gerada em parágrafos"
    )
    fonte_explicacao: Literal["gemini", "template", "seguranca", "demo"]
    versao_modelo: str | None = None


class Decisao(BaseModel):
    decisao: Literal["continuar", "cancelar"] = Field(description="O que o cliente fez depois do chat")


class Feedback(BaseModel):
    feedback_cliente: Literal["golpe", "nao_golpe", "sem_resposta"] = Field(
        description='"golpe" (quer falar com o suporte), "nao_golpe" (era legítima) ou "sem_resposta" (fechou sem responder)'
    )


class FeedbackPendente(BaseModel):
    sessao_id: str
    descricao_exibicao: str | None
    concluida_em: str


# ---------- Auxiliares ----------

def _carregar(sessao_id: str) -> dict:
    sessao = armazenamento().obter(sessao_id)
    if not sessao:
        raise HTTPException(404, "Sessão não encontrada")
    return sessao


def _perguntas_feitas(sessao: dict) -> list[str]:
    return [sessao[f"pergunta_{n}_id"] for n in range(1, TOTAL_PERGUNTAS + 1) if sessao.get(f"pergunta_{n}_id")]


def _respondidas(sessao: dict) -> int:
    return sum(1 for n in range(1, TOTAL_PERGUNTAS + 1) if sessao.get(f"pergunta_{n}_resposta"))


def _demo(sessao: dict) -> bool:
    return sessao.get("modo") == "demo"


def _alternativa(sessao: dict, pergunta_id: str, alternativa_id: str):
    """(multiplicador, coacao) da alternativa escolhida; KeyError se não existir."""
    if _demo(sessao):
        demo.alternativa(pergunta_id, alternativa_id)
        return None, False
    alt = carregar_banco().por_id[pergunta_id].alternativa(alternativa_id)
    return alt.multiplicador, alt.coacao


def _registrar_pergunta(sessao: dict, n: int) -> tuple[dict, PerguntaPublica]:
    if _demo(sessao):
        pergunta = demo.pergunta(n, sessao.get("nome_destinatario"))
        campos = {f"pergunta_{n}_id": pergunta["id"], f"pergunta_{n}_dimensao": pergunta["dimensao"]}
        return campos, PerguntaPublica(**pergunta)
    pergunta = seletor().proxima_pergunta(
        _perguntas_feitas(sessao), sessao["fator_risco_principal"], sessao["fator_risco_secundario"]
    )
    campos = {f"pergunta_{n}_id": pergunta.id, f"pergunta_{n}_dimensao": pergunta.dimensao}
    return campos, PerguntaPublica(**pergunta.publica())


def _perguntas_respostas(sessao: dict) -> list[dict]:
    banco = carregar_banco()
    saida = []
    for n in range(1, TOTAL_PERGUNTAS + 1):
        pid, resp = sessao.get(f"pergunta_{n}_id"), sessao.get(f"pergunta_{n}_resposta")
        if pid and resp:
            pergunta = banco.por_id[pid]
            alt = pergunta.alternativa(resp)
            saida.append({
                "pergunta": pergunta.pergunta, "resposta": alt.texto,
                "multiplicador": alt.multiplicador, "protetora": alt.protetora,
            })
    return saida


def _resultado(sessao: dict) -> Resultado:
    coacao = bool(sessao["sinalizador_coacao_fisica"])
    return Resultado(
        sessao_id=sessao["sessao_id"],
        status=sessao["status"],
        sinalizador_coacao_fisica=coacao,
        score_inicial_modelo_base=sessao["score_inicial_modelo_base"],
        score_refinado=sessao["score_refinado"],
        nivel_risco=sessao["nivel_risco"],
        pontuacao_reconhecimento_padroes=sessao["pontuacao_reconhecimento_padroes"],
        explicacao_gerada=sessao["explicacao_gerada"],
        explicacao_topicos=json.loads(sessao["explicacao_topicos"]) if sessao.get("explicacao_topicos") else None,
        fonte_explicacao=sessao["fonte_explicacao"],
        versao_modelo=sessao["versao_modelo"],
    )


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _concluir_demo(sessao_id: str, sessao: dict) -> None:
    """Modo demo: resultado mockado a partir das respostas, sem classificador nem Gemini."""
    respostas = [(sessao[f"pergunta_{n}_id"], sessao[f"pergunta_{n}_resposta"]) for n in range(1, TOTAL_PERGUNTAS + 1)]
    r = demo.resultado(respostas)
    armazenamento().atualizar(sessao_id, {
        "status": "concluida",
        "concluida_em": _agora().isoformat(),
        "score_refinado": r["score_refinado"],
        "nivel_risco": r["nivel_risco"],
        "explicacao_gerada": r["texto"],
        "explicacao_topicos": json.dumps(r["topicos"], ensure_ascii=False),
        "fonte_explicacao": "demo",
        "versao_modelo": demo.VERSAO_MODELO_DEMO,
    })


def _concluir(sessao_id: str, sessao: dict) -> None:
    """Calcula score e explicação a partir das 3 respostas e encerra a sessão."""
    if _demo(sessao):
        return _concluir_demo(sessao_id, sessao)
    qa = _perguntas_respostas(sessao)
    sessao["pontuacao_reconhecimento_padroes"] = sum(q["protetora"] for q in qa)

    modelo = carregar_modelo()
    linha = pd.DataFrame([{c: sessao.get(c) for c in COLUNAS}])
    prob, exibido = modelo.prever_sessoes(linha)
    prob, score = float(prob[0]), round(float(exibido[0]), 4)
    nivel = nivel_risco(prob, modelo.limiar)

    texto, fonte = gemini.gerar_explicacao(sessao, qa, nivel)
    armazenamento().atualizar(sessao_id, {
        "status": "concluida",
        "concluida_em": _agora().isoformat(),
        "pontuacao_reconhecimento_padroes": sessao["pontuacao_reconhecimento_padroes"],
        "score_refinado": score,
        "prob_interna": prob,
        "nivel_risco": nivel,
        "explicacao_gerada": texto,
        "fonte_explicacao": fonte,
        "versao_modelo": modelo.versao,
    })


# ---------- Endpoints ----------

@app.post("/v1/sessoes", response_model=RespostaEtapa, status_code=201, tags=["sessões"])
def criar_sessao(situacao: SituacaoInicial, _: str = Depends(autenticar)):
    """Inicia a triagem com os sinais da transação e devolve a primeira pergunta."""
    dados = situacao.model_dump()
    dados["id_transacao"] = dados["id_transacao"] or str(uuid.uuid4())
    dados["timestamp_transacao"] = (dados["timestamp_transacao"] or datetime.now(timezone.utc)).isoformat()
    if dados["desvio_valor_padrao"] is None:
        media = dados["valor_medio_historico_usuario"]
        dados["desvio_valor_padrao"] = round((dados["valor_transacao"] - media) / media, 4)
    dados["sinalizador_coacao_fisica"] = False
    dados["feedback_cliente"] = "sem_resposta"  # até o cliente responder o pop-up
    dados["modo"] = "demo" if modo_demo() else "real"  # fixado na criação: trocar o .env não quebra sessões em andamento

    sessao_id = str(uuid.uuid4())
    campos, pergunta = _registrar_pergunta(dados, 1)
    armazenamento().criar(sessao_id, {
        **dados, **campos, "status": "em_andamento",
        "versao_banco_perguntas": demo.versao() if dados["modo"] == "demo" else carregar_banco().versao,
    })
    return RespostaEtapa(sessao_id=sessao_id, status="em_andamento", pergunta=pergunta, progresso=Progresso(atual=1))


@app.post("/v1/sessoes/{sessao_id}/respostas", response_model=RespostaEtapa, tags=["sessões"])
def responder(sessao_id: str, resposta: RespostaUsuario, _: str = Depends(autenticar)):
    """Registra a resposta da pergunta atual e devolve a próxima.

    Após a última pergunta, calcula o score e a explicação e devolve `status = "concluida"`;
    o resultado sai em `GET /resultado`.

    Se a alternativa indicar coação física, o fluxo é encerrado com `status = "coacao"`
    e `orientacao_seguranca`.
    """
    sessao = _carregar(sessao_id)
    if sessao["status"] != "em_andamento":
        raise HTTPException(409, f"Sessão não aceita respostas (status: {sessao['status']})")
    n = _respondidas(sessao) + 1
    esperada = sessao[f"pergunta_{n}_id"]
    if resposta.pergunta_id != esperada:
        raise HTTPException(409, f"Pergunta atual é {esperada}")
    try:
        multiplicador, coacao = _alternativa(sessao, esperada, resposta.alternativa_id)
    except KeyError:
        raise HTTPException(422, "Alternativa inválida para esta pergunta")

    campos = {f"pergunta_{n}_resposta": resposta.alternativa_id, f"pergunta_{n}_multiplicador": multiplicador}

    if coacao:
        texto, fonte = gemini.gerar_explicacao(sessao, [], None, coacao=True)
        armazenamento().atualizar(sessao_id, {
            **campos, "status": "coacao", "sinalizador_coacao_fisica": True,
            "explicacao_gerada": texto, "fonte_explicacao": fonte,
        })
        return RespostaEtapa(
            sessao_id=sessao_id, status="coacao", progresso=Progresso(atual=n), orientacao_seguranca=texto
        )

    if n == TOTAL_PERGUNTAS:
        armazenamento().atualizar(sessao_id, campos)
        _concluir(sessao_id, {**sessao, **campos})
        return RespostaEtapa(sessao_id=sessao_id, status="concluida", progresso=Progresso(atual=n))

    sessao.update(campos)
    proxima, pergunta = _registrar_pergunta(sessao, n + 1)
    armazenamento().atualizar(sessao_id, {**campos, **proxima})
    return RespostaEtapa(sessao_id=sessao_id, status="em_andamento", pergunta=pergunta, progresso=Progresso(atual=n + 1))


@app.get("/v1/sessoes/{sessao_id}/resultado", response_model=Resultado, tags=["sessões"])
def obter_resultado(sessao_id: str, _: str = Depends(autenticar)):
    """Devolve score refinado e explicação (ou a orientação de segurança, em caso de coação)."""
    sessao = _carregar(sessao_id)
    if sessao["status"] not in ("concluida", "coacao"):
        raise HTTPException(409, f"Resultado ainda não disponível (status: {sessao['status']})")
    return _resultado(sessao)


@app.post("/v1/sessoes/{sessao_id}/decisao", status_code=204, tags=["decisão e feedback"])
def registrar_decisao(sessao_id: str, decisao: Decisao, _: str = Depends(autenticar)):
    """Registra se o cliente continuou ou cancelou a transferência depois do chat.

    Só sessões com `continuar` recebem depois o pop-up de feedback.
    """
    sessao = _carregar(sessao_id)
    if sessao["status"] != "concluida":
        raise HTTPException(409, f"Sessão não concluída (status: {sessao['status']})")
    arriscado = sessao["nivel_risco"] in ("moderado", "alto")
    armazenamento().atualizar(sessao_id, {
        "decisao_cliente": decisao.decisao,
        "usuario_seguiu_recomendacao": (decisao.decisao == "cancelar") == arriscado,
    })


@app.get("/v1/feedbacks/pendentes", response_model=list[FeedbackPendente], tags=["decisão e feedback"])
def feedbacks_pendentes(cliente_id: str = Query(..., description="Mesmo cliente_id enviado ao criar a sessão"),
                        _: str = Depends(autenticar)):
    """Transações que o cliente continuou e sobre as quais ainda não mostramos o pop-up de feedback.

    Só entram sessões concluídas há pelo menos `FEEDBACK_ATRASO_MINUTOS` (0 na demo). Mais antiga primeiro.
    """
    limite = _agora() - timedelta(minutes=float(obter("FEEDBACK_ATRASO_MINUTOS")))
    return [
        FeedbackPendente(sessao_id=s["sessao_id"], descricao_exibicao=s["descricao_exibicao"], concluida_em=s["concluida_em"])
        for s in armazenamento().feedbacks_pendentes(cliente_id)
        if datetime.fromisoformat(s["concluida_em"]) <= limite
    ]


@app.post("/v1/sessoes/{sessao_id}/feedback/exibido", status_code=204, tags=["decisão e feedback"])
def marcar_feedback_exibido(sessao_id: str, _: str = Depends(autenticar)):
    """Marca que o pop-up foi mostrado: a sessão sai de /pendentes e não é perguntada de novo."""
    _carregar(sessao_id)
    armazenamento().atualizar(sessao_id, {"feedback_exibido_em": _agora().isoformat()})


@app.post("/v1/sessoes/{sessao_id}/feedback", status_code=204, tags=["decisão e feedback"])
def registrar_feedback(sessao_id: str, feedback: Feedback, _: str = Depends(autenticar)):
    """Grava a resposta do cliente no pop-up. Fechar sem responder envia `sem_resposta`."""
    sessao = _carregar(sessao_id)
    armazenamento().atualizar(sessao_id, {
        "feedback_cliente": feedback.feedback_cliente,
        "feedback_respondido_em": _agora().isoformat(),
        "feedback_exibido_em": sessao["feedback_exibido_em"] or _agora().isoformat(),
    })


@app.get("/saude", tags=["infra"])
def saude():
    modelo = carregar_modelo()
    return {
        "ok": True,
        "versao_modelo": modelo.versao,
        "versao_banco_perguntas": carregar_banco().versao,
        "gemini_configurado": bool(obter("GEMINI_API_KEY")),
        "modo_demo": modo_demo(),
    }
