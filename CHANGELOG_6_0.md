# Fratelli 6.0

- Corrigida dependência `bs4` no `requirements.txt`.
- Reestruturado o motor para separar evidência, cobertura, confiança, política e decisão.
- Pesquisa pública com fontes individuais e horário.
- Divergências entre fontes preservadas.
- Pesquisa de sócios por nome tratada como pista, não como prova de identidade.
- Regra de 25% para ausência de evidência.
- Simulação de pedido operacional.
- Histórico e auditoria persistidos em SQLite.
- Interface com logo Fratelli e sem número de versão no nome visual.
- Produto e unidades mantidos genéricos.

## Hotfix 6.0.1 — Streamlit import compatibility
- Corrigido o import de `engine` em `public_research.py` para funcionar quando o Streamlit executa `app.py` como módulo principal.
- Mantido fallback relativo para execução como pacote.
- Removidos caches de teste e arquivos temporários do pacote de publicação.
