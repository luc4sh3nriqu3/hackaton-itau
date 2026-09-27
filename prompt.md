# Prompt para Claude Code — Sistema de Triagem Educativa de Golpes do Pix

## Como usar este documento
Cole este documento inteiro como prompt inicial pro Claude Code. Ele descreve o projeto completo: dataset sintético, os dois modelos, a integração com Gemini e a API REST. **Revise a seção "Interpretação do fluxo" antes de enviar** — é a parte que tinha mais ambiguidade na conversa que originou este prompt.

## Objetivo do projeto
Construir um serviço que: recebe uma transação Pix com uma probabilidade inicial de golpe (calculada por um modelo já existente, fora do escopo deste projeto); conduz o usuário por um questionário educativo de 10 perguntas de múltipla escolha, sorteadas adaptativamente de um banco maior de perguntas; usa as respostas para refinar essa probabilidade; ao final coleta o veredito do próprio usuário sobre se aquilo é golpe; gera um texto explicativo personalizado via API do Gemini; expõe tudo por uma API REST que qualquer sistema possa consumir; e integra esse serviço ao MVP de app de banco já existente neste repositório, na pasta `MVP`.

## Etapa 0 — explorar o MVP antes de escrever qualquer código
Antes de criar a base de dados ou os modelos, explore a pasta `MVP` e reporte um resumo curto do que encontrar:
- Stack usado (frontend, backend se houver, linguagem, framework)
- Se é só frontend com dados mockados ou se já existe alguma API/backend real
- Onde no fluxo existe (ou poderia existir) uma tela de transferência Pix — é ali que a integração da seção 6 vai entrar
- Qualquer convenção de código/estilo do projeto que valha seguir pra manter consistência

Se estiver rodando de forma não-interativa, tome a decisão mais razoável com base no que encontrar e documente as escolhas no README, em vez de travar esperando confirmação humana.

## Interpretação do fluxo (confirme antes de prosseguir)
- As 10 perguntas não são só coleta de contexto: cada uma ensina um princípio de reconhecimento de golpe (por que golpistas preferem certos canais, por que pedem sigilo etc.) ao mesmo tempo em que extrai sinal sobre a situação específica do usuário.
- Ao final, o usuário dá seu próprio veredito (golpe / não é golpe / não tenho certeza) sobre a situação dele. Esse veredito entra como mais um sinal de entrada pro classificador final, junto com o quanto o usuário demonstrou reconhecer os padrões de risco ao longo das 10 perguntas (uma medida de confiabilidade desse veredito).
- Esse par (respostas às perguntas + veredito do usuário), agregado ao longo do tempo e comparado com o desfecho real quando disponível, é o que permite recalibrar o classificador base periodicamente — não dentro de uma sessão, e sim como insumo pra retreinamento futuro. Arquitete o logging pensando nisso, mesmo que o retreinamento automático fique fora do escopo desta primeira versão.
- Se qualquer resposta sinalizar coação física em andamento (sequestro relâmpago, ameaça presencial), o fluxo educativo deve ser interrompido e substituído por orientação de segurança imediata — não continuar coletando respostas pra pontuação.

## O que construir — 6 componentes
1. Base de dados sintética
2. Modelo seletor de pergunta
3. Modelo classificador final (treinado, não regra fixa)
4. Integração com a API do Gemini
5. API REST
6. Integração dessa API com o MVP de app de banco já existente no repositório

---

## 1. Base de dados sintética

### 1.1 Abordagem
Gerar inteiramente por código/LLM — não depender de nenhuma base real de terceiros (já verificamos: não existe base pública, real, caso-a-caso de transação Pix; sigilo bancário e LGPD impedem isso). O importante é realismo estatístico: as distribuições e correlações abaixo devem refletir os padrões documentados nas fontes da seção 1.4, não ruído aleatório.

Gerar entre 8.000 e 20.000 sessões completas (situação + 10 perguntas/respostas + veredito + rótulo). Split 80/10/10 treino/validação/teste. Desbalanceamento moderado (20-40% golpe), não extremo — o cenário de entrada já é pré-filtrado por um score inicial alto, então não faz sentido simular 0,1% de golpe como em datasets de cartão de crédito genéricos.

### 1.2 Schema completo (66 colunas)

**Bloco 1 — sinal-base da transação (18 campos, sintéticos com distribuição realista):**

| Campo | Como gerar |
|---|---|
| `id_transacao` | UUID sequencial |
| `timestamp_transacao` | Data/hora aleatória; concentrar em horário comercial, com cauda em horários atípicos (madrugada) quando `rotulo_real_golpe = true` |
| `valor_transacao` | Log-normal, mediana ~R$150; golpes tendem a valores mais altos ou redondos (R$500, R$1000) |
| `valor_medio_historico_usuario` | Por perfil de usuário simulado (perfis com médias entre R$50 e R$5000) |
| `desvio_valor_padrao` | Calculado a partir dos dois campos acima |
| `destinatario_chave_pix_hash` | UUID |
| `tipo_chave_pix` | Categórico: CPF, e-mail, telefone, aleatória — distribuição realista de uso no Brasil |
| `destinatario_novo` | Booleano, correlacionado positivamente com `rotulo_real_golpe` |
| `idade_chave_pix_destinatario` | Dias desde o cadastro da chave; golpes tendem a chaves mais recentes |
| `horario_transacao_incomum` | Booleano, derivado do timestamp vs. padrão do usuário |
| `dispositivo_reconhecido` | Booleano; golpes tipo "mão fantasma" (acesso remoto) tendem a `false` |
| `velocidade_digitacao_atipica` | Booleano/score; correlacionado com golpes de acesso remoto |
| `numero_transacoes_conta_24h` | Poisson; cauda mais alta em cenário de esvaziamento de conta |
| `canal_transacao` | Categórico: app, internet banking |
| `motivo_alerta_modelo_base` | Texto curto livre (ex: "destinatário novo + valor atípico") — usado só pro Gemini, não pra lógica do seletor |
| `fator_risco_principal` | **Categórico, obrigatório** — qual campo deste bloco mais contribuiu pro `score_inicial_modelo_base`. Um de: `valor_atipico`, `destinatario_novo_ou_desconhecido`, `dispositivo_nao_reconhecido`, `velocidade_digitacao_atipica`, `horario_incomum`, `chave_pix_recente`, `volume_transacoes_24h_alto`. É o que direciona a seleção de pergunta (ver seção 2) |
| `fator_risco_secundario` | Mesmo domínio do campo acima, opcional (pode ser nulo) — segundo maior contribuinte |
| `score_inicial_modelo_base` | Probabilidade de entrada; enviesar pra faixa 0,55–0,90 (cenário "borderline", que é o caso de uso real do sistema) |

**Bloco 2 — perguntas e respostas (10 rodadas, não mais 3):**
Para cada rodada N de 1 a 10: `pergunta_N_id`, `pergunta_N_dimensao`, `pergunta_N_resposta`, `pergunta_N_multiplicador` (40 campos).
Mais: `sinalizador_coacao_fisica` (booleano, override de segurança, fora da lógica de score).

**Bloco 3 — veredito e saída (7 campos):**

| Campo | Descrição |
|---|---|
| `veredito_usuario` | Resposta final do próprio usuário: golpe / não é golpe / não tenho certeza |
| `pontuacao_reconhecimento_padroes` | 0–10: quantas das 10 perguntas o usuário respondeu de um jeito consistente com reconhecer o risco. Vira peso de confiabilidade do veredito dele |
| `score_refinado` | Probabilidade final, saída do componente 3 |
| `rotulo_real_golpe` | Rótulo de verdade usado pra treinar (só existe no dataset sintético/rotulado — em produção real não existe até confirmação externa) |
| `rotulo_tipo_golpe` | Categoria (opcional): falsa_central, mao_fantasma, whatsapp_clonado, falsa_taxa, sequestro_pix, venda_falsa, outro |
| `explicacao_gerada` | Texto do Gemini — não entra no treino, é só logging |
| `usuario_seguiu_recomendacao` | Opcional, feedback de produto |

Total: 18 + 40 + 1 + 7 = **66 colunas**.

### 1.3 Banco de perguntas
Expandir as 7 dimensões de risco abaixo para um banco de **28 a 35 perguntas candidatas** (4-5 variantes didáticas por dimensão). Cada variante deve: ensinar um princípio específico de reconhecimento de golpe do Pix; pertencer à mesma dimensão de risco e à mesma faixa de multiplicador da dimensão-base; ter de 3 a 6 alternativas.

As 7 dimensões-base e seus multiplicadores (usar como estrutura geradora dos rótulos sintéticos — ver 1.1 — e como faixa de referência pras variantes novas):

| Dimensão | Amplitude de multiplicador |
|---|---|
| P1 — Canal de contato | ×0,25 a ×3,0 |
| P2 — O que foi pedido | ×0,4 a ×5,0 |
| P3 — Identidade alegada | ×0,3 a ×3,0 |
| P4 — Pressão psicológica | ×0,5 a ×3,2 |
| P5 — Histórico com o destinatário | ×0,3 a ×2,2 |
| P6 — Como o contato começou | ×0,4 a ×2,3 |
| P7 — Verificação independente já feita | ×0,2 a ×3,5 |

Exemplo de variante didática pra P1 (use este padrão pras demais): em vez de só "de qual canal veio o contato?", framear como "Golpistas preferem WhatsApp porque a plataforma permite trocar de número rapidamente e imitar contatos salvos. No seu caso, o contato veio de um número novo, de um contato salvo com comportamento diferente, por ligação, SMS/e-mail, rede social, ou você mesmo verificou pelo canal oficial do banco?" — mesma dimensão, mesmas alternativas de base, só com a camada didática antes da pergunta.

### 1.4 Fontes de referência para realismo
Usar como base factual pros padrões de golpe simulados (nomes de golpes, proporções, canais):
- "A Taxonomy of Pix Fraud in Brazil" (Pizzolato et al., UNIPAMPA, arXiv:2511.20902) — revisão de literatura + entrevistas com setor bancário.
- Relatório "A Jornada dos Golpes" (Observatório Lupa) — WhatsApp em ~65% dos golpes analisados; 74% usam nome de marca/instituição conhecida; 71% prometem vantagem financeira; um terço exige pagamento exclusivo via Pix.
- Padrões nomeados a incluir no `rotulo_tipo_golpe`: golpe da falsa central de atendimento, golpe da mão fantasma (acesso remoto), golpe do WhatsApp clonado, golpe da falsa taxa/imposto sobre o Pix, sequestro do Pix (coação física), golpe do falso leilão/venda em marketplace.

---

## 2. Modelo seletor de pergunta

- Critério base: ganho de informação esperado (Expected Value of Information / Bayesian Experimental Design), aproximado pela amplitude log dos multiplicadores de cada dimensão (tabela 1.3).
- **Viés pelo maior fator de risco (requisito de produto):** as perguntas selecionadas devem ter mais chance de pertencer à dimensão ligada ao `fator_risco_principal` da transação — não é coleta de contexto genérica, é foco no que mais pesou no alerta. Ex.: se `fator_risco_principal = valor_atipico`, a maioria das 10 perguntas da sessão deve vir de P2 e P5 (ver mapa abaixo), não distribuídas igualmente entre as 7 dimensões.

  Mapa `fator_risco_principal` → dimensões priorizadas:

  | Fator de risco | Dimensões priorizadas |
  |---|---|
  | `valor_atipico` | P2 (o que foi pedido), P5 (histórico com o destinatário) |
  | `destinatario_novo_ou_desconhecido` | P5 (histórico), P6 (como começou), P3 (identidade alegada) |
  | `dispositivo_nao_reconhecido` | P7 (verificação independente), P1 (canal) |
  | `velocidade_digitacao_atipica` | P2 (pedido — instalar app/acesso remoto), P7 (verificação) |
  | `horario_incomum` | P4 (pressão psicológica), P1 (canal) |
  | `chave_pix_recente` | P3 (identidade alegada), P6 (como começou) |
  | `volume_transacoes_24h_alto` | P2 (pedido), P4 (pressão) |

- Fórmula de prioridade por dimensão, usada como **peso de um sorteio ponderado sem reposição** (não um ranking determinístico top-10 — isso preserva variedade entre sessões com o mesmo fator de risco, evitando repetir sempre as mesmas 10 perguntas):

  `prioridade(dimensão) = amplitude_log(dimensão) × boost_fator_risco(dimensão) × [ainda não perguntada nesta sessão]`

  onde `boost_fator_risco` = 2,0 se a dimensão está no mapa de `fator_risco_principal`; 1,3 se está no mapa de `fator_risco_secundario`; 1,0 caso contrário.

- Cobrir o máximo de dimensões distintas possível antes de repetir alguma, mesmo com o viés acima — o boost aumenta a chance, não garante 10 perguntas da mesma dimensão.
- Pode ser implementado como regra determinística com sorteio ponderado (sem precisar de modelo treinado à parte) para esta primeira versão; documentar como módulo separado e substituível caso depois se queira um agente de LLM fazendo essa escolha de forma mais adaptativa.

## 3. Modelo classificador final

- É um modelo treinado de verdade (ex: gradient boosting — XGBoost/LightGBM, ou regressão logística como baseline), não os multiplicadores fixos hardcoded. Os multiplicadores da seção 1.3 servem só pra gerar o processo de rotulagem sintética (o "gerador de verdade" que o modelo vai aprender a aproximar) — o modelo em produção deve reaprender seus próprios pesos a partir dos dados sintéticos, o que permite generalizar pra combinações de respostas não previstas manualmente.
- Features de entrada: todo o Bloco 1 + as 10 respostas do Bloco 2 (dimensão + resposta, one-hot ou embedding) + `pontuacao_reconhecimento_padroes`.
- Não usar `veredito_usuario` como feature do classificador principal (evita que o modelo apenas copie o palpite do usuário) — logar separadamente pra análise de concordância humano-modelo e pro circuito de melhoria contínua mencionado na interpretação do fluxo.
- Avaliação: AUC-ROC, precisão/recall com foco em recall (custo de falso negativo aqui é alto), calibração de probabilidade (Brier score) já que o produto final mostra uma probabilidade ao usuário.
- Aplicar teto/piso na saída (ex: 0,15 a 0,98) pra nunca comunicar certeza absoluta.

## 4. Integração com a API do Gemini

- Entrada do prompt pro Gemini: situação original, `motivo_alerta_modelo_base`, as 10 perguntas e respostas, `veredito_usuario`, `score_refinado`.
- Tarefa: gerar um texto curto, em português, explicando de forma personalizada e não alarmista por que a situação foi (ou não) classificada como provável golpe, citando os sinais concretos que o próprio usuário informou (não genérico), e terminando com uma recomendação de ação clara.
- Comportamento de segurança: se `sinalizador_coacao_fisica = true`, o Gemini não deve gerar o texto educativo padrão — deve gerar uma orientação de segurança imediata (contato com 190/polícia), sem o tom didático do restante do fluxo.
- Configuração: chave da API do Gemini via variável de ambiente, nunca hardcoded.

## 5. API REST

Endpoints sugeridos (autenticação por API key, já que "qualquer sistema" deve poder consumir):

- `POST /v1/sessoes` — inicia sessão com a situação inicial (campos do Bloco 1 + `score_inicial_modelo_base`) → retorna `sessao_id` + primeira pergunta
- `POST /v1/sessoes/{id}/respostas` — envia resposta da pergunta atual → retorna a próxima pergunta ou, após a 10ª, sinaliza que está pronto pro veredito
- `POST /v1/sessoes/{id}/veredito` — envia `veredito_usuario` → dispara o cálculo final
- `GET /v1/sessoes/{id}/resultado` — retorna `score_refinado` + `explicacao_gerada`
- Formato: JSON em todas as rotas; documentar com OpenAPI/Swagger.

## 6. Integração com o MVP

### 6.1 Onde plugar
No fluxo de transferência Pix do MVP, no momento da confirmação — antes de a transferência ser efetivada na simulação. Se esse fluxo ainda não existir no MVP, criar uma tela mínima de "nova transferência Pix" só o suficiente pra demonstrar a integração de ponta a ponta.

### 6.2 O score inicial é mockado dentro do MVP
`score_inicial_modelo_base` e os demais campos do Bloco 1 vêm, no mundo real, de um modelo de detecção já existente e fora do escopo deste projeto. Como esse modelo não existe dentro do MVP, simule esses valores com uma heurística simples (ex: função leve sobre valor da transferência e se o destinatário é novo) só pra ter algo plausível alimentando a nova API. Deixar isso documentado como placeholder no código, de forma clara o suficiente pra trocar por um modelo real depois sem precisar reescrever a integração.

### 6.3 Fluxo de integração
1. Usuário confirma uma transferência Pix na tela do MVP.
2. MVP monta o payload do Bloco 1 (mockado, ver 6.2) e chama `POST /v1/sessoes`.
3. MVP renderiza a pergunta retornada como um passo/modal dentro do fluxo de confirmação existente, reaproveitando os componentes visuais já usados no MVP.
4. A cada resposta, MVP chama `POST /v1/sessoes/{id}/respostas` e renderiza a próxima pergunta.
5. Após a 10ª resposta, MVP pergunta o veredito do próprio usuário e chama `POST /v1/sessoes/{id}/veredito`.
6. MVP chama `GET /v1/sessoes/{id}/resultado` e mostra `explicacao_gerada` + `score_refinado` antes de liberar a confirmação final da transferência.
7. Decisão de produto: não bloquear a transferência automaticamente mesmo com score alto — mostrar um aviso claro e deixar o usuário decidir se quer prosseguir, cancelar, ou revisar. Se `sinalizador_coacao_fisica = true`, substituir esse passo pela orientação de segurança imediata, sem o restante do fluxo educativo.

### 6.4 Consistência
Consumir exatamente a mesma API pública do componente 5, sem atalho interno — isso valida que a API desenhada pra "qualquer sistema consumir" funciona de verdade no primeiro consumidor real dela.

---

## Entregáveis esperados
- [ ] Resumo da exploração do MVP (Etapa 0) documentado no README
- [ ] Script de geração do dataset sintético (66 colunas, 8-20k sessões, splits salvos)
- [ ] Banco de 28-35 perguntas didáticas (arquivo separado, versionável)
- [ ] Seletor de pergunta (regra determinística com sorteio ponderado, documentada)
- [ ] Classificador treinado + métricas de avaliação + calibração
- [ ] Módulo de integração com Gemini (com tratamento do caso de coação física)
- [ ] API REST com os 4 endpoints, documentação OpenAPI, testes básicos
- [ ] Tela de transferência Pix do MVP integrada ao fluxo de 10 perguntas + veredito + resultado, consumindo a API REST acima
- [ ] Heurística mock do score inicial claramente documentada como placeholder no código do MVP
