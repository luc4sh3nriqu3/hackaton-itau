"""Geração do texto explicativo final (Gemini, com fallback local por template).

- A chave é lida de GEMINI_API_KEY (servico/.env ou ambiente) a CADA chamada: basta
  colocá-la no .env e a próxima sessão já usa o Gemini, sem reiniciar nada.
- Sem chave, com erro ou timeout, cai no template local (sempre personalizado com as
  respostas do usuário), e o campo `fonte` indica qual foi usado.
- Coação física: não gera texto educativo. Devolve orientação de segurança fixa e
  revisada — num momento de risco à integridade física, o texto não deve depender de
  rede nem de variação de um modelo generativo.
"""
import logging

from .config import obter

log = logging.getLogger(__name__)

ORIENTACAO_COACAO = (
    "Sua segurança vem antes de qualquer valor. Se há alguém te ameaçando agora, não reaja "
    "e não tente enfrentar a pessoa. Assim que puder fazer isso com segurança, ligue 190 "
    "(Polícia Militar). Depois, avise o banco pelo número que está no verso do seu cartão "
    "ou pelo app: é possível bloquear a conta e pedir a devolução pelo MED (Mecanismo "
    "Especial de Devolução do Pix). Você não está sozinho e não tem culpa pelo que está acontecendo."
)

# Fecho do texto: convida a uma pausa e a uma checagem, sem ordenar nem assustar.
CONVITE = {
    "alto": "Que tal fazer uma pausa de alguns minutos e confirmar essa história por um canal que você mesmo procure, como o app do banco ou o número antigo da pessoa? Se ainda fizer sentido depois disso, a decisão é sua.",
    "moderado": "Vale tirar uns minutos para confirmar a história por um canal que você mesmo procure, como o app do banco, o site oficial da empresa ou o número antigo da pessoa, antes de seguir.",
    "baixo": "Se quiser, confira com calma o nome do recebedor e a chave Pix antes de confirmar.",
}

INSTRUCAO_SISTEMA = (
    "Você é o assistente de segurança de um app de banco brasileiro. O cliente acabou de responder "
    "3 perguntas sobre um Pix que ele está fazendo. Escreva em português do Brasil, em tom calmo, "
    "acolhedor e nada alarmista, falando diretamente com o cliente (você). O objetivo não é assustar, "
    "e sim ajudar o cliente a repensar com calma antes de concluir. Explique os motivos citando os "
    "sinais concretos que o PRÓPRIO cliente informou nas respostas — nada genérico — e, quando fizer "
    "sentido, por que golpistas costumam agir assim. Não invente fatos que não estão nas respostas. "
    "NUNCA mencione números, porcentagens, probabilidades ou 'nível de risco'. Não use as palavras "
    "'fraude' ou 'golpista' de forma acusatória contra o destinatário. Não use markdown, listas nem "
    "títulos: no máximo 2 parágrafos curtos (até ~100 palavras no total). Não ordene: termine com "
    "um convite gentil para uma pausa e uma checagem por canal oficial, deixando claro que a "
    "decisão é do cliente."
)


def _formatar_qa(perguntas_respostas: list[dict]) -> str:
    return "\n".join(
        f"{i}. {qa['pergunta']} -> {qa['resposta']}" for i, qa in enumerate(perguntas_respostas, 1)
    )


def montar_prompt(situacao: dict, perguntas_respostas: list[dict], nivel: str) -> str:
    return (
        f"Situação da transação: Pix de R$ {situacao['valor_transacao']:.2f}, "
        f"destinatário {'novo' if situacao['destinatario_novo'] else 'já conhecido'}, "
        f"chave do tipo {situacao['tipo_chave_pix']}.\n"
        f"Motivo do alerta inicial: {situacao.get('motivo_alerta_modelo_base') or 'não informado'}.\n"
        f"Perguntas e respostas do cliente:\n{_formatar_qa(perguntas_respostas)}\n"
        f"Avaliação interna (NÃO cite): risco {nivel}.\n"
        f"Termine com este convite, com suas palavras: {CONVITE[nivel]}"
    )


def explicacao_template(perguntas_respostas: list[dict], nivel: str) -> str:
    alertas = sorted((qa for qa in perguntas_respostas if qa["multiplicador"] >= 1.8), key=lambda qa: -qa["multiplicador"])
    bons = [qa for qa in perguntas_respostas if qa["protetora"]]
    partes = []
    if nivel == "baixo" or not alertas:
        partes.append("Pelo que você contou, não apareceram sinais fortes de golpe nessa transferência.")
    else:
        sinais = "; ".join(f"\"{qa['resposta'].rstrip('.')}\"" for qa in alertas[:3])
        partes.append(
            f"Algumas coisas que você contou costumam aparecer em golpes de Pix: {sinais}. "
            "Isso não quer dizer que seja golpe, mas vale olhar com mais calma."
        )
    if bons:
        partes.append(f"Você agiu bem ao responder \"{bons[0]['resposta'].rstrip('.')}\" — esse tipo de cuidado é o que mais protege.")
    partes.append(CONVITE[nivel])
    return " ".join(partes)


def gerar_explicacao(
    situacao: dict, perguntas_respostas: list[dict], nivel: str | None, coacao: bool = False,
) -> tuple[str, str]:
    """Retorna (texto, fonte) com fonte em {"gemini", "template", "seguranca"}."""
    if coacao:
        return ORIENTACAO_COACAO, "seguranca"

    chave = obter("GEMINI_API_KEY")
    if chave:
        # Modelo principal e, se ele estiver fora do ar/sobrecarregado, os de reserva, em ordem.
        reservas = [m.strip() for m in (obter("GEMINI_MODELOS_RESERVA") or "").split(",") if m.strip()]
        for modelo in [obter("GEMINI_MODEL"), *reservas]:
            try:
                from google import genai
                from google.genai import types

                cliente = genai.Client(
                    api_key=chave,
                    http_options=types.HttpOptions(timeout=int(float(obter("GEMINI_TIMEOUT_S")) * 1000)),
                )
                resposta = cliente.models.generate_content(
                    model=modelo,
                    contents=montar_prompt(situacao, perguntas_respostas, nivel),
                    config=types.GenerateContentConfig(
                        system_instruction=INSTRUCAO_SISTEMA,
                        temperature=0.4,
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                    ),
                )
                texto = (resposta.text or "").strip()
                if texto:
                    return texto, "gemini"
            except Exception as erro:  # rede, cota, chave inválida: nunca derruba o fluxo
                log.warning("Falha no Gemini (%s): %s", modelo, erro)
        log.warning("Nenhum modelo Gemini respondeu, usando template")
    return explicacao_template(perguntas_respostas, nivel), "template"
