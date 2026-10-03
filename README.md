# Fratelli B2B Crédito 6.0.9

6.0.9 adds company age/status derivation, hardened location parsing, a Google Maps location link, and optional display of publicly exposed image candidates.

## Location
The Google Maps button is generated from the public cadastral address. A Street View/facade image is not fabricated; when a public source exposes an image URL it may be displayed, otherwise the interface asks the analyst to open Maps and verify the physical location.

# Fratelli B2B Crédito 6.0.6

Motor B2B genérico de análise de crédito com pesquisa pública, evidências, score, limite, conversão em caixas/unidades, composição automática de produtos e pesquisa judicial.

## Onde alterar os produtos
No arquivo `app.py`, procure `PRODUCT_CONFIG`. Ali ficam os nomes, preços unitários e unidades por caixa dos três produtos configuráveis.

## Onde alterar as condições comerciais
No mesmo bloco, procure `COMMERCIAL_TIERS`. A interface permite selecionar somente uma condição por vez e ajustar faixa e desconto.

## Composição automática
A 6.0.6 usa somente o crédito efetivamente liberado (`dec["approved"]`) para gerar uma sugestão. A sugestão pode variar aleatoriamente e nunca ultrapassa o crédito.

## Execução
```bash
pip install -r requirements.txt
streamlit run app.py
```

### 6.0.8 — fluxo de simulação
A solicitação de aprovação manual é condicional ao valor informado na simulação: somente aparece quando `valor_simulado > valor_aprovado_na_decisao`. O campo inicia em R$ 0,00 e não exibe alerta de aprovação manual na abertura.


## 6.1.0 — QSA e pesquisa judicial automática

O QSA é extraído automaticamente das fontes públicas que o sistema conseguir consultar. A documentação oficial do governo informa que a consulta de CNPJ inclui o Quadro de Sócios e Administradores (QSA).

Para consulta judicial estruturada automática do Jusbrasil, a versão 6.1.0 aceita a variável/secret `JUSBRASIL_API_KEY`. Sem essa credencial autorizada, o sistema não faz scraping de área protegida nem afirma ausência de processos; a pesquisa pública fica apenas como descoberta/evidência.

No Streamlit Cloud, configure em Settings → Secrets:

```toml
JUSBRASIL_API_KEY = "sua_chave"
```


## 6.1.2 — composição automática
A tela operacional não exige que o usuário monte o pedido. O sistema usa `dec["approved"]` e `suggest_automatic_mix()` para gerar automaticamente uma composição de caixas dentro do crédito. A faixa comercial é determinada pela quantidade total de unidades.

Os produtos continuam configuráveis em `PRODUCT_CONFIG` no `app.py`; a interface administrativa fica recolhida durante a operação.
