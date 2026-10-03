# Fratelli — Motor B2B de Crédito

Aplicação Streamlit de análise de crédito empresarial, neutra em relação ao produto vendido.

## Corrige o erro `ModuleNotFoundError: bs4`
O `requirements.txt` declara explicitamente `beautifulsoup4`, que fornece o módulo `bs4` usado pela aplicação.

## Execução
```bash
pip install -r requirements.txt
streamlit run app.py
```

## O que faz
- valida CNPJ localmente;
- pesquisa páginas públicas sem API de crédito;
- extrai dados cadastrais quando as páginas respondem;
- mostra fontes e divergências;
- pesquisa nomes publicamente como pistas, sem atribuir automaticamente homônimos;
- score 0–100;
- 25% da pontuação máxima quando falta evidência;
- cobertura e confiança separadas;
- política de limite por score;
- pedido solicitado x limite;
- simulação funcional;
- histórico e auditoria SQLite;
- não trata ausência de resultado como prova de ausência de dívida/processo;
- não acessa bases privadas sem autorização.

## Limitações
Sites públicos podem bloquear automação, mudar HTML ou exigir interação. Nesses casos a fonte aparece como "Sem resposta" e o sistema não inventa o dado.
