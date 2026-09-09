# Revisao da plataforma - 9 setembro 2026

## Alteracoes aplicadas

- Dashboard do treinador: acessos explicitos a preparar treino, Playbook, competicao e analise integrada. Presencas continuam numa acao direta; exportacao de dados passa para uma acao secundaria, sem eliminar a funcionalidade.
- Navegacao: analise acessivel mesmo sem equipa selecionada; destinos de planeamento explicitos; distincao entre registar presencas e consultar o relatorio; remocao de entradas repetidas e de seccoes vazias.
- Identidade: barra lateral neutra com acentos da cor do clube, foco visivel, identificacao unica da pagina ativa e controlos mais adequados ao toque.
- Studio: ferramentas numa linha propria em desktop; controlos de velocidade e numero do jogador disponiveis em mobile; instrucoes da animacao separadas do campo, sem o tapar.
- Animacao: leitura de 700 ms e movimento de 850 ms, velocidade inicial 1,25x (560 e 680 ms efetivos). Mantem o ciclo desenho -> movimento sem riscos -> desenho seguinte.
- Reproducao: trajetorias pre-calculadas, interpolacao suavizada, sem recriar o canvas a cada fotograma; pausa, retoma, procura e mudanca de velocidade sem reiniciar o relogio. Fechar o dialogo ou ocultar a pagina suspende a animacao.
- Gravacao: debounces e filas independentes por cena, incluindo instrucoes; revisoes sucessivas ordenadas; aviso de alteracoes pendentes ao sair; tentativa manual apos erro. Respostas HTML/redirects de login nao contam como gravacao bem-sucedida.
- Desenho: jogadores sobre os tracos de forma consistente no editor, miniaturas e animacao. Atalhos de edicao nao alteram o desenho por tras de um dialogo aberto.
- Separadores: fragmentos de URL invalidos deixam de interromper a inicializacao.

## Verificacao

- `node --test frontend/tests/playbook-studio.test.cjs`: 13 testes passaram. Geometria, drible curvo, lancamento, ciclo da animacao, procura para tras, relogio, concorrencia de gravacoes e respostas invalidas.
- `python -m pytest tests/test_sidebar_design.py --noconftest -q` em backend: 5 testes passaram; sem carregar fixtures de base de dados.
- 140 templates Jinja analisados sem erros de sintaxe.
- `node --check` nos scripts alterados e `git diff --check` sem erros.
- Ensaio visual no navegador a 1280x720 e 390x844, com dados sinteticos: dashboard, menu lateral, Studio e controlos de reproducao. Sem overflow horizontal no ensaio mobile. Sem erros de consola observados no Studio.
- Servidor de ensaio reutilizavel: `venv/Scripts/python.exe frontend/tests/preview_server.py`; serve apenas templates e assets locais, com dados ficticios em memoria, sem importar a aplicacao nem a base de dados. Rotas `/studio` e `/dashboard`, porta 8765.

## Limites e trabalho ainda necessario

- A execucao geral de `pytest tests -q --tb=short` terminou com 235 testes aprovados, 78 falhados e 4 erros. Entre os problemas observados estao fixtures de login do coordenador e testes que ainda esperam a antiga navegacao por cabecalho. As restantes falhas nao foram todas diagnosticadas ou corrigidas nesta revisao.
- A suite existente depende da base configurada e de contas de teste. Deve ser isolada numa base descartavel antes de se usar como criterio de publicacao integral. Nao se alteraram passwords ou permissoes para contornar falhas.
- Nao se certificam todos os percursos, perfis ou modulos como livres de erros. Esta revisao concentra as correcoes em navegacao partilhada, dashboard e Playbook Studio.
- O ensaio mobile foi feito no navegador com viewport reduzido, nao num iPad fisico. Apple Pencil e desempenho em hardware real continuam por verificar.
- A aceleracao aplica-se a pre-visualizacao da jogada; nao foi introduzido um novo exportador MP4.
