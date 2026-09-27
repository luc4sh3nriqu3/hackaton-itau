# hackaton-itau

Protótipo de app bancário (pasta `MVP/`) integrado a um serviço de **triagem educativa de golpes do Pix** (pasta `servico/`).

Quando uma transferência Pix parece suspeita, o app abre uma conversa com a ia.itaú. São 3 perguntas de múltipla escolha, escolhidas conforme a transação, e cada uma ensina um truque usado por golpistas. Depois o usuário dá o próprio veredito e recebe uma probabilidade refinada de golpe, com uma explicação personalizada. A transferência nunca é bloqueada: a decisão final é do usuário.

## Como rodar

```bash
# 1. Ambiente Python (3.12)
python3 -m venv .venv            # se faltar o pacote python3-venv: python3 -m venv --without-pip .venv
.venv/bin/pip install -r servico/requirements.txt   # ou: python3 -m pip --python .venv/bin/python install -r servico/requirements.txt

# 2. Configuração
cp servico/.env.example servico/.env

# 3. Dataset sintético + treino (o modelo já treinado está em servico/modelos/)
cd servico
../.venv/bin/python -m triagem.gerador_dataset --n 12000
../.venv/bin/python -m triagem.treino
../.venv/bin/python -m triagem.relatorio   # métricas + gráficos (seção "Métricas do modelo")

# 4. API  →  http://localhost:8000/docs
../.venv/bin/uvicorn triagem.api:app --port 8000

# 5. MVP (em outro terminal)  →  http://localhost:5500/index.html
cd MVP && python3 -m http.server 5500

# Testes
cd servico && ../.venv/bin/python -m pytest -q tests
```

Roteiro da demo: Pix → digite uma chave nova (por exemplo `golpista@mail.com`) → valor de R$ 1.000,00 → Transferir → "Iniciar avaliação".

### Onde colocar a chave do Gemini

Coloque a chave em **`servico/.env`**, na linha `GEMINI_API_KEY=` (a chave é gerada em https://aistudio.google.com/apikey).

O `.env` é relido a cada requisição, então a próxima avaliação já usa o Gemini sem reiniciar nada. Enquanto não houver chave, ou se o Gemini falhar ou demorar, a explicação sai de um template local, também personalizado com as respostas do usuário. O campo `fonte_explicacao` do resultado indica qual dos dois foi usado, e `GET /saude` mostra se a chave foi detectada. O `.env` está no `.gitignore`.

## Etapa 0 — o que tinha no MVP

- **Stack:** só frontend, em HTML, CSS e JavaScript puros, sem build e sem framework. Não havia backend nem API. Os dados são mockados, e o estado da transferência fica no `sessionStorage` (`lerTransferencia` e `salvarTransferencia` em `MVP/app.js`).
- **Fluxo Pix que já existia:** `pix.html` → `destinatario.html` → `contato.html` → `valor.html` → `conta.html` → `confirmacao.html` → `comprovante.html`. A confirmação sempre abria um alerta de "Possível fraude" levando a `avaliacao.html`, um chat com 3 perguntas fixas e um score escrito à mão.
- **Convenções seguidas:** nomes em português, script inline em cada página usando os helpers de `app.js`, e os mesmos componentes visuais do chat (`.msg-bot`, `.msg-usuario`, `.chip`, `.sheet`).
- **Decisão:** a integração entrou no `avaliacao.html`, que foi reescrito para consumir a API mantendo o visual de chat. O `confirmacao.html` passou a abrir o alerta só quando o score inicial mockado passa de `LIMIAR_ALERTA` (0,65).

## Arquitetura

```
servico/
  dados/perguntas.json       banco de 30 perguntas didáticas (7 dimensões × 4–5 facetas), versionado
  dados/sintetico/*.csv      dataset gerado (treino/validacao/teste, 38 colunas)
  modelos/                   classificador.joblib + metricas.json
  triagem/
    config.py                variáveis de ambiente + .env (relido a cada chamada)
    banco_perguntas.py       carrega e valida o banco
    seletor.py               seletor de perguntas (sorteio ponderado, substituível)
    esquema.py               as colunas (38 com 3 perguntas)
    gerador_dataset.py       dataset sintético
    features.py              vetorização compartilhada entre treino e produção
    treino.py / classificador.py
    gemini.py                explicação (Gemini ou template) + orientação de coação
    armazenamento.py         log em SQLite (insumo de retreino)
    api.py                   FastAPI
MVP/
  triagem.js                 cliente da API + heurística mock do Bloco 1 (PLACEHOLDER)
  confirmacao.html           decide se abre o alerta
  avaliacao.html             chat com 3 perguntas → veredito → resultado
```

### API REST (`X-API-Key`, JSON, OpenAPI em `/docs`)

| Rota | O que faz |
|---|---|
| `POST /v1/sessoes` | Recebe o Bloco 1 e devolve `sessao_id` e a 1ª pergunta |
| `POST /v1/sessoes/{id}/respostas` | Recebe `{pergunta_id, alternativa_id}` e devolve a próxima pergunta, `aguardando_veredito` ou `coacao` |
| `POST /v1/sessoes/{id}/veredito` | Recebe `{veredito_usuario}` e calcula score e explicação |
| `GET /v1/sessoes/{id}/resultado` | Devolve `score_refinado`, `nivel_risco`, `explicacao_gerada` e `fonte_explicacao` |
| `POST /v1/sessoes/{id}/decisao` | (extra, opcional) Recebe `usuario_seguiu_recomendacao` |
| `GET /saude` | Versões e se o Gemini está configurado |

As perguntas chegam ao cliente sem multiplicadores nem flags internas. O MVP consome exatamente essa API pública, sem atalho interno.

## Métricas do modelo

Para regenerar esta seção, os gráficos e o relatório completo (`servico/relatorios/`):

```bash
cd servico && ../.venv/bin/python -m triagem.relatorio
```

<!-- METRICAS:INICIO -->
<!-- Seção gerada por `python -m triagem.relatorio` (a partir de servico/). Não edite à mão. -->

Avaliado em **1198 sessões de teste** que o modelo nunca viu (391 golpes, 32,6%), com **3 perguntas por sessão**. Modelo: `regressao_logistica`, versão `20260927000114`. O relatório completo está em [`servico/relatorios/metricas.md`](servico/relatorios/metricas.md).

**Resumo:** de cada 100 golpes, o modelo alerta ~87; de cada 10 alertas, ~6 são golpe de verdade. As 3 perguntas levam a AUC de 0,80 (só o score inicial) para 0,86.

| Métrica | Limiar do modelo (16,6%) | Limiar 50% |
|---|---|---|
| Acurácia | **73,5%** | 81,2% |
| Precisão | **56,1%** | 73,7% |
| Recall (sensibilidade) | **86,7%** | 66,0% |
| Especificidade | **67,2%** | 88,6% |
| F1-score | **68,1%** | 69,6% |
| Acurácia balanceada | **76,9%** | 77,3% |
| AUC-ROC | **0,856** (score inicial sozinho: 0,797) | — |
| AUC-PR | **0,750** (score inicial sozinho: 0,661) | — |
| Brier score | **0,137** (chute: 0,220) | — |
| Log loss | 0,434 | — |

| | |
|---|---|
| ![Matriz de confusão](servico/relatorios/figuras/matriz_confusao.png) | ![Curva ROC](servico/relatorios/figuras/curva_roc.png) |
| ![Curva precisão × recall](servico/relatorios/figuras/curva_precisao_recall.png) | ![Calibração](servico/relatorios/figuras/calibracao.png) |
| ![Efeito do limiar](servico/relatorios/figuras/limiar.png) | ![Distribuição dos scores](servico/relatorios/figuras/distribuicao_scores.png) |

### De onde vêm esses números

Não há base pública de transações Pix com desfecho real, então as sessões foram **simuladas** por `triagem/gerador_dataset.py` (12.000 sessões):

1. **Situação escondida:** o gerador sorteia se a sessão é legítima (~66%) ou um tipo de golpe (falsa central, WhatsApp clonado, venda falsa, mão fantasma etc.).
2. **Dados da transação:** valor, horário, chave e dispositivo são gerados de acordo com essa situação. Um golpe, por exemplo, tende a ter valor alto e redondo e chave recém-criada.
3. **Perguntas e respostas:** as 3 perguntas são escolhidas pelo mesmo seletor da API, e as respostas são sorteadas conforme a situação. Numa sessão de mão fantasma, "instalei um app que me pediram" é bem mais provável; numa legítima, predominam respostas tranquilas.
4. **Gabarito:** cada sessão recebe o rótulo golpe / não é golpe por uma fórmula que combina o score inicial, as respostas e um ruído aleatório.

As sessões foram divididas em 80% treino, 10% validação e 10% teste. O modelo aprendeu só com o treino. Para cada uma das 1198 sessões de teste (sem as de coação física), ele recebe os dados da transação e as respostas, **sem ver o gabarito**, e devolve uma probabilidade. Se ela for de pelo menos 16,6%, a sessão conta como alerta. Comparando com o gabarito:

| | Era golpe | Não era golpe |
|---|---|---|
| **Modelo alertou** | VP = 339 | FP = 265 |
| **Modelo não alertou** | FN = 52 | VN = 542 |

Todas as outras métricas saem dessas quatro contagens (por exemplo, recall = VP / (VP + FN)). A exceção são AUC, Brier e calibração, que usam a probabilidade diretamente.

> **Limitação:** como o gabarito vem de uma fórmula escrita por nós, as métricas medem o quanto o modelo reaprende essa fórmula a partir das respostas, **não** o quanto ele acertaria com golpes reais. Para isso é preciso comparar com desfechos reais confirmados; o log da API em SQLite já guarda as sessões no mesmo formato para quando esses dados existirem.

### Como interpretar

**A matriz de confusão** cruza o que o modelo disse com o que era verdade. Das 391 transações de golpe do teste, o modelo alertou 339 (**verdadeiros positivos**) e deixou passar 52 (**falsos negativos**, o erro mais caro). Das 807 legítimas, liberou 542 sem alerta (**verdadeiros negativos**) e alertou 265 à toa (**falsos positivos**, que custam um incômodo ao cliente).

- **Acurácia (73,5%)**: quantas decisões o modelo acertou, no total. Parece a métrica mais natural, mas engana quando as classes são desbalanceadas: como só 32,6% das sessões são golpe, um "modelo" que respondesse sempre "não é golpe" teria 67,4% de acurácia sem detectar nenhum golpe. Por isso ela não é a métrica principal aqui.
- **Recall ou sensibilidade (86,7%)**: dos golpes reais, quantos o modelo pegou. Aqui, **de cada 100 golpes, ~87 são alertados**. É a métrica prioritária, porque um golpe que passa vira dinheiro perdido e, no Pix, difícil de recuperar.
- **Precisão (56,1%)**: dos alertas que o modelo deu, quantos eram golpe mesmo. Aqui, **de cada 10 alertas, ~6 são golpe**; os outros são falsos alarmes. Com 604 alertas no teste, 265 foram em transações legítimas.
- **Especificidade (67,2%)**: das transações legítimas, quantas passaram sem alerta. É o "recall" do lado das legítimas.
- **F1-score (68,1%)**: um único número que combina precisão e recall (média harmônica). Só fica alto se os dois forem altos; serve para comparar modelos ou limiares.
- **Acurácia balanceada (76,9%)**: média entre recall e especificidade. Diferente da acurácia comum, não é inflada pela classe majoritária.
- **AUC-ROC (0,856)**: não depende de limiar. É a chance de um golpe sorteado receber um score maior que uma transação legítima sorteada. 0,5 é chute; 1,0 é perfeito. O score inicial sozinho dá 0,797: **as 3 perguntas melhoram a separação**.
- **AUC-PR (0,750)**: resume a curva precisão × recall. A referência de um chute é a proporção de golpes (0,326); quanto mais acima, melhor.
- **Brier score (0,137)**: erro médio da probabilidade (0 é perfeito). Um modelo que sempre dissesse "32,6% de chance" teria 0,220. Importa porque o app mostra a probabilidade ao cliente.
- **Calibração**: se o modelo diz 70%, cerca de 70% desses casos deveriam ser golpe. No gráfico, quanto mais perto da diagonal, mais confiável é o número exibido.

**Por que o limiar é 16,6% e não 50%?** O limiar é a probabilidade a partir da qual a transação vira alerta. Ele foi escolhido no conjunto de validação como o maior que ainda detecta pelo menos 90% dos golpes; no teste, com dados que o modelo nunca viu, o recall ficou em 86,7%, uma variação normal entre amostras. Abaixá-lo aumenta o recall e derruba a precisão; subi-lo faz o contrário (veja o gráfico do limiar e a coluna "Limiar 50%" da tabela). Como a transferência nunca é bloqueada, só avisada, um falso alarme custa pouco e um golpe não detectado custa muito, então o limiar favorece o recall.
<!-- METRICAS:FIM -->

## Decisões de modelagem

- **Banco de perguntas:** cada variante de uma dimensão pergunta uma **faceta diferente**. Por exemplo, em P4 há urgência, sigilo, medo e apelo emocional, assim o usuário nunca responde a mesma coisa duas vezes. Cada alternativa tem:
  - um multiplicador dentro da faixa da dimensão;
  - a flag `protetora`, que marca uma resposta de quem reconhece o risco;
  - a flag `coacao`;
  - `tipos`, com os golpes em que ela é típica.
- **`pontuacao_reconhecimento_padroes`** é o número de respostas `protetora`, de 0 a 3.
- **Seletor:** usa `amplitude_log × boost × 0,6^(repetições da dimensão)` como peso de um sorteio sem reposição.
  - A sessão tem **3 perguntas** (`TOTAL_PERGUNTAS` em `seletor.py`).
  - A penalidade suave faz as perguntas preferirem dimensões diferentes. Com `valor_atipico`, P2 e P5 são as mais perguntadas; ~1,3 das 3 perguntas vêm das dimensões do fator de risco.
  - `BOOST_PRINCIPAL` e `PENALIDADE_REPETICAO` em `seletor.py` controlam essa concentração.
- **Gerador sintético:**
  - Sorteia uma situação latente: legítima ou um dos 7 tipos de golpe.
  - Gera o Bloco 1 com as correlações descritas nas fontes: madrugada, valores altos e redondos, chave recente, mão fantasma com dispositivo não reconhecido e digitação atípica, entre outras.
  - Responde às perguntas com o mesmo seletor de produção.
  - Os multiplicadores só entram no rótulo, nunca no classificador.
  - O rótulo usa `logit(score_base) + 0,8·Σlog(mult)` sobre as 3 respostas. Resultado: 12.000 sessões, ~32% de golpe e ~0,2% de coação, com split 80/10/10.
- **Classificador:**
  - Features: o Bloco 1, o one-hot de cada pergunta e alternativa (e não por posição, porque a dimensão de cada posição varia), a contagem por dimensão e `pontuacao_reconhecimento_padroes`.
  - Não usa os multiplicadores nem `veredito_usuario`. As sessões com coação ficam fora do treino.
  - Comparei regressão logística e LightGBM, e a logística venceu na validação (o gerador é linear no logit). A calibração é de Platt.
  - O limiar é o maior que mantém recall ≥ 90% na validação.
  - A decisão usa a probabilidade sem corte. O score exibido tem piso 0,15 e teto 0,98.
- **Métricas:** veja a seção [Métricas do modelo](#métricas-do-modelo), gerada pelo script `triagem/relatorio.py`.
- **Coação física:** a sessão é interrompida na hora e a API devolve uma orientação de segurança **fixa e revisada** (190, MED, banco), sem passar pelo Gemini. Numa situação de risco físico, esse texto não deve depender de rede nem da variação de um modelo generativo.
- **Log para retreino:** o SQLite (`servico/triagem.db`) guarda uma linha por sessão com as colunas do esquema, mais o status, as versões de modelo e de banco e a probabilidade interna. Quando o desfecho real for confirmado, basta preencher `rotulo_real_golpe` e `rotulo_tipo_golpe`, e as linhas passam a servir de dado real no mesmo formato do sintético. O retreino automático fica fora do escopo desta versão.

## Placeholders e limitações

- **Score inicial mockado:** `montarBloco1` em `MVP/triagem.js` simula o modelo antifraude de origem a partir do valor, de o destinatário ser novo e do horário. Para usar o modelo real, basta trocar o corpo dessa função mantendo o formato do objeto retornado.
- **Chave da API no navegador:** a chave fica visível em `MVP/triagem.js`. Serve para o protótipo, mas em produção a chamada passaria por um backend.
- **Dados sintéticos:** o dataset é inteiramente sintético (não existe base pública caso a caso de Pix). As métricas medem o quanto o modelo recupera o processo gerador, não o desempenho no mundo real.
- **Fontes usadas para o realismo:** Pizzolato et al., *A Taxonomy of Pix Fraud in Brazil* (arXiv:2511.20902), e o Observatório Lupa, *A Jornada dos Golpes*.
