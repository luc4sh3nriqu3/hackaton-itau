// Ligação entre o app e o pop-up de feedback (feedback-popup.js).
// Depende de triagem.js (descreverPix, enviarFeedback).
//
// Versão da demo: o gatilho é a TRANSFERÊNCIA REALIZADA, com ou sem avaliação.
// - comprovante.html chama registrarTransferenciaRealizada(dados): guarda a pendência no navegador.
// - home.html chama verificarFeedbackPendente(): mostra o pop-up uma única vez e apaga a pendência.
// - Transferência cancelada nunca chega ao comprovante, então não gera pop-up.
// Se a transferência passou pela avaliação, a resposta também vai para a API (coluna feedback_cliente).
// Em produção, a pendência viria de GET /v1/feedbacks/pendentes (ver README.md desta pasta).

const CHAVE_FEEDBACK = "feedback-pendente";

function registrarTransferenciaRealizada(dados) {
  try {
    localStorage.setItem(
      CHAVE_FEEDBACK,
      JSON.stringify({ descricao: descreverPix(dados), sessaoId: dados.sessaoTriagem || null })
    );
  } catch {
    // navegador sem armazenamento: só não mostra o pop-up
  }
}

function verificarFeedbackPendente() {
  let pendente = null;
  try {
    pendente = JSON.parse(localStorage.getItem(CHAVE_FEEDBACK) || "null");
    localStorage.removeItem(CHAVE_FEEDBACK); // aparece uma única vez
  } catch {
    return;
  }
  if (!pendente) return;

  mostrarPopupFeedback({
    descricao: pendente.descricao || "Pix que você fez",
    aoResponder: (resposta) => {
      if (pendente.sessaoId) {
        enviarFeedback(pendente.sessaoId, resposta).catch((erro) => console.warn("Feedback: falha ao enviar", erro));
      }
    },
  });
}
