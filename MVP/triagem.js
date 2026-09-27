// Integração com a API de triagem educativa de golpes do Pix (servico/).
// O MVP consome a mesma API pública que qualquer outro sistema usaria.

const TRIAGEM_API_URL = "http://localhost:8000";
const TRIAGEM_API_KEY = "demo-mvp-key"; // protótipo: em produção a chave ficaria num backend, não no navegador

// Acima deste score inicial a confirmação abre o alerta e oferece a avaliação.
const LIMIAR_ALERTA = 0.65;

// ---------------------------------------------------------------------------
// PLACEHOLDER — modelo de detecção de origem (fora do escopo deste projeto)
//
// No mundo real, o Bloco 1 (sinais da transação + score_inicial_modelo_base) vem do
// modelo antifraude do banco. Como ele não existe no MVP, `montarBloco1` simula esses
// campos com uma heurística leve sobre valor, destinatário e horário, espelhando
// `contribuicoes_risco` de servico/triagem/gerador_dataset.py.
//
// Para plugar o modelo real, troque apenas o corpo de `montarBloco1` por uma chamada a
// ele, mantendo o formato do objeto retornado (é o corpo de POST /v1/sessoes).
// ---------------------------------------------------------------------------
const PERFIL_SIMULADO = { valorMedio: 250 }; // média histórica fictícia do cliente, em R$
const CHAVES_CONHECIDAS = ["(12) 9 9777-4728", "felipe.kenji@email.com"]; // contatos de destinatario.html

const DESCRICAO_FATOR = {
  valor_atipico: "valor acima do padrão do cliente",
  destinatario_novo_ou_desconhecido: "destinatário novo",
  dispositivo_nao_reconhecido: "dispositivo não reconhecido",
  velocidade_digitacao_atipica: "digitação atípica (possível acesso remoto)",
  horario_incomum: "horário incomum",
  chave_pix_recente: "chave Pix cadastrada recentemente",
  volume_transacoes_24h_alto: "muitas transações nas últimas 24h",
};

function tipoDaChave(chave) {
  const digitos = chave.replace(/\D/g, "");
  if (chave.includes("@")) return "email";
  if (/^\(?\d{2}\)?\s?9/.test(chave.trim()) && digitos.length >= 10 && digitos.length <= 11) return "telefone";
  if (digitos.length === 11 && /^[\d.\-\s]+$/.test(chave)) return "cpf";
  return "aleatoria";
}

function hashSimples(texto) {
  let h = 0;
  for (const c of texto) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return h.toString(16).padStart(8, "0");
}

function montarBloco1(dados) {
  const agora = new Date();
  const valor = dados.valor / 100;
  const destinatarioNovo = !CHAVES_CONHECIDAS.includes(dados.chavePix);
  const idadeChave = destinatarioNovo ? 5 : 700;
  const horarioIncomum = agora.getHours() < 6 || agora.getHours() >= 22;
  const sinais = { dispositivoReconhecido: true, velocidadeAtipica: false, transacoes24h: 1 };

  const redondo = valor >= 200 && valor % 100 === 0 ? 1 : 0;
  const contrib = {
    valor_atipico: Math.max(0, Math.log(valor / PERFIL_SIMULADO.valorMedio)) * 0.8 + 0.3 * redondo,
    destinatario_novo_ou_desconhecido: destinatarioNovo ? 0.9 : 0,
    dispositivo_nao_reconhecido: sinais.dispositivoReconhecido ? 0 : 1.4,
    velocidade_digitacao_atipica: sinais.velocidadeAtipica ? 1.2 : 0,
    horario_incomum: horarioIncomum ? 0.9 : 0,
    chave_pix_recente: (idadeChave < 30 ? 1 : 0) + (idadeChave < 7 ? 0.3 : 0),
    volume_transacoes_24h_alto: 0.3 * Math.max(0, sinais.transacoes24h - 3),
  };
  const ordem = Object.keys(contrib).sort((a, b) => contrib[b] - contrib[a]);
  const principal = ordem[0];
  const secundario = contrib[ordem[1]] > 0.3 ? ordem[1] : null;
  const soma = Object.values(contrib).reduce((a, b) => a + b, 0);
  const score = Math.min(0.95, Math.max(0.5, 0.55 + 0.35 / (1 + Math.exp(-(soma - 2.2)))));

  return {
    timestamp_transacao: agora.toISOString(),
    valor_transacao: valor,
    valor_medio_historico_usuario: PERFIL_SIMULADO.valorMedio,
    destinatario_chave_pix_hash: hashSimples(dados.chavePix || dados.nome),
    tipo_chave_pix: tipoDaChave(dados.chavePix || ""),
    destinatario_novo: destinatarioNovo,
    idade_chave_pix_destinatario: idadeChave,
    horario_transacao_incomum: horarioIncomum,
    dispositivo_reconhecido: sinais.dispositivoReconhecido,
    velocidade_digitacao_atipica: sinais.velocidadeAtipica,
    numero_transacoes_conta_24h: sinais.transacoes24h,
    canal_transacao: "app",
    motivo_alerta_modelo_base: DESCRICAO_FATOR[principal] + (secundario ? ` + ${DESCRICAO_FATOR[secundario]}` : ""),
    fator_risco_principal: principal,
    fator_risco_secundario: secundario,
    score_inicial_modelo_base: Math.round(score * 10000) / 10000,
  };
}

// ---------------------------------------------------------------------------
// Cliente da API REST
// ---------------------------------------------------------------------------
async function chamarTriagem(metodo, caminho, corpo) {
  const resposta = await fetch(TRIAGEM_API_URL + caminho, {
    method: metodo,
    headers: { "Content-Type": "application/json", "X-API-Key": TRIAGEM_API_KEY },
    body: corpo ? JSON.stringify(corpo) : undefined,
  });
  if (!resposta.ok) throw new Error(`Triagem ${resposta.status}: ${await resposta.text()}`);
  return resposta.status === 204 ? null : resposta.json();
}

const iniciarSessao = (bloco1) => chamarTriagem("POST", "/v1/sessoes", bloco1);
const enviarResposta = (id, perguntaId, alternativaId) =>
  chamarTriagem("POST", `/v1/sessoes/${id}/respostas`, { pergunta_id: perguntaId, alternativa_id: alternativaId });
const enviarVeredito = (id, veredito) => chamarTriagem("POST", `/v1/sessoes/${id}/veredito`, { veredito_usuario: veredito });
const buscarResultado = (id) => chamarTriagem("GET", `/v1/sessoes/${id}/resultado`);
const registrarDecisao = (id, seguiu) =>
  chamarTriagem("POST", `/v1/sessoes/${id}/decisao`, { usuario_seguiu_recomendacao: seguiu }).catch(() => null);
