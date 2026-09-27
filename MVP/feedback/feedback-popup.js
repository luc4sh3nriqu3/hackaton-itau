// Pop-up de feedback pós-transação: SÓ a interface. Não chama a API.
//
// Contrato (mantenha ao trocar por outra tela):
//   mostrarPopupFeedback({ descricao, aoResponder })
//     descricao    texto da transação, ex.: "Pix de R$ 1.000,00 para Lucas"
//     aoResponder  chamada UMA vez com "golpe" | "nao_golpe" | "sem_resposta"
//                  (✕, Esc ou clique fora contam como "sem_resposta")
// Quem busca as pendências e envia a resposta para a API é feedback.js.
// Os dois botões têm o mesmo peso visual de propósito: destacar um deles enviesaria o feedback.

function mostrarPopupFeedback({ descricao, aoResponder }) {
  const alvo = document.querySelector(".phone") || document.body;
  let respondido = false;

  const overlay = document.createElement("div");
  overlay.className = "fb-overlay";
  overlay.innerHTML = `
    <div class="fb-cartao" role="dialog" aria-modal="true" aria-labelledby="fb-titulo">
      <button class="fb-fechar" aria-label="Fechar">✕</button>
      <div class="fb-icone" aria-hidden="true">
        <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6l8-3z"/><path d="M12 8v5"/><circle cx="12" cy="16.2" r=".6" fill="currentColor"/></svg>
      </div>
      <h2 class="fb-titulo" id="fb-titulo">Uma pergunta rápida</h2>
      <p class="fb-texto"></p>
      <div class="fb-acoes">
        <button class="fb-botao" data-resposta="golpe">Sim, gostaria de entrar em contato com o suporte</button>
        <button class="fb-botao" data-resposta="nao_golpe">Não, era uma transação legítima</button>
      </div>
    </div>`;
  overlay.querySelector(".fb-texto").textContent = `Aquele ${descricao} era golpe?`;
  alvo.appendChild(overlay);
  requestAnimationFrame(() => overlay.classList.add("fb-visivel"));

  function fechar() {
    overlay.classList.remove("fb-visivel");
    document.removeEventListener("keydown", aoTeclar);
    setTimeout(() => overlay.remove(), 200);
  }

  function responder(resposta) {
    if (respondido) return;
    respondido = true;
    aoResponder(resposta);
    if (resposta === "golpe") mostrarConfirmacaoSuporte();
    else fechar();
  }

  // Depois do "Sim": próximos passos, no mesmo cartão.
  function mostrarConfirmacaoSuporte() {
    overlay.querySelector(".fb-titulo").textContent = "Vamos te ajudar";
    overlay.querySelector(".fb-texto").textContent =
      "Obrigado por avisar. Nosso time de suporte vai entrar em contato. Se preferir falar agora, ligue para o " +
      "número que está no verso do seu cartão: dá para pedir a devolução do Pix pelo MED (Mecanismo Especial de Devolução).";
    overlay.querySelector(".fb-acoes").innerHTML = '<button class="fb-botao fb-principal">Entendi</button>';
    overlay.querySelector(".fb-acoes button").addEventListener("click", fechar);
  }

  function aoTeclar(evento) {
    if (evento.key === "Escape") respondido ? fechar() : responder("sem_resposta");
  }

  overlay.querySelectorAll("[data-resposta]").forEach((botao) =>
    botao.addEventListener("click", () => responder(botao.dataset.resposta))
  );
  overlay.querySelector(".fb-fechar").addEventListener("click", () => (respondido ? fechar() : responder("sem_resposta")));
  overlay.addEventListener("click", (evento) => {
    if (evento.target === overlay) respondido ? fechar() : responder("sem_resposta");
  });
  document.addEventListener("keydown", aoTeclar);
  overlay.querySelector("[data-resposta]").focus();
}
