# Auditoria dos fluxos operacionais

Esta auditoria foi feita sobre as rotas, serviços, modelos e templates existentes. Os números de cliques são estimativas do percurso mínimo, sem contar autenticação, e devem ser confirmados na validação com utilizadores.

## Preparar uma sessão

- Entrada: dashboard, calendário, microciclo ou plano semanal sincronizado.
- Percurso mínimo: abrir a sessão, guardar cabeçalho, adicionar exercícios, guardar desenhos e guardar reflexão.
- Problemas: a página concentra demasiadas decisões; `hora_inicio` existe na sessão e no plano; cada exercício é uma submissão independente; a biblioteca abre num modal separado.
- Reutilização: duplicar uma sessão completa e copiar exercícios/blocos de outra sessão.

## Consultar o próximo treino

- Entrada: centro de ação do dashboard ou calendário operacional.
- Percurso mínimo: um clique para abrir a sessão.
- Problemas: a ação é clara para estados da sessão, mas não cobre plano incompleto, convocatória pendente ou conflito de espaço.
- Reutilização: o mesmo item de agenda deve servir dashboard, calendário, microciclo e plano semanal.

## Registar presenças

- Entrada: ação “Registar sessão” ou ligação de assiduidade no plano.
- Percurso mínimo: abrir a página e submeter todos os estados.
- Problemas corrigidos nesta fase: a página já não cria faltas apenas por ser aberta; existe agora “Por registar”; há ações rápidas para todos presentes ou limpar estados.
- Reutilização: aplicar o mesmo componente a sessões, jogos e relatórios.

## Fechar uma sessão

- Entrada: plano, assiduidade ou dashboard.
- Percurso mínimo: atualizar estado, guardar assiduidade e guardar reflexão.
- Problemas: o estado é alterado por um seletor genérico; ainda falta checklist de fecho com plano, presenças, RPE e reflexão.
- Reutilização: a próxima ação deve ser a mesma em todos os pontos de entrada.

## Criar convocatória

- Entrada: detalhe do jogo.
- Percurso mínimo: selecionar jogadoras, preencher encontro e guardar.
- Problemas: a gravação apaga e recria todos os convocados; não existem estados individuais nem duplicação da convocatória anterior.
- Reutilização: copiar convocatória de jogo anterior da mesma equipa.

## Planear uma semana

- Entrada: planeamento mensal ou navegação direta.
- Percurso mínimo: abrir/criar plano semanal, criar eventos, atribuir espaços, sincronizar e publicar.
- Problemas: formulários repetem equipa, espaço, data e horários; conflitos aparecem no detalhe, mas não existe fluxo de resolução dedicado.
- Correção aplicada nesta fase: a página de edição semanal volta a devolver corretamente o template.

## Consultar um jogador

- Entrada: plantel, dashboard ou lista global.
- Percurso mínimo: abrir a ficha; os dados de evolução já estão integrados.
- Problemas: a ficha é extensa e mistura acompanhamento desportivo, secretaria, documentos e contactos.
- Reutilização: separar leitura rápida, evolução e secretaria sem duplicar os dados.

## Exportar um PDF

- Entrada: cada detalhe tem pelo menos uma exportação relevante.
- Problemas: existem templates A4, mas com estilos, cores, margens e cabeçalhos diferentes; falta uma camada comum de identidade e validação visual.
- Reutilização: preparar dados uma vez e usar os mesmos componentes para HTML, impressão e PDF.
