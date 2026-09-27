"""Relatório de métricas do classificador final (triagem com 3 perguntas).

Uso:  python -m triagem.relatorio      (a partir de servico/, depois de treino.py)

Avalia o modelo salvo em modelos/ no conjunto de TESTE (dados que ele nunca viu) e gera:
- relatorios/metricas.md      relatório completo, com explicação de cada métrica
- relatorios/metricas.json    os mesmos números em formato de máquina
- relatorios/figuras/*.png    matriz de confusão, curvas ROC/PR, calibração, limiar, distribuição
- README.md (raiz)            atualiza a seção entre <!-- METRICAS:INICIO --> e <!-- METRICAS:FIM -->

As métricas usam a probabilidade calibrada sem teto/piso, que é a mesma usada nas
decisões da API; o teto/piso (15%–98%) vale só para o número exibido ao usuário.
Sessões com coação física ficam fora, como no treino (não passam pelo score).
"""
import json
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.ticker import FuncFormatter
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    average_precision_score, brier_score_loss, confusion_matrix, log_loss,
    precision_recall_curve, roc_auc_score, roc_curve,
)

from .classificador import carregar_modelo, nivel_risco
from .config import DADOS_DIR, SERVICO_DIR
from .features import vetorizar
from .seletor import TOTAL_PERGUNTAS
from .treino import _rotulo, _sem_coacao

RELATORIO_DIR = SERVICO_DIR / "relatorios"
FIGURAS_DIR = RELATORIO_DIR / "figuras"
README = SERVICO_DIR.parent / "README.md"
MARCA_INICIO, MARCA_FIM = "<!-- METRICAS:INICIO -->", "<!-- METRICAS:FIM -->"

# Paleta validada (scripts/validate_palette.js da skill de dataviz, modo claro).
AZUL, LARANJA, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
TEXTO, TEXTO_2, GRADE, SUPERFICIE = "#0b0b0b", "#52514e", "#e4e3de", "#fcfcfb"
RAMPA_AZUL = LinearSegmentedColormap.from_list("azul", ["#eef4fc", "#9cc2f0", "#2a78d6", "#123a6b"])


# ---------------------------------------------------------------- métricas

def metricas_no_limiar(y, p, limiar) -> dict:
    tn, fp, fn, tp = confusion_matrix(y, p >= limiar, labels=[0, 1]).ravel()
    div = lambda a, b: float(a / b) if b else 0.0
    precisao, recall = div(tp, tp + fp), div(tp, tp + fn)
    especificidade = div(tn, tn + fp)
    return {
        "limiar": round(float(limiar), 4),
        "vp": int(tp), "fp": int(fp), "fn": int(fn), "vn": int(tn),
        "acuracia": round(div(tp + tn, tp + tn + fp + fn), 4),
        "precisao": round(precisao, 4),
        "recall": round(recall, 4),
        "especificidade": round(especificidade, 4),
        "f1": round(div(2 * precisao * recall, precisao + recall), 4),
        "acuracia_balanceada": round((recall + especificidade) / 2, 4),
        "valor_preditivo_negativo": round(div(tn, tn + fn), 4),
    }


def calcular(df: pd.DataFrame) -> dict:
    modelo = carregar_modelo()
    y = _rotulo(df)
    p = modelo.prob_calibrada(vetorizar(df))
    base = df["score_inicial_modelo_base"].astype(float).to_numpy()
    prevalencia = float(y.mean())

    niveis = np.array([nivel_risco(v, modelo.limiar) for v in p])
    por_nivel = {
        n: {"sessoes": int((niveis == n).sum()), "golpe_real": round(float(y[niveis == n].mean()), 4) if (niveis == n).any() else None}
        for n in ("baixo", "moderado", "alto")
    }
    return {
        "modelo": modelo.nome_modelo,
        "versao_modelo": modelo.versao,
        "perguntas_por_sessao": TOTAL_PERGUNTAS,
        "sessoes_teste": int(len(y)),
        "golpes_teste": int(y.sum()),
        "prevalencia_golpe": round(prevalencia, 4),
        "no_limiar_do_modelo": metricas_no_limiar(y, p, modelo.limiar),
        "no_limiar_0_5": metricas_no_limiar(y, p, 0.5),
        "auc_roc": round(roc_auc_score(y, p), 4),
        "auc_pr": round(average_precision_score(y, p), 4),
        "brier": round(brier_score_loss(y, p), 4),
        "brier_referencia_chute": round(prevalencia * (1 - prevalencia), 4),
        "log_loss": round(log_loss(y, np.clip(p, 1e-6, 1 - 1e-6)), 4),
        "score_base_sozinho": {
            "auc_roc": round(roc_auc_score(y, base), 4),
            "auc_pr": round(average_precision_score(y, base), 4),
        },
        "por_nivel_de_risco": por_nivel,
        "_y": y, "_p": p, "_base": base,
    }


# ---------------------------------------------------------------- gráficos

def _estilo():
    plt.rcParams.update({
        "figure.facecolor": SUPERFICIE, "axes.facecolor": SUPERFICIE, "savefig.facecolor": SUPERFICIE,
        "font.size": 10.5, "axes.titlesize": 12.5, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.titlecolor": TEXTO, "axes.labelcolor": TEXTO_2, "xtick.color": TEXTO_2, "ytick.color": TEXTO_2,
        "axes.edgecolor": GRADE, "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": GRADE, "grid.linewidth": 0.8,
        "legend.frameon": False, "legend.labelcolor": TEXTO_2, "lines.linewidth": 2,
    })


def _virgula(valor, _pos):
    return f"{valor:g}".replace(".", ",")


def _salvar(fig, nome):
    for ax in fig.axes:
        if ax.get_xticks().size and ax.xaxis.get_ticklabels() and ax.get_xlabel():
            ax.xaxis.set_major_formatter(FuncFormatter(_virgula))
            ax.yaxis.set_major_formatter(FuncFormatter(_virgula))
    FIGURAS_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURAS_DIR / nome, dpi=150, bbox_inches="tight")
    plt.close(fig)


def grafico_matriz(m):
    c = m["no_limiar_do_modelo"]
    matriz = np.array([[c["vn"], c["fp"]], [c["fn"], c["vp"]]])
    total_linha = matriz.sum(axis=1, keepdims=True)
    fig, ax = plt.subplots(figsize=(5.4, 4.4))
    ax.imshow(matriz / total_linha, cmap=RAMPA_AZUL, vmin=0, vmax=1)
    ax.grid(False)
    rotulos = [["Verdadeiro negativo", "Falso positivo"], ["Falso negativo", "Verdadeiro positivo"]]
    for i in range(2):
        for j in range(2):
            frac = matriz[i, j] / total_linha[i, 0]
            cor = "white" if frac > 0.55 else TEXTO
            ax.text(j, i - 0.12, f"{matriz[i, j]}", ha="center", va="center", fontsize=20, fontweight="bold", color=cor)
            ax.text(j, i + 0.14, f"{frac:.0%} da linha", ha="center", va="center", fontsize=9.5, color=cor)
            ax.text(j, i + 0.32, rotulos[i][j], ha="center", va="center", fontsize=8.5, color=cor)
    ax.set_xticks([0, 1], ["Modelo: não é golpe", "Modelo: golpe"])
    ax.set_yticks([0, 1], ["Real: não é golpe", "Real: golpe"])
    ax.tick_params(length=0)
    for lado in ax.spines.values():
        lado.set_visible(False)
    ax.set_title(f"Matriz de confusão (limiar {_pct(c['limiar'])})")
    _salvar(fig, "matriz_confusao.png")


def grafico_roc(m):
    y, p, base = m["_y"], m["_p"], m["_base"]
    fig, ax = plt.subplots(figsize=(5.4, 4.6))
    ax.plot([0, 1], [0, 1], color=GRADE, lw=1.5, ls="--")
    ax.text(0.62, 0.55, "chute aleatório (AUC 0,50)", color=TEXTO_2, fontsize=8.5, rotation=36)
    for serie, cor, nome, auc in [(p, AZUL, "Modelo (3 perguntas)", m["auc_roc"]),
                                  (base, LARANJA, "Só o score inicial", m["score_base_sozinho"]["auc_roc"])]:
        fpr, tpr, _ = roc_curve(y, serie)
        ax.plot(fpr, tpr, color=cor, label=f"{nome} · AUC {auc:.2f}".replace(".", ","))
    c = m["no_limiar_do_modelo"]
    ax.plot(1 - c["especificidade"], c["recall"], "o", ms=8, color=AZUL, mec=SUPERFICIE, mew=2)
    ax.annotate("limiar do modelo", (1 - c["especificidade"], c["recall"]), xytext=(-125, 16),
                textcoords="offset points", color=TEXTO_2, fontsize=9,
                arrowprops={"arrowstyle": "-", "color": TEXTO_2, "lw": 0.8})
    ax.set(xlim=(0, 1), ylim=(0, 1.01), xlabel="Taxa de falsos positivos (legítimas alertadas)",
           ylabel="Recall (golpes detectados)")
    ax.set_title("Curva ROC")
    ax.legend(loc="lower right")
    _salvar(fig, "curva_roc.png")


def grafico_pr(m):
    y, p, base = m["_y"], m["_p"], m["_base"]
    fig, ax = plt.subplots(figsize=(5.4, 4.6))
    ax.axhline(m["prevalencia_golpe"], color=GRADE, lw=1.5, ls="--")
    ax.text(0.02, m["prevalencia_golpe"] + 0.02, f"chute aleatório ({m['prevalencia_golpe']:.0%} de golpes)",
            color=TEXTO_2, fontsize=8.5)
    for serie, cor, nome, ap in [(p, AZUL, "Modelo (3 perguntas)", m["auc_pr"]),
                                 (base, LARANJA, "Só o score inicial", m["score_base_sozinho"]["auc_pr"])]:
        prec, rec, _ = precision_recall_curve(y, serie)
        ax.plot(rec, prec, color=cor, label=f"{nome} · AUC-PR {ap:.2f}".replace(".", ","))
    c = m["no_limiar_do_modelo"]
    ax.plot(c["recall"], c["precisao"], "o", ms=8, color=AZUL, mec=SUPERFICIE, mew=2)
    ax.annotate("limiar do modelo", (c["recall"], c["precisao"]), xytext=(-100, -18),
                textcoords="offset points", color=TEXTO_2, fontsize=9)
    ax.set(xlim=(0, 1), ylim=(0, 1.01), xlabel="Recall (golpes detectados)", ylabel="Precisão (alertas corretos)")
    ax.set_title("Curva precisão × recall")
    ax.legend(loc="lower left")
    _salvar(fig, "curva_precisao_recall.png")


def grafico_calibracao(m):
    y, p = m["_y"], m["_p"]
    frac, media = calibration_curve(y, p, n_bins=10, strategy="quantile")
    fig, ax = plt.subplots(figsize=(5.4, 4.6))
    ax.plot([0, 1], [0, 1], color=GRADE, lw=1.5, ls="--")
    ax.text(0.55, 0.47, "calibração perfeita", color=TEXTO_2, fontsize=8.5, rotation=40)
    ax.plot(media, frac, color=AZUL, marker="o", ms=8, mec=SUPERFICIE, mew=2, label="Modelo")
    ax.set(xlim=(0, 1), ylim=(0, 1), xlabel="Probabilidade prevista pelo modelo",
           ylabel="Fração que era golpe de verdade")
    ax.set_title(f"Calibração · Brier {m['brier']:.3f}".replace(".", ","))
    ax.legend(loc="upper left")
    _salvar(fig, "calibracao.png")


def grafico_limiar(m):
    y, p = m["_y"], m["_p"]
    # Só limiares com alertas suficientes: acima disso a precisão vira ruído de poucos casos.
    limiares = [t for t in np.linspace(0.02, 0.95, 94) if (p >= t).sum() >= 25]
    series = {k: [] for k in ("precisao", "recall", "f1")}
    for t in limiares:
        r = metricas_no_limiar(y, p, t)
        for k in series:
            series[k].append(r[k])
    fig, ax = plt.subplots(figsize=(6.4, 4.4))
    # Rótulo direto de cada linha: (posição x, deslocamento vertical), em trechos onde as linhas se afastam.
    rotulos = {"precisao": (0.60, 0.04), "recall": (0.48, -0.11), "f1": (0.70, 0.04)}
    for (chave, nome), cor, estilo in zip([("precisao", "Precisão"), ("recall", "Recall"), ("f1", "F1")],
                                          [AZUL, LARANJA, AQUA], ["-", "--", "-."]):
        ax.plot(limiares, series[chave], color=cor, ls=estilo, label=nome)
        x, dy = rotulos[chave]
        ax.text(x, np.interp(x, limiares, series[chave]) + dy, nome, color=TEXTO_2, fontsize=9)
    limiar = m["no_limiar_do_modelo"]["limiar"]
    ax.axvline(limiar, color=TEXTO_2, lw=1, ls=":")
    ax.text(limiar + 0.01, 0.04, f"limiar escolhido ({_pct(limiar)})", color=TEXTO_2, fontsize=9)
    ax.set(xlim=(0, 1), ylim=(0, 1.02), xlabel="Limiar de decisão (probabilidade a partir da qual vira alerta)",
           ylabel="Valor da métrica")
    ax.set_title("Efeito do limiar nas métricas")
    ax.legend(loc="upper center", ncols=3, bbox_to_anchor=(0.5, -0.16))
    _salvar(fig, "limiar.png")


def grafico_distribuicao(m):
    y, p = m["_y"], m["_p"]
    bins = np.linspace(0, 1, 26)
    limiar = m["no_limiar_do_modelo"]["limiar"]
    fig, eixos = plt.subplots(2, 1, figsize=(6.4, 5.2), sharex=True, sharey=True)
    for ax, classe, cor, nome in [(eixos[0], 0, AZUL, "Não era golpe"), (eixos[1], 1, LARANJA, "Era golpe")]:
        ax.hist(p[y == classe], bins=bins, color=cor, edgecolor=SUPERFICIE, linewidth=2)
        ax.axvline(limiar, color=TEXTO_2, lw=1, ls=":")
        ax.set_title(f"{nome} ({(y == classe).sum()} sessões)", fontsize=10.5, color=TEXTO_2, fontweight="normal")
        ax.set_ylabel("Sessões")
    alto = eixos[0].get_ylim()[1]
    eixos[0].text(limiar + 0.01, alto * 0.85, f"limiar ({_pct(limiar)}): à direita vira alerta", color=TEXTO_2, fontsize=9)
    eixos[1].set(xlim=(0, 1), xlabel="Probabilidade de golpe prevista")
    fig.suptitle("Distribuição dos scores por classe real", x=0.08, ha="left", fontsize=12.5, fontweight="bold", color=TEXTO)
    fig.tight_layout()
    _salvar(fig, "distribuicao_scores.png")


# ---------------------------------------------------------------- texto

def _pct(v):
    return f"{v:.1%}".replace(".", ",")


def _num(v, casas=3):
    return f"{v:.{casas}f}".replace(".", ",")


def tabela_metricas(m) -> str:
    a, b = m["no_limiar_do_modelo"], m["no_limiar_0_5"]
    linhas = [
        ("Acurácia", "acuracia"), ("Precisão", "precisao"), ("Recall (sensibilidade)", "recall"),
        ("Especificidade", "especificidade"), ("F1-score", "f1"), ("Acurácia balanceada", "acuracia_balanceada"),
    ]
    out = [f"| Métrica | Limiar do modelo ({_pct(a['limiar'])}) | Limiar 50% |", "|---|---|---|"]
    out += [f"| {nome} | **{_pct(a[k])}** | {_pct(b[k])} |" for nome, k in linhas]
    out += [
        f"| AUC-ROC | **{_num(m['auc_roc'])}** (score inicial sozinho: {_num(m['score_base_sozinho']['auc_roc'])}) | — |",
        f"| AUC-PR | **{_num(m['auc_pr'])}** (score inicial sozinho: {_num(m['score_base_sozinho']['auc_pr'])}) | — |",
        f"| Brier score | **{_num(m['brier'])}** (chute: {_num(m['brier_referencia_chute'])}) | — |",
        f"| Log loss | {_num(m['log_loss'])} | — |",
    ]
    return "\n".join(out)


def tabela_matriz(c) -> str:
    return "\n".join([
        "| | Modelo: não é golpe | Modelo: golpe |",
        "|---|---|---|",
        f"| **Real: não é golpe** | {c['vn']} (verdadeiro negativo) | {c['fp']} (falso positivo) |",
        f"| **Real: golpe** | {c['fn']} (falso negativo) | {c['vp']} (verdadeiro positivo) |",
    ])


def tabela_niveis(m) -> str:
    out = ["| Nível de risco mostrado | Sessões | Quantas eram golpe de verdade |", "|---|---|---|"]
    for nivel, d in m["por_nivel_de_risco"].items():
        out.append(f"| {nivel} | {d['sessoes']} | {_pct(d['golpe_real']) if d['golpe_real'] is not None else '—'} |")
    return "\n".join(out)


def explicacao(m) -> str:
    c = m["no_limiar_do_modelo"]
    golpes, legit = c["vp"] + c["fn"], c["vn"] + c["fp"]
    alertas = c["vp"] + c["fp"]
    return f"""\
**A matriz de confusão** cruza o que o modelo disse com o que era verdade. Das {golpes} transações de golpe do teste, o modelo alertou {c['vp']} (**verdadeiros positivos**) e deixou passar {c['fn']} (**falsos negativos**, o erro mais caro). Das {legit} legítimas, liberou {c['vn']} sem alerta (**verdadeiros negativos**) e alertou {c['fp']} à toa (**falsos positivos**, que custam um incômodo ao cliente).

- **Acurácia ({_pct(c['acuracia'])})**: quantas decisões o modelo acertou, no total. Parece a métrica mais natural, mas engana quando as classes são desbalanceadas: como só {_pct(m['prevalencia_golpe'])} das sessões são golpe, um "modelo" que respondesse sempre "não é golpe" teria {_pct(1 - m['prevalencia_golpe'])} de acurácia sem detectar nenhum golpe. Por isso ela não é a métrica principal aqui.
- **Recall ou sensibilidade ({_pct(c['recall'])})**: dos golpes reais, quantos o modelo pegou. Aqui, **de cada 100 golpes, ~{round(c['recall'] * 100)} são alertados**. É a métrica prioritária, porque um golpe que passa vira dinheiro perdido e, no Pix, difícil de recuperar.
- **Precisão ({_pct(c['precisao'])})**: dos alertas que o modelo deu, quantos eram golpe mesmo. Aqui, **de cada 10 alertas, ~{round(c['precisao'] * 10)} são golpe**; os outros são falsos alarmes. Com {alertas} alertas no teste, {c['fp']} foram em transações legítimas.
- **Especificidade ({_pct(c['especificidade'])})**: das transações legítimas, quantas passaram sem alerta. É o "recall" do lado das legítimas.
- **F1-score ({_pct(c['f1'])})**: um único número que combina precisão e recall (média harmônica). Só fica alto se os dois forem altos; serve para comparar modelos ou limiares.
- **Acurácia balanceada ({_pct(c['acuracia_balanceada'])})**: média entre recall e especificidade. Diferente da acurácia comum, não é inflada pela classe majoritária.
- **AUC-ROC ({_num(m['auc_roc'])})**: não depende de limiar. É a chance de um golpe sorteado receber um score maior que uma transação legítima sorteada. 0,5 é chute; 1,0 é perfeito. O score inicial sozinho dá {_num(m['score_base_sozinho']['auc_roc'])}: **as 3 perguntas melhoram a separação**.
- **AUC-PR ({_num(m['auc_pr'])})**: resume a curva precisão × recall. A referência de um chute é a proporção de golpes ({_num(m['prevalencia_golpe'])}); quanto mais acima, melhor.
- **Brier score ({_num(m['brier'])})**: erro médio da probabilidade (0 é perfeito). Um modelo que sempre dissesse "{_pct(m['prevalencia_golpe'])} de chance" teria {_num(m['brier_referencia_chute'])}. Importa porque o app mostra a probabilidade ao cliente.
- **Calibração**: se o modelo diz 70%, cerca de 70% desses casos deveriam ser golpe. No gráfico, quanto mais perto da diagonal, mais confiável é o número exibido.

**Por que o limiar é {_pct(c['limiar'])} e não 50%?** O limiar é a probabilidade a partir da qual a transação vira alerta. Ele foi escolhido no conjunto de validação como o maior que ainda detecta pelo menos 90% dos golpes; no teste, com dados que o modelo nunca viu, o recall ficou em {_pct(c['recall'])}, uma variação normal entre amostras. Abaixá-lo aumenta o recall e derruba a precisão; subi-lo faz o contrário (veja o gráfico do limiar e a coluna "Limiar 50%" da tabela). Como a transferência nunca é bloqueada, só avisada, um falso alarme custa pouco e um golpe não detectado custa muito, então o limiar favorece o recall."""


def origem_dos_dados(m) -> str:
    c = m["no_limiar_do_modelo"]
    return f"""\
Não há base pública de transações Pix com desfecho real, então as sessões foram **simuladas** por `triagem/gerador_dataset.py` (12.000 sessões):

1. **Situação escondida:** o gerador sorteia se a sessão é legítima (~66%) ou um tipo de golpe (falsa central, WhatsApp clonado, venda falsa, mão fantasma etc.).
2. **Dados da transação:** valor, horário, chave e dispositivo são gerados de acordo com essa situação. Um golpe, por exemplo, tende a ter valor alto e redondo e chave recém-criada.
3. **Perguntas e respostas:** as {m['perguntas_por_sessao']} perguntas são escolhidas pelo mesmo seletor da API, e as respostas são sorteadas conforme a situação. Numa sessão de mão fantasma, "instalei um app que me pediram" é bem mais provável; numa legítima, predominam respostas tranquilas.
4. **Gabarito:** cada sessão recebe o rótulo golpe / não é golpe por uma fórmula que combina o score inicial, as respostas e um ruído aleatório.

As sessões foram divididas em 80% treino, 10% validação e 10% teste. O modelo aprendeu só com o treino. Para cada uma das {m['sessoes_teste']} sessões de teste (sem as de coação física), ele recebe os dados da transação e as respostas, **sem ver o gabarito**, e devolve uma probabilidade. Se ela for de pelo menos {_pct(c['limiar'])}, a sessão conta como alerta. Comparando com o gabarito:

| | Era golpe | Não era golpe |
|---|---|---|
| **Modelo alertou** | VP = {c['vp']} | FP = {c['fp']} |
| **Modelo não alertou** | FN = {c['fn']} | VN = {c['vn']} |

Todas as outras métricas saem dessas quatro contagens (por exemplo, recall = VP / (VP + FN)). A exceção são AUC, Brier e calibração, que usam a probabilidade diretamente.

> **Limitação:** como o gabarito vem de uma fórmula escrita por nós, as métricas medem o quanto o modelo reaprende essa fórmula a partir das respostas, **não** o quanto ele acertaria com golpes reais. Para isso é preciso comparar com desfechos reais confirmados; o log da API em SQLite já guarda as sessões no mesmo formato para quando esses dados existirem."""


def secao_readme(m) -> str:
    c = m["no_limiar_do_modelo"]
    fig = "servico/relatorios/figuras"
    return f"""{MARCA_INICIO}
<!-- Seção gerada por `python -m triagem.relatorio` (a partir de servico/). Não edite à mão. -->

Avaliado em **{m['sessoes_teste']} sessões de teste** que o modelo nunca viu ({m['golpes_teste']} golpes, {_pct(m['prevalencia_golpe'])}), com **{m['perguntas_por_sessao']} perguntas por sessão**. Modelo: `{m['modelo']}`, versão `{m['versao_modelo']}`. O relatório completo está em [`servico/relatorios/metricas.md`](servico/relatorios/metricas.md).

**Resumo:** de cada 100 golpes, o modelo alerta ~{round(c['recall'] * 100)}; de cada 10 alertas, ~{round(c['precisao'] * 10)} são golpe de verdade. As 3 perguntas levam a AUC de {_num(m['score_base_sozinho']['auc_roc'], 2)} (só o score inicial) para {_num(m['auc_roc'], 2)}.

{tabela_metricas(m)}

| | |
|---|---|
| ![Matriz de confusão]({fig}/matriz_confusao.png) | ![Curva ROC]({fig}/curva_roc.png) |
| ![Curva precisão × recall]({fig}/curva_precisao_recall.png) | ![Calibração]({fig}/calibracao.png) |
| ![Efeito do limiar]({fig}/limiar.png) | ![Distribuição dos scores]({fig}/distribuicao_scores.png) |

### De onde vêm esses números

{origem_dos_dados(m)}

### Como interpretar

{explicacao(m)}
{MARCA_FIM}"""


def relatorio_md(m) -> str:
    c = m["no_limiar_do_modelo"]
    return f"""# Relatório de métricas do classificador

Gerado por `python -m triagem.relatorio`. Modelo `{m['modelo']}`, versão `{m['versao_modelo']}`, **{m['perguntas_por_sessao']} perguntas por sessão**.
Conjunto de teste: {m['sessoes_teste']} sessões ({m['golpes_teste']} golpes, {_pct(m['prevalencia_golpe'])}), sem as sessões de coação física.
As métricas usam a probabilidade calibrada sem teto/piso, que é a usada nas decisões da API.

## De onde vêm esses números

{origem_dos_dados(m)}

## Métricas

{tabela_metricas(m)}

## Matriz de confusão (limiar {_pct(c['limiar'])})

{tabela_matriz(c)}

![Matriz de confusão](figuras/matriz_confusao.png)

## Como interpretar

{explicacao(m)}

## Curvas

**ROC**: cada ponto é um limiar possível. Quanto mais a curva encosta no canto superior esquerdo, melhor. A curva laranja mostra o que o score inicial conseguiria sozinho, sem as perguntas.

![Curva ROC](figuras/curva_roc.png)

**Precisão × recall**: mostra a troca entre detectar mais golpes (direita) e dar menos alarmes falsos (alto). É a curva mais honesta quando os golpes são minoria.

![Curva precisão × recall](figuras/curva_precisao_recall.png)

**Calibração**: as probabilidades foram agrupadas em 10 faixas; cada ponto compara a média prevista com a fração real de golpes na faixa.

![Calibração](figuras/calibracao.png)

**Efeito do limiar**: como precisão, recall e F1 mudam conforme o limiar sobe. A linha pontilhada é o limiar em uso.

![Efeito do limiar](figuras/limiar.png)

**Distribuição dos scores**: quanto menos as duas cores se sobrepõem, melhor o modelo separa golpe de não-golpe. O que fica à direita do limiar vira alerta.

![Distribuição dos scores](figuras/distribuicao_scores.png)

## Níveis de risco mostrados ao cliente

O app mostra baixo (abaixo do limiar), moderado (entre o limiar e 50%) ou alto (50% ou mais). A tabela mostra quantos eram golpe de verdade em cada nível:

{tabela_niveis(m)}
"""


def atualizar_readme(m) -> bool:
    texto = README.read_text(encoding="utf-8")
    if MARCA_INICIO not in texto or MARCA_FIM not in texto:
        return False
    padrao = re.compile(re.escape(MARCA_INICIO) + r".*?" + re.escape(MARCA_FIM), re.S)
    README.write_text(padrao.sub(lambda _: secao_readme(m), texto), encoding="utf-8")
    return True


def main():
    df = _sem_coacao(pd.read_csv(DADOS_DIR / "sintetico" / "teste.csv"))
    m = calcular(df)

    _estilo()
    for grafico in (grafico_matriz, grafico_roc, grafico_pr, grafico_calibracao, grafico_limiar, grafico_distribuicao):
        grafico(m)

    RELATORIO_DIR.mkdir(exist_ok=True)
    (RELATORIO_DIR / "metricas.md").write_text(relatorio_md(m), encoding="utf-8")
    publicas = {k: v for k, v in m.items() if not k.startswith("_")}
    (RELATORIO_DIR / "metricas.json").write_text(json.dumps(publicas, indent=2, ensure_ascii=False), encoding="utf-8")
    readme_ok = atualizar_readme(m)

    c = m["no_limiar_do_modelo"]
    print(f"Teste: {m['sessoes_teste']} sessões ({_pct(m['prevalencia_golpe'])} golpe), {m['perguntas_por_sessao']} perguntas/sessão")
    print(f"Limiar {_pct(c['limiar'])}: acurácia {_pct(c['acuracia'])} | precisão {_pct(c['precisao'])} | "
          f"recall {_pct(c['recall'])} | especificidade {_pct(c['especificidade'])} | F1 {_pct(c['f1'])}")
    print(f"Matriz: VN={c['vn']} FP={c['fp']} FN={c['fn']} VP={c['vp']}")
    print(f"AUC-ROC {_num(m['auc_roc'])} (score inicial: {_num(m['score_base_sozinho']['auc_roc'])}) | "
          f"AUC-PR {_num(m['auc_pr'])} | Brier {_num(m['brier'])}")
    print(f"Relatório: {RELATORIO_DIR / 'metricas.md'}")
    print("README atualizado." if readme_ok else f"README sem os marcadores {MARCA_INICIO}/{MARCA_FIM}: não alterado.")


if __name__ == "__main__":
    main()
