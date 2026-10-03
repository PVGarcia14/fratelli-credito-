# Changelog — Fratelli B2B Crédito

## 6.0.4
- QSA (sócios/administradores) passa a ser extraído automaticamente das fontes públicas que o parser conseguir identificar.
- Nome e qualificação do sócio/administrador aparecem automaticamente após a análise do CNPJ.
- Pesquisa judicial automática no Jusbrasil para o CNPJ e para cada sócio/administrador identificado.
- A interface diferencia: processo encontrado, acesso público indisponível e ausência de resultado verificável.
- Incluído link direto para consulta no Jusbrasil.
- Pesquisa manual de nomes continua disponível como complemento.
- Não são feitas acusações nem conclusões automáticas de que um processo é “prejudicial”; a tela apresenta a evidência para análise.
- Mantida a lógica de limite e conversão da 6.0.3.


## 6.0.5
- Resultado da simulação passa a exibir explicitamente CRÉDITO APROVADO ou CRÉDITO NÃO APROVADO AUTOMATICAMENTE.
- Incluído fluxo de solicitação de aprovação manual para pedidos fora dos parâmetros automáticos.
- Botão de e-mail com mensagem pré-preenchida para o responsável configurado.
- Botão de WhatsApp com mensagem pré-preenchida para o responsável configurado.
- Inclusão de registro da solicitação no módulo de auditoria.
- Nenhum envio é realizado automaticamente; o usuário confirma o envio no aplicativo escolhido.
- Mantido o motor de risco, limite, pesquisa pública, QSA, pesquisa judicial e simulador da 6.0.4.

## 6.0.7
- Corrigida a simulação manual por caixas para calcular imediatamente caixas, unidades, bruto, desconto e líquido.
- Quantidade inicial de caixas passa a ser 1 para tornar o cálculo visível sem configuração adicional.
- Exibe preço unitário e valor de uma caixa antes da simulação.
- O cálculo do pedido é independente da aprovação: mesmo com crédito aprovado igual a zero, o sistema calcula o valor e informa separadamente que não há autorização.
- Comparação com o crédito efetivamente liberado usa o valor líquido do pedido.
- Mensagens distintas para preço não configurado, crédito zero, pedido dentro do limite e excesso.
