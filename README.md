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
