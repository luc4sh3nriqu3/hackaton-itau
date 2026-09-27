"""Esquema das colunas de uma sessão (dataset sintético e log de produção).

18 do Bloco 1 + 4 por pergunta + sinalizador de coação + 7 do Bloco 3
(com 3 perguntas: 18 + 12 + 1 + 7 = 38 colunas).
"""
from .seletor import TOTAL_PERGUNTAS

BLOCO1 = [
    "id_transacao",
    "timestamp_transacao",
    "valor_transacao",
    "valor_medio_historico_usuario",
    "desvio_valor_padrao",
    "destinatario_chave_pix_hash",
    "tipo_chave_pix",
    "destinatario_novo",
    "idade_chave_pix_destinatario",
    "horario_transacao_incomum",
    "dispositivo_reconhecido",
    "velocidade_digitacao_atipica",
    "numero_transacoes_conta_24h",
    "canal_transacao",
    "motivo_alerta_modelo_base",
    "fator_risco_principal",
    "fator_risco_secundario",
    "score_inicial_modelo_base",
]

BLOCO2 = [
    f"pergunta_{n}_{campo}"
    for n in range(1, TOTAL_PERGUNTAS + 1)
    for campo in ("id", "dimensao", "resposta", "multiplicador")
] + ["sinalizador_coacao_fisica"]

BLOCO3 = [
    "feedback_cliente",  # resposta do pop-up pós-transação: golpe | nao_golpe | sem_resposta
    "pontuacao_reconhecimento_padroes",
    "score_refinado",
    "rotulo_real_golpe",
    "rotulo_tipo_golpe",
    "explicacao_gerada",
    "usuario_seguiu_recomendacao",
]

COLUNAS = BLOCO1 + BLOCO2 + BLOCO3
assert len(COLUNAS) == 18 + 4 * TOTAL_PERGUNTAS + 1 + 7, len(COLUNAS)

TIPOS_CHAVE = ["cpf", "email", "telefone", "aleatoria"]
CANAIS = ["app", "internet_banking"]
FEEDBACKS = ["golpe", "nao_golpe", "sem_resposta"]
TIPOS_GOLPE = [
    "falsa_central",
    "mao_fantasma",
    "whatsapp_clonado",
    "falsa_taxa",
    "sequestro_pix",
    "venda_falsa",
    "outro",
]
