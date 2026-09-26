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

function irPara(pagina) {
  window.location.href = pagina;
}

function voltar() {
  if (history.length > 1) history.back();
  else irPara("index.html");
}

function relogio() {
  const agora = new Date();
  const texto = `${String(agora.getHours()).padStart(2, "0")}:${String(agora.getMinutes()).padStart(2, "0")}`;
  document.querySelectorAll("[data-relogio]").forEach((el) => (el.textContent = texto));
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
  setInterval(relogio, 20000);
  document.querySelectorAll("[data-voltar]").forEach((botao) => botao.addEventListener("click", voltar));
});
