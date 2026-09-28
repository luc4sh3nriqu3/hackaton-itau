# hackaton-itau · espera.ai

Protótipo de app bancário (pasta `MVP/`) integrado a um serviço de **triagem educativa de golpes do Pix** (pasta `servico/`).
▶️ [Vídeo Demonstrativo](https://www.youtube.com/watch?v=zCMpnO325g0)

**Como funciona:**
1. Quando uma transferência Pix foge do padrão do cliente, o app mostra uma **página de alerta** com os pontos de atenção. O cliente pode seguir direto ou fazer a avaliação com a **espera.ai**.
2. A avaliação é uma conversa com **3 perguntas** de múltipla escolha. Cada uma vem com uma dica curta sobre golpes, e os balões podem ser lidos em voz alta (botão de som).
3. Com base nas respostas, o serviço estima a chance de golpe. Se houver sinais de risco, o chat pergunta *"Você não gostaria de repensar sobre essa transação por alguns minutos?"* e mostra os motivos com calma, sem números nem alarme.
4. A transferência **nunca é bloqueada**: o cliente escolhe entre "Continuar transferência mesmo assim" e "Cancelar transferência".
5. Depois de qualquer **transferência realizada**, com ou sem avaliação, a próxima visita à home mostra um pop-up perguntando se aquele Pix era golpe. A resposta (`golpe`, `nao_golpe` ou `sem_resposta`) ajuda a confirmar desfechos reais para o retreino. Transferência cancelada não gera pop-up.

## Como rodar

Você vai subir duas coisas: a **API** (porta 8000) e o **site do app** (porta 5500). Cada uma roda num terminal separado e precisa continuar aberta enquanto você usa o app.

**Pré-requisitos:**
- **Python 3.10 ou mais novo** ([python.org/downloads](https://www.python.org/downloads/)). No Windows, marque **"Add python.exe to PATH"** na instalação.
- O código do projeto: `git clone https://github.com/luc4sh3nriqu3/hackaton-itau.git`, ou baixe o ZIP pelo botão "Code" do GitHub e extraia.
- Não precisa de chave do Gemini: sem ela, o texto final sai de um modelo local.

O modelo já vem treinado em `servico/modelos/`, então não é preciso gerar dados nem treinar para ver o app.

### Linux (e macOS)

Abra um terminal na pasta do projeto (`hackaton-itau`):

```bash
# 1. Criar o ambiente Python e instalar as dependências (só na primeira vez; leva alguns minutos)
python3 -m venv .venv
.venv/bin/pip install -r servico/requirements.txt

# 2. Criar o arquivo de configuração (só na primeira vez)
cp servico/.env.example servico/.env

# 3. Subir a API (deixe este terminal aberto)
cd servico
../.venv/bin/python -m uvicorn triagem.api:app --port 8000
```

Abra **outro terminal** na pasta do projeto:

```bash
# 4. Subir o site do app (deixe este terminal aberto também)
cd MVP
python3 -m http.server 5500
```

No Ubuntu/Debian, se o passo 1 der erro de `ensurepip`, instale o pacote que falta com `sudo apt install python3-venv` e repita.

### Windows (PowerShell ou Prompt de Comando)

Abra um terminal na pasta do projeto (`hackaton-itau`). Os comandos funcionam tanto no PowerShell quanto no Prompt de Comando.

**1. Criar o ambiente Python e instalar as dependências** (só na primeira vez; leva alguns minutos):

```bat
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r servico\requirements.txt
```

**2. Criar o arquivo de configuração** (só na primeira vez):

```bat
copy servico\.env.example servico\.env
```

**3. Subir a API** (deixe este terminal aberto):

```bat
cd servico
..\.venv\Scripts\python.exe -m uvicorn triagem.api:app --port 8000
```

**4. Subir o site do app:** abra **outro terminal** na pasta do projeto e rode (deixe aberto também):

```bat
cd MVP
py -m http.server 5500
```

Se o comando `py` não existir, use `python` no lugar. Os comandos chamam o Python do ambiente direto, então não é preciso "ativar" o `.venv`, o que evita o bloqueio de scripts do PowerShell.

### Usar o app

1. Abra **http://localhost:5500/index.html** no navegador. Funciona melhor no Chrome ou Edge, com a janela estreita ou no modo celular do DevTools (F12).
2. Para conferir a API, abra **http://localhost:8000/saude**, que deve mostrar `"ok": true`. A documentação das rotas fica em **http://localhost:8000/docs**.
3. Para a apresentação, ligue o [modo demo](#modo-demo-apresentações): em `servico/.env`, troque para `TRIAGEM_MODO_DEMO=1`. Não precisa reiniciar.

**Roteiro do fluxo real:** Pix → digite uma chave nova (ex.: `golpista@mail.com`) → valor de R$ 1.000,00 → Transferir → página de alerta → "Iniciar avaliação" → responda as 3 perguntas → "Continuar transferência mesmo assim" → senha (qualquer 6 dígitos) → comprovante → "Voltar ao início": o pop-up de feedback aparece na home.

**Se algo der errado:**
- **O chat diz "Não consegui concluir a avaliação":** a API não está rodando. Confira o terminal do passo 3.
- **A tela parece antiga depois de atualizar o código:** recarregue sem cache com **Ctrl+Shift+R**.
- **"Address already in use" ou porta ocupada:** já existe outro programa usando a porta 8000 ou 5500. Feche o terminal antigo ou troque a porta (se trocar a da API, ajuste `TRIAGEM_API_URL` em `MVP/triagem.js`).
- **Para parar:** `Ctrl+C` em cada terminal.

### Para desenvolvedores

A partir da pasta `servico/` (no Windows, troque `../.venv/bin/python` por `..\.venv\Scripts\python.exe`):

```bash
../.venv/bin/python -m pytest -q tests                      # testes
../.venv/bin/python -m triagem.gerador_dataset --n 12000     # regerar o dataset sintético
../.venv/bin/python -m triagem.treino                        # retreinar o modelo
../.venv/bin/python -m triagem.relatorio                     # métricas + gráficos (seção "Métricas do modelo")
../.venv/bin/python -m uvicorn triagem.api:app --port 8000 --reload   # API recarregando ao editar o código
```

### Onde colocar a chave do Gemini

Coloque a chave em **`servico/.env`**, na linha `GEMINI_API_KEY=` (a chave é gerada em https://aistudio.google.com/apikey).

O `.env` é relido a cada requisição, então a próxima avaliação já usa o Gemini sem reiniciar nada. Enquanto não houver chave, ou se o Gemini falhar ou demorar, a explicação sai de um template local, também personalizado com as respostas do usuário. O campo `fonte_explicacao` do resultado indica qual dos dois foi usado, e `GET /saude` mostra se a chave foi detectada. O `.env` está no `.gitignore`.

### Modo demo (apresentações)

Para apresentar, o chat pode usar sempre as **mesmas 3 perguntas** e um **texto final pronto**, sem sortear perguntas, sem o classificador e sem depender do Gemini.

**Como ativar:** no arquivo `servico/.env`, coloque

```
TRIAGEM_MODO_DEMO=1
```

Vale a partir da próxima avaliação, sem reiniciar a API. Para voltar ao fluxo real, use `TRIAGEM_MODO_DEMO=0` (ou apague a linha). Para conferir o modo ativo, abra `http://localhost:8000/saude` e veja `"modo_demo": true`.

**O que muda no modo demo:**
- As perguntas vêm de `servico/dados/perguntas_demo.json`, sempre nesta ordem, cada uma com uma dica curta:
  1. Falaram que esta transferência precisa ser feita com urgência? (Sim / Não)
  2. É para esta pessoa que você quer enviar o dinheiro? **nome do recebedor** (Sim / Não)
  3. Qual é o motivo da sua transferência? (Um parente ou conhecido está pedindo / Recebi uma mensagem para quitar dívidas / Recebi uma ligação fazendo cobranças)
- O texto final é uma lista curta de tópicos montada a partir das respostas. Cada alternativa tem um tópico pronto, com destaques em vermelho (alerta), laranja (ação) ou verde (bom sinal). Para mudar os textos, edite o JSON.
- Qualquer resposta de risco leva à mensagem de "repensar". Como todo motivo da pergunta 3 é um padrão de golpe, uma sessão completa sempre termina em "repensar".
- Decisão, pop-up de feedback e registro na base funcionam normalmente. As sessões ficam marcadas com `modo = demo` e `versao_modelo = demo`, para não se misturarem com dados reais.

**Roteiro da persona:** José Pereira, aposentado de 66 anos, recebe pelo WhatsApp uma mensagem de uma loja conhecida pedindo um Pix de R$ 2.500 para "quitar dívidas".
1. Pix → digite uma chave nova (ex.: `loja.whats@email.com`) → valor de R$ 2.500,00 → Transferir. Aparece o alerta.
2. Toque em "Iniciar avaliação" e responda: **Sim** (urgência) → **Sim** (é para essa pessoa) → **Recebi uma mensagem para quitar dívidas**.
3. O chat mostra "Você não gostaria de repensar sobre essa transação por alguns minutos?" com os tópicos.
4. "Continuar transferência mesmo assim" → senha → comprovante → "Voltar ao início": aparece o pop-up de feedback.

## Etapa 0 — o que tinha no MVP

- **Stack:** só frontend, em HTML, CSS e JavaScript puros, sem build e sem framework. Não havia backend nem API. Os dados são mockados, e o estado da transferência fica no `sessionStorage` (`lerTransferencia` e `salvarTransferencia` em `MVP/app.js`).
- **Fluxo Pix que já existia:** `pix.html` → `destinatario.html` → `contato.html` → `valor.html` → `conta.html` → `confirmacao.html` → `comprovante.html`. A confirmação sempre abria um alerta de "Possível fraude" levando a `avaliacao.html`, um chat com 3 perguntas fixas e um score escrito à mão.
- **Convenções seguidas:** nomes em português, script inline em cada página usando os helpers de `app.js`, e os mesmos componentes visuais do chat (`.msg-bot`, `.msg-usuario`, `.chip`, `.sheet`).
- **Decisão:** a integração entrou no `avaliacao.html`, que foi reescrito para consumir a API mantendo o visual de chat. O `confirmacao.html` passou a abrir o alerta só quando o score inicial mockado passa de `LIMIAR_ALERTA` (0,65).
- **Evoluções depois disso:** o assistente virou **espera.ai**; o alerta ganhou uma página própria (`alerta.html`) com pontos de atenção; a senha passou a ser pedida só quando o cliente decide transferir; e os balões do chat podem ser lidos em voz alta (`falar` e `montarBotaoSom` em `app.js`).

## Arquitetura

```
servico/
  dados/perguntas.json       banco de 30 perguntas didáticas (7 dimensões × 4–5 facetas), versionado
  dados/perguntas_demo.json  as 3 perguntas fixas e os tópicos do texto final do modo demo
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
    demo.py                  modo demo: perguntas fixas e texto final mockado
    relatorio.py             relatório de métricas + gráficos (atualiza o README)
    armazenamento.py         log em SQLite (insumo de retreino)
    api.py                   FastAPI
MVP/
  app.js                     helpers do app (estado da transferência, navegação, leitura em voz)
  triagem.js                 cliente da API + heurística mock do Bloco 1 (PLACEHOLDER)
  confirmacao.html           decide se abre o alerta
  alerta.html                página de alerta com pontos de atenção → avaliação ou seguir
  avaliacao.html             chat com 3 perguntas → "repensar" → continuar (senha) ou cancelar
  comprovante.html           transferência realizada: registra o pop-up de feedback pendente
  home.html                  mostra o pop-up de feedback pendente ao abrir
  feedback/                  pop-up de feedback: interface separada da integração com a API
                             (contrato e como trocar a tela em MVP/feedback/README.md)
```

### API REST (`X-API-Key`, JSON, OpenAPI em `/docs`)

| Rota | O que faz |
|---|---|
| `POST /v1/sessoes` | Recebe o Bloco 1 e devolve `sessao_id` e a 1ª pergunta |
| `POST /v1/sessoes/{id}/respostas` | Recebe `{pergunta_id, alternativa_id}` e devolve a próxima pergunta. Na 3ª resposta já calcula score e explicação e devolve `concluida`; em caso de coação, `coacao` |
| `GET /v1/sessoes/{id}/resultado` | Devolve `score_refinado`, `nivel_risco`, `explicacao_gerada` e `fonte_explicacao` |
| `POST /v1/sessoes/{id}/decisao` | Recebe `{decisao: "continuar" \| "cancelar"}`, o que o cliente fez depois do chat |
| `GET /v1/feedbacks/pendentes?cliente_id=…` | Transações que o cliente continuou e cujo pop-up de feedback ainda não apareceu |
| `POST /v1/sessoes/{id}/feedback/exibido` | Marca que o pop-up apareceu (não é perguntado de novo) |
| `POST /v1/sessoes/{id}/feedback` | Recebe `{feedback_cliente: "golpe" \| "nao_golpe" \| "sem_resposta"}` |
| `GET /saude` | Versões, se o Gemini está configurado e se o modo demo está ligado |

O `POST /v1/sessoes` também aceita `cliente_id` e `descricao_exibicao` (opcionais, usados pelo pop-up de feedback) e `nome_destinatario` (opcional, usado na pergunta de conferência do modo demo). No modo demo, o resultado traz `explicacao_topicos` (lista de `{tom, texto}`, com `**trechos**` a destacar); no modo real esse campo vem `null` e o texto está em `explicacao_gerada`. As perguntas chegam ao cliente sem multiplicadores nem flags internas. O MVP consome exatamente essa API pública, sem atalho interno.

## Base de dados (variáveis analisadas)

Cada linha da base é **uma sessão de triagem**, com **38 colunas** em 3 blocos. O esquema está em `servico/triagem/esquema.py` e os dados em `servico/dados/sintetico/{treino,validacao,teste}.csv`. A coluna "Modelo usa?" diz se a variável entra no classificador que calcula a probabilidade de golpe.

**Bloco 1: sinais da transação (18 colunas).** No mundo real vêm do modelo antifraude do banco; no MVP são simulados.

| Campo | O que é | Modelo usa? |
|---|---|---|
| `id_transacao` | Identificador da transação | Não (só identifica) |
| `timestamp_transacao` | Data e hora do Pix | Sim, a hora do dia |
| `valor_transacao` | Valor do Pix, em R$ | Sim |
| `valor_medio_historico_usuario` | Quanto o cliente costuma transferir | Sim |
| `desvio_valor_padrao` | Quanto o valor foge da média: (valor − média) / média | Sim |
| `destinatario_chave_pix_hash` | Chave do destinatário, anonimizada | Não (só identifica) |
| `tipo_chave_pix` | CPF, e-mail, telefone ou aleatória | Sim |
| `destinatario_novo` | Se é a primeira vez que o cliente paga essa pessoa | Sim |
| `idade_chave_pix_destinatario` | Há quantos dias a chave do destinatário existe | Sim |
| `horario_transacao_incomum` | Se o horário foge do padrão do cliente (ex.: madrugada) | Sim |
| `dispositivo_reconhecido` | Se o Pix saiu de um celular já conhecido | Sim |
| `velocidade_digitacao_atipica` | Digitação estranha, possível sinal de acesso remoto | Sim |
| `numero_transacoes_conta_24h` | Quantos Pix a conta fez nas últimas 24h | Sim |
| `canal_transacao` | App ou internet banking | Sim |
| `motivo_alerta_modelo_base` | Texto curto com o motivo do alerta | Não (vai só para o Gemini) |
| `fator_risco_principal` | O sinal que mais pesou no alerta (também guia a escolha das perguntas) | Sim |
| `fator_risco_secundario` | O segundo sinal que mais pesou (pode ser vazio) | Sim |
| `score_inicial_modelo_base` | Probabilidade de golpe dada pelo modelo antifraude, antes das perguntas | Sim |

**Bloco 2: perguntas e respostas (13 colunas).** Para cada pergunta N (1 a 3):

| Campo | O que é | Modelo usa? |
|---|---|---|
| `pergunta_N_id` | Qual das 30 perguntas do banco foi feita | Sim, junto com a resposta |
| `pergunta_N_dimensao` | Dimensão de risco da pergunta (P1 canal … P7 verificação) | Sim, contagem por dimensão |
| `pergunta_N_resposta` | Alternativa escolhida (a, b, c…) | Sim, junto com a pergunta |
| `pergunta_N_multiplicador` | Peso de risco da alternativa, usado só para gerar o gabarito sintético | **Não** (o modelo aprende os próprios pesos) |
| `sinalizador_coacao_fisica` | Se alguma resposta indicou ameaça física em andamento | Não (interrompe o fluxo e mostra a orientação de segurança) |

**Bloco 3: resultado e feedback (7 colunas).**

| Campo | O que é | Modelo usa? |
|---|---|---|
| `feedback_cliente` | Resposta do pop-up pós-transação: `golpe` (quer falar com o suporte), `nao_golpe` (era legítima) ou `sem_resposta` (fechou ou nunca respondeu; é o valor padrão) | **Não** (chega horas depois; serve para confirmar o desfecho no retreino) |
| `pontuacao_reconhecimento_padroes` | Quantas das 3 respostas mostram que o cliente reconhece o risco (0 a 3) | Sim |
| `score_refinado` | Probabilidade final calculada pelo modelo (saída) | Não (é o resultado) |
| `rotulo_real_golpe` | Gabarito: era golpe ou não | Não (é o que o modelo tenta acertar) |
| `rotulo_tipo_golpe` | Tipo de golpe (falsa central, WhatsApp clonado, venda falsa…) | Não |
| `explicacao_gerada` | Texto final mostrado ao cliente | Não (só log) |
| `usuario_seguiu_recomendacao` | Se o cliente seguiu a recomendação | Não (feedback de produto) |

**Como essas colunas viram entradas do modelo:** das 38 colunas, o classificador usa 25 (15 do Bloco 1, 9 das perguntas e respostas e a pontuação de reconhecimento), transformadas em 173 variáveis numéricas (`servico/triagem/features.py`):
- Os números passam por logaritmo, porque valores e idades de chave variam muito, e a hora vira uma posição num ciclo de 24h.
- As categorias (tipo de chave, canal, fatores de risco) viram colunas 0/1, uma por opção.
- As respostas viram 131 colunas 0/1, uma para cada combinação pergunta + alternativa do banco. Como a pergunta da posição 1 muda de sessão para sessão, o modelo olha "qual pergunta, qual resposta", e não "o que respondeu na posição 1".
- Mais 7 colunas com quantas perguntas foram feitas em cada dimensão.

## Métricas do modelo

Para regenerar esta seção, os gráficos e o relatório completo (`servico/relatorios/`):

```bash
cd servico && ../.venv/bin/python -m triagem.relatorio
```

<!-- METRICAS:INICIO -->
<!-- Seção gerada por `python -m triagem.relatorio` (a partir de servico/). Não edite à mão. -->

Avaliado em **1198 sessões de teste** que o modelo nunca viu (391 golpes, 32,6%), com **3 perguntas por sessão**. Modelo: `regressao_logistica`, versão `20260927122658`. O relatório completo está em [`servico/relatorios/metricas.md`](servico/relatorios/metricas.md).

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

A matriz soma 1198 e não 12.000 porque só usa o teste: avaliar com sessões que o modelo já viu no treino daria números otimistas demais. Todas as outras métricas saem dessas quatro contagens (por exemplo, recall = VP / (VP + FN)). A exceção são AUC, Brier e calibração, que usam a probabilidade diretamente.

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
- **Brier score (0,137)**: erro médio da probabilidade (0 é perfeito). Um modelo que sempre dissesse "32,6% de chance" teria 0,220. Importa porque a probabilidade é guardada na base e devolvida pela API (`score_refinado`); o MVP não a mostra ao cliente, mas outro sistema pode usá-la.
- **Calibração**: se o modelo diz 70%, cerca de 70% desses casos deveriam ser golpe. No gráfico, quanto mais perto da diagonal, mais confiável é a probabilidade devolvida pela API.

**Por que o limiar é 16,6% e não 50%?** O limiar é a probabilidade a partir da qual a transação vira alerta: acima dele, o chat mostra a mensagem "Você não gostaria de repensar sobre essa transação por alguns minutos?"; abaixo, "Não encontramos sinais fortes de golpe". Ele foi escolhido no conjunto de validação como o maior que ainda detecta pelo menos 90% dos golpes; no teste, com dados que o modelo nunca viu, o recall ficou em 86,7%, uma variação normal entre amostras. Abaixá-lo aumenta o recall e derruba a precisão; subi-lo faz o contrário (veja o gráfico do limiar e a coluna "Limiar 50%" da tabela). Como a transferência nunca é bloqueada, só há um convite a repensar, um falso alarme custa pouco e um golpe não detectado custa muito, então o limiar favorece o recall.
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
  - Não usa os multiplicadores nem `feedback_cliente`. As sessões com coação ficam fora do treino.
  - Comparei regressão logística e LightGBM, e a logística venceu na validação (o gerador é linear no logit). A calibração é de Platt.
  - O limiar é o maior que mantém recall ≥ 90% na validação.
  - A decisão usa a probabilidade sem corte. O `score_refinado` devolvido pela API tem piso 0,15 e teto 0,98, para nenhum sistema que o exiba comunicar certeza absoluta. O MVP não mostra o número ao cliente.
- **Métricas:** veja a seção [Métricas do modelo](#métricas-do-modelo), gerada pelo script `triagem/relatorio.py`.
- **Coação física:** a sessão é interrompida na hora e a API devolve uma orientação de segurança **fixa e revisada** (190, MED, banco), sem passar pelo Gemini. Numa situação de risco físico, esse texto não deve depender de rede nem da variação de um modelo generativo.
- **Log para retreino:** o SQLite (`servico/triagem.db`) guarda uma linha por sessão com as colunas do esquema, mais o status, as versões de modelo e de banco, a probabilidade interna, a decisão do cliente (`decisao_cliente`) e os horários do pop-up (`feedback_exibido_em`, `feedback_respondido_em`). O `feedback_cliente` é o primeiro indício do desfecho real. Quando o desfecho for confirmado (feedback mais confirmação do banco), basta preencher `rotulo_real_golpe` e `rotulo_tipo_golpe`, e as linhas passam a servir de dado real no mesmo formato do sintético. O retreino automático fica fora do escopo desta versão.
- **Feedback pós-transação:** na versão atual (demo), o pop-up é disparado pelo comprovante: aparece uma única vez depois de **qualquer transferência realizada**, com ou sem avaliação, e nunca depois de um cancelamento. A pendência fica no `localStorage` do navegador. Quando a transferência passou pela avaliação, a resposta também vai para a API. Para produção, a API já tem as rotas de pendências por cliente, com `FEEDBACK_ATRASO_MINUTOS` (ver `MVP/feedback/README.md`). Se o cliente fechar sem responder, fica `sem_resposta`: nada é suposto. No dataset sintético, `feedback_cliente` é simulado para todas as sessões (quem tem menos consciência de risco responde menos), só para testar o pipeline.
- **Tom do fim do chat:** o texto (Gemini ou template) cita os sinais que o próprio cliente contou, não mostra números nem porcentagens e termina convidando a uma pausa e a uma checagem por canal oficial. A probabilidade continua calculada e salva na base.

## Placeholders e limitações

- **Score inicial mockado:** `montarBloco1` em `MVP/triagem.js` simula o modelo antifraude de origem a partir do valor, de o destinatário ser novo e do horário. Para usar o modelo real, basta trocar o corpo dessa função mantendo o formato do objeto retornado.
- **Cliente fixo:** o MVP não tem login real, então todas as sessões usam `CLIENTE_ID = "cliente-demo-jose"` (em `MVP/triagem.js`). Em produção, esse id viria do login, para cada cliente ver só os pop-ups das transações dele.
- **Chave da API no navegador:** a chave fica visível em `MVP/triagem.js`. Serve para o protótipo, mas em produção a chamada passaria por um backend.
- **Dados sintéticos:** o dataset é inteiramente sintético (não existe base pública caso a caso de Pix). As métricas medem o quanto o modelo recupera o processo gerador, não o desempenho no mundo real.
- **Fontes usadas para o realismo:** Pizzolato et al., *A Taxonomy of Pix Fraud in Brazil* (arXiv:2511.20902), e o Observatório Lupa, *A Jornada dos Golpes*.
