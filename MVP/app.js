const CHAVE = "transferencia-itau";

const padrao = {
  nome: "",
  chavePix: "",
  cpf: "",
  instituicao: "",
  valor: 0,
  origem: "",
  data: "Hoje",
  repetir: "Não",
  mensagem: "",
};

function lerTransferencia() {
  try {
    return { ...padrao, ...JSON.parse(sessionStorage.getItem(CHAVE) || "{}") };
  } catch {
    return { ...padrao };
  }
}

function salvarTransferencia(dados) {
  sessionStorage.setItem(CHAVE, JSON.stringify({ ...lerTransferencia(), ...dados }));
}

function limparTransferencia() {
  sessionStorage.removeItem(CHAVE);
}

function formatarMoeda(centavos) {
  return (centavos / 100).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function mostrarCarregando() {
  let carregando = document.querySelector(".carregando");
  if (!carregando) {
    carregando = document.createElement("div");
    carregando.className = "carregando";
    carregando.innerHTML = '<span class="giro"></span>';
    (document.querySelector(".phone") || document.body).appendChild(carregando);
  }
  requestAnimationFrame(() => carregando.classList.add("visivel"));
}

function irPara(pagina, espera = 550) {
  mostrarCarregando();
  setTimeout(() => (window.location.href = pagina), espera);
}

function voltar() {
  if (history.length > 1) history.back();
  else irPara("home.html");
}

function relogio() {
  const agora = new Date();
  const texto = `${String(agora.getHours()).padStart(2, "0")}:${String(agora.getMinutes()).padStart(2, "0")}`;
  document.querySelectorAll("[data-relogio]").forEach((el) => (el.textContent = texto));
}

const CHAVE_SOM = "som-itau";

function somAtivo() {
  return localStorage.getItem(CHAVE_SOM) === "1";
}

function falar(texto) {
  if (!somAtivo() || !window.speechSynthesis || !texto) return;
  const fala = new SpeechSynthesisUtterance(texto);
  fala.lang = "pt-BR";
  fala.rate = 1.05;
  window.speechSynthesis.speak(fala);
}

const ICONE_SOM_LIGADO =
  '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9v6h3.5L13 19V5L7.5 9H4z"/><path d="M16.5 8.8a4.5 4.5 0 0 1 0 6.4"/><path d="M19 6.3a8 8 0 0 1 0 11.4"/></svg>';

const ICONE_SOM_DESLIGADO =
  '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9v6h3.5L13 19V5L7.5 9H4z"/><path d="M17 10l4 4"/><path d="M21 10l-4 4"/></svg>';

// Botão de som compartilhado: guarda a preferência e, quando ligado, lê o texto da tela.
function montarBotaoSom(botao, aoLigar) {
  function pintar() {
    const ligado = somAtivo();
    botao.innerHTML = ligado ? ICONE_SOM_LIGADO : ICONE_SOM_DESLIGADO;
    botao.classList.toggle("ativo", ligado);
    botao.setAttribute("aria-pressed", String(ligado));
    botao.setAttribute("aria-label", ligado ? "Desativar som" : "Ativar som");
  }

  botao.addEventListener("click", () => {
    const ligado = !somAtivo();
    localStorage.setItem(CHAVE_SOM, ligado ? "1" : "0");
    pintar();
    if (!ligado) window.speechSynthesis && window.speechSynthesis.cancel();
    else if (aoLigar) aoLigar();
  });

  pintar();
  if (somAtivo() && aoLigar) aoLigar();
}

function montarTeclado(alvo, aoDigitar) {
  const letras = ["", "", "ABC", "DEF", "GHI", "JKL", "MNO", "PQRS", "TUV", "WXYZ"];
  const teclas = [];
  for (let n = 1; n <= 9; n++) teclas.push({ n: String(n), letras: letras[n] });
  teclas.push({ vazia: true }, { n: "0", letras: "" }, { apagar: true });

  alvo.innerHTML = teclas
    .map((t) => {
      if (t.vazia) return `<button class="tecla vazia" tabindex="-1" aria-hidden="true"></button>`;
      if (t.apagar) return `<button class="tecla" data-tecla="apagar" aria-label="Apagar">⌫</button>`;
      return `<button class="tecla" data-tecla="${t.n}">${t.n}${t.letras ? `<small>${t.letras}</small>` : "<small>&nbsp;</small>"}</button>`;
    })
    .join("");

  alvo.addEventListener("click", (evento) => {
    const botao = evento.target.closest("[data-tecla]");
    if (botao) aoDigitar(botao.dataset.tecla);
  });

  document.addEventListener("keydown", (evento) => {
    if (/^[0-9]$/.test(evento.key)) aoDigitar(evento.key);
    if (evento.key === "Backspace") aoDigitar("apagar");
  });
}

document.addEventListener("DOMContentLoaded", () => {
  relogio();
  document.querySelectorAll("[data-ir]").forEach((el) =>
    el.addEventListener("click", () => irPara(el.dataset.ir))
  );
  setInterval(relogio, 20000);
  document.querySelectorAll("[data-voltar]").forEach((botao) => botao.addEventListener("click", voltar));
});
