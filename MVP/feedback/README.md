# Pop-up de feedback pós-transação

Quando o cliente passa pela avaliação da ia.itaú e decide **continuar** com o Pix, na próxima vez que ele abrir o app aparece um pop-up perguntando se aquela transação era golpe. A resposta vai para a base (coluna `feedback_cliente`) e serve para confirmar desfechos reais no retreino do modelo.

Esta pasta separa a **interface** da **integração com a API**. Para mudar o visual ou criar uma tela nova, basta mexer nos dois primeiros arquivos.

| Arquivo | Responsabilidade | Chama a API? |
|---|---|---|
| `feedback-popup.css` | Só estilo (classes com prefixo `fb-`) | Não |
| `feedback-popup.js` | Só interface: monta o pop-up e avisa qual foi a resposta | Não |
| `feedback.js` | Busca pendências, marca como exibido, mostra o pop-up e envia a resposta | Sim, via `../triagem.js` |

A página que usa o pop-up (hoje `MVP/home.html`) inclui, nesta ordem, `app.js`, `triagem.js`, `feedback/feedback-popup.js` e `feedback/feedback.js`, mais o CSS. Depois chama `verificarFeedbackPendente()`.

## Contrato da interface

Para trocar a tela, mantenha esta função com a mesma assinatura:

```js
mostrarPopupFeedback({ descricao, aoResponder })
```

- `descricao`: texto da transação vindo da API, por exemplo `"Pix de R$ 1.000,00 para Lucas"`.
- `aoResponder(resposta)`: chame **uma única vez**, com um destes valores:

| Valor | Quando | Texto atual do botão |
|---|---|---|
| `"golpe"` | Cliente diz que era golpe e quer falar com o suporte | "Sim, gostaria de entrar em contato com o suporte" |
| `"nao_golpe"` | Cliente diz que a transação era legítima | "Não, era uma transação legítima" |
| `"sem_resposta"` | Cliente fechou o pop-up (✕, Esc ou clique fora) | — |

O que acontece depois do clique (a tela de confirmação do suporte, por exemplo) é decisão só da interface. A API não precisa saber.

## Contrato da API

Todas as rotas usam o header `X-API-Key` e JSON. A documentação interativa fica em `http://localhost:8000/docs`, na seção "decisão e feedback".

**1. Ao final do chat, registrar a decisão do cliente** (feito por `avaliacao.html`):
```http
POST /v1/sessoes/{sessao_id}/decisao
{ "decisao": "continuar" }          // ou "cancelar"
```
Só sessões com `"continuar"` geram pop-up. Para aparecer no pop-up, a sessão precisa ter sido criada com `cliente_id` e `descricao_exibicao` no `POST /v1/sessoes` (o `triagem.js` já envia os dois).

**2. Ao abrir o app, buscar pendências:**
```http
GET /v1/feedbacks/pendentes?cliente_id=cliente-demo-felipe
→ 200 [
    { "sessao_id": "…", "descricao_exibicao": "Pix de R$ 1.000,00 para Lucas", "concluida_em": "2026-09-27T14:02:11+00:00" }
  ]
```
Devolve as sessões em que o cliente continuou, concluídas há pelo menos `FEEDBACK_ATRASO_MINUTOS` (configurado em `servico/.env`; 0 na demo) e cujo pop-up ainda não foi exibido. A mais antiga vem primeiro. O `feedback.js` mostra só uma por visita.

**3. Ao exibir o pop-up, marcar como exibido:**
```http
POST /v1/sessoes/{sessao_id}/feedback/exibido      → 204
```
Assim a transação não volta a aparecer, mesmo que o cliente feche o app sem clicar em nada. Nesse caso a coluna fica `sem_resposta`, que é o valor padrão.

**4. Quando o cliente responder, enviar a resposta:**
```http
POST /v1/sessoes/{sessao_id}/feedback
{ "feedback_cliente": "golpe" }     // "golpe" | "nao_golpe" | "sem_resposta"
→ 204   (valor fora da lista → 422)
```

## Como o dado fica na base

| Coluna | Valores | Observação |
|---|---|---|
| `feedback_cliente` | `golpe`, `nao_golpe`, `sem_resposta` | Começa como `sem_resposta`; nada é suposto se o cliente não responder |
| `feedback_exibido_em` | data e hora | Quando o pop-up apareceu |
| `feedback_respondido_em` | data e hora | Quando o cliente respondeu ou fechou |
| `decisao_cliente` | `continuar`, `cancelar` | O que ele fez ao final do chat |

O `feedback_cliente` **não** é entrada do modelo: chega horas depois e é usado para conferir o desfecho no retreino.
