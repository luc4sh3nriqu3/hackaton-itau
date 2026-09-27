// Ligação entre a API e o pop-up de feedback (feedback-popup.js).
// Depende de triagem.js (buscarFeedbacksPendentes, marcarFeedbackExibido, enviarFeedback).
//
// Fluxo: busca as transações pendentes do cliente → pega a mais antiga → avisa a API que
// o pop-up foi exibido (assim ela não volta a aparecer) → mostra o pop-up → envia a resposta.
// Qualquer falha de rede é ignorada: o feedback nunca pode atrapalhar o uso do app.

async function verificarFeedbackPendente() {
  let pendentes;
  try {
    pendentes = await buscarFeedbacksPendentes();
  } catch (erro) {
    console.warn("Feedback: não foi possível buscar pendências", erro);
    return;
  }
  const item = pendentes[0];
  if (!item) return;

  await marcarFeedbackExibido(item.sessao_id).catch(() => null);
  mostrarPopupFeedback({
    descricao: item.descricao_exibicao || "Pix que você fez",
    aoResponder: (resposta) =>
      enviarFeedback(item.sessao_id, resposta).catch((erro) => console.warn("Feedback: falha ao enviar", erro)),
  });
}
