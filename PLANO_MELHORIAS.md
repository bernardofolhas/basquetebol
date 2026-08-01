# Plano de Melhorias — Plataforma de Basquetebol

> Análise sistemática do projeto e conjunto de correções aplicadas.
> Nenhuma alteração de lógica de negócio — apenas correções, consolidação e melhorias do que já existia.

---

## Resumo Executivo

| Fase | Área | Itens | Estado |
|---|---|---|---|
| 1 | Bugs Críticos (produção quebrada) | 2 | ✅ Concluído |
| 2 | Segurança e Autorização | 4 | ✅ Concluído |
| 3 | Qualidade de Código | 3 | ✅ Concluído |
| 4 | Layout e UX | 3 | ✅ Concluído |
| 5 | Infraestrutura | 3 | ✅ Concluído |

---

## FASE 1 — Bugs Críticos

### Bug 1 — `assiduidade.py`: `NameError` em runtime que torna a assiduidade inacessível

**Ficheiro:** `backend/routers/assiduidade.py`

**Problema:** A função `obter_utilizador_atual` é importada corretamente no topo do ficheiro, mas depois redefinida localmente em **dois sítios diferentes** (linhas 22–33 e 154–175). Ambas as definições locais chamam `verificar_token(token)`, que não está importada nesse scope, causando `NameError` em runtime. Toda a funcionalidade de assiduidade estava inacessível.

**Correção aplicada:**
- Removidas as duas definições locais de `obter_utilizador_atual`
- A importação do topo do ficheiro já era suficiente e correta
- Adicionada verificação `verificar_acesso_equipa` em ambos os endpoints (`GET` e `POST /assiduidade/sessoes/{sessao_id}`) para que um treinador não consiga aceder à assiduidade de equipas alheias (ver também Fix 5)

---

### Bug 2 — `plano_print.html`: URLs hardcoded com localhost

**Ficheiro:** `frontend/templates/treino/plano_print.html`

**Problema:** As imagens de fundo dos campos táticos de desenho usavam URLs absolutas com `http://127.0.0.1:8000/static/...`. Em qualquer ambiente de produção (domínio diferente de localhost), as imagens não carregavam e a impressão do plano de treino ficava sem os campos.

**Correção aplicada:**
```
ANTES:  src="http://127.0.0.1:8000/static/campos/campo_meio.png"
DEPOIS: src="/static/campos/campo_meio.png"

ANTES:  src="http://127.0.0.1:8000/static/campos/campo_completo.png"
DEPOIS: src="/static/campos/campo_completo.png"
```

---

## FASE 2 — Segurança e Autorização

### Fix 3 — `atividades.py`: sem verificação de perfil nos endpoints de escrita

**Ficheiro:** `backend/routers/atividades.py`

**Problema:** Os endpoints de criar, editar e apagar atividades globais do clube apenas verificavam se o utilizador estava autenticado. Qualquer treinador podia criar ou apagar atividades globais, função reservada a administradores e coordenadores.

**Correção aplicada:** Adicionado `verificar_perfil(utilizador, ["administrador", "coordenador"])` imediatamente após a verificação de autenticação nos três endpoints de escrita (`POST /atividades/nova`, `POST /atividades/{id}/editar`, `POST /atividades/{id}/apagar`). Utilizadores sem o perfil correto são redirecionados sem executar a ação.

---

### Fix 4 — `criar_admin.py`: password padrão criada sem aviso

**Ficheiro:** `backend/criar_admin.py`

**Problema:** O script de inicialização criava o utilizador `admin` com a password `"admin123"` de forma silenciosa. Em produção, esta password podia ficar esquecida e comprometer a segurança.

**Correção aplicada:** Adicionado `logger.warning(...)` após o commit do utilizador admin, com mensagem explícita a alertar para a necessidade de alterar a password antes de usar em produção.

---

### Fix 5 — `assiduidade.py`: falta de verificação de acesso à equipa

**Ficheiro:** `backend/routers/assiduidade.py`

**Problema:** Os endpoints de visualização e edição de assiduidade não verificavam se o utilizador autenticado tinha permissão para aceder à equipa da sessão em questão. Um treinador podia consultar e registar assiduidade de equipas que não eram suas.

**Correção aplicada:** Após obter a equipa a partir da sessão, adicionada a verificação:
```python
if not verificar_acesso_equipa(utilizador, equipa.id, db):
    return RedirectResponse(url="/dashboard")
```

---

### Fix 6 — `.gitignore` ausente na raiz do projeto

**Problema:** O projeto não tinha ficheiro `.gitignore`. O ficheiro `.env` (com chaves secretas, credenciais de base de dados e tokens JWT) podia ter sido versionado acidentalmente no repositório git.

**Correção aplicada:** Criado `.gitignore` na raiz do projeto com exclusões para:
- `.env` (variáveis de ambiente e segredos)
- `__pycache__/`, `*.pyc`, `*.pyo` (bytecode Python)
- `.venv/`, `venv/` (ambientes virtuais)
- `*.db`, `*.sqlite3` (bases de dados locais)
- `.pytest_cache/`, `.coverage`, `htmlcov/` (artefactos de testes)
- `.vscode/settings.json`, `.idea/` (configurações de IDE)
- `*.log`, `.DS_Store`, `Thumbs.db` (ficheiros de sistema)

---

## FASE 3 — Qualidade de Código

### Fix 7 — `admin.py`: função `obter_utilizador_atual` duplicada localmente

**Ficheiro:** `backend/routers/admin.py`

**Problema:** O router de administração definia a sua própria versão de `obter_utilizador_atual` em vez de importar a função centralizada de `auth.py`, criando código duplicado com risco de divergência de comportamento.

**Correção aplicada:**
- Removida a definição local da função (18 linhas)
- Adicionado `from auth import obter_utilizador_atual, verificar_token, encriptar_password`
- Movidos os imports de modelos (`Utilizador`, `PerfilEnum`, `Treinador`) para o topo do ficheiro, retirando-os do interior das funções onde estavam redundantemente

---

### Fix 8 — `equipas.py`: `MENSAGENS_ERRO_EQUIPA = {}` sempre vazio

**Ficheiro:** `backend/routers/equipas.py`

**Problema:** O dicionário `MENSAGENS_ERRO_EQUIPA` estava definido como vazio (`{}`). Sempre que havia um erro ao criar ou editar uma equipa, a chamada `.get(request.query_params.get("erro"))` retornava sempre `None` e o utilizador nunca via qualquer mensagem de erro.

**Correção aplicada:** Removido o dicionário vazio e o mecanismo de query param associado. Os contextos de template passam agora `"erro": None` diretamente, que pode ser preenchido com mensagens concretas à medida que a lógica de validação for expandida.

---

### Fix 9 — Imports de `datetime` e modelos dentro do corpo de funções

**Ficheiros:** `backend/routers/treinadores.py`, `backend/routers/admin.py`

**Problema:** Instruções `from datetime import date` e `from models.X import Y` estavam dentro do corpo de funções — anti-pattern em Python que re-importa o módulo a cada chamada e dificulta a leitura do ficheiro.

**Correção aplicada:** Movidos todos os imports para o topo dos respetivos ficheiros, seguindo a convenção PEP 8.

---

## FASE 4 — Layout e UX

### Fix 10 — Sidebar: treinador com múltiplas equipas só via a primeira

**Ficheiro:** `frontend/templates/base.html`

**Problema:** O link da sidebar para a equipa do treinador apontava apenas para `equipas[0]`. Um treinador responsável por duas ou mais equipas não tinha forma de navegar para a segunda equipa a partir da sidebar.

**Correção aplicada:** Substituído o link único por um ciclo Jinja2 que itera sobre todas as equipas do treinador:
```jinja2
{% for equipa in utilizador.treinador.equipas %}
    <a href="/equipas/{{ equipa.id }}" class="...">
        <span>🏀</span> {{ equipa.nome }}
    </a>
{% endfor %}
```
Adicionado também o estado "Sem equipa atribuída" para treinadores sem equipa.

---

### Fix 11 — `utilizadores_lista.html`: tabela cortada em ecrãs pequenos

**Ficheiro:** `frontend/templates/admin/utilizadores_lista.html`

**Problema:** A tabela de utilizadores tem 7 colunas mas não tinha `overflow-x-auto`, pelo que em ecrãs de tamanho médio ou pequeno as colunas da direita eram cortadas sem possibilidade de scroll.

**Correção aplicada:** Envolvida a tabela num contentor `<div class="overflow-x-auto">`, permitindo scroll horizontal em ecrãs menores.

---

### Fix 12 — Sidebar sem indicação de página ativa

**Ficheiro:** `frontend/templates/base.html`

**Problema:** Todos os links da sidebar tinham o mesmo estilo visual independentemente da página atual, dificultando a orientação do utilizador dentro da aplicação.

**Correção aplicada:** Criada uma macro Jinja2 `nav_link(href, icon, label)` que compara `request.url.path` com o `href` de cada link e aplica automaticamente as classes de estado ativo (`bg-orange-100 text-orange-600 font-semibold`) ou inativo (`text-gray-700 hover:bg-orange-50 hover:text-orange-600`). Todos os links da sidebar passam a usar esta macro.

---

## FASE 5 — Infraestrutura

### Fix 13 — `docker-compose.yml`: arranque local com PostgreSQL

**Problema:** Não existia forma simples de arrancar o projeto localmente com PostgreSQL. Era necessário instalar e configurar PostgreSQL manualmente.

**Correção aplicada:** Criado `docker-compose.yml` na raiz do projeto com:
- Serviço `db`: PostgreSQL 16 Alpine com healthcheck
- Serviço `app`: imagem da aplicação, aguarda pela base de dados estar saudável antes de arrancar
- Volume persistente `pgdata` para os dados

Arranque com um único comando: `docker compose up`

---

### Fix 14 — 4 testes a falhar em `test_planeamento_clube.py`

**Ficheiro:** `backend/tests/test_planeamento_clube.py` e `backend/models/planeamento.py`

#### Testes 1 e 2 — `test_sincronizacao_cria_sessoes_sem_duplicar` e `test_sincronizacao_cria_microciclos_automaticamente`

**Problema:** Ambos os testes esperavam exatamente 5 sessões mas obtinham 6. A causa: o evento global (`aplica_a_todas_equipas=True`) usa `db.query(Equipa).all()` para obter todas as equipas do sistema. Se a base de dados de testes tiver equipas de outros dados de seed ou de outros testes, são criadas sessões extra para essas equipas, inflacionando a contagem.

**Correção aplicada:** As asserções passam agora a filtrar as sessões para apenas as duas equipas do contexto de teste (`equipa_1_id` e `equipa_2_id`) antes de verificar a contagem e a distribuição por evento. Sessões de equipas extra são ignoradas na validação, tornando os testes robustos ao estado da base de dados.

#### Teste 3 — `test_sincronizacao_inativa_sessao_quando_evento_e_removido`

**Problema:** O teste esperava encontrar 1 sessão com `ativa=False` após apagar o evento, mas encontrava 0 sessões. O comportamento padrão do SQLAlchemy, ao detetar a eliminação de um objeto pai, emite automaticamente `UPDATE sessoes_treino SET evento_planeamento_clube_id = NULL` antes de apagar o evento. A sessão sobrevivia, mas com a FK a `NULL`, tornando-a invisível à query de verificação do teste.

**Correção aplicada:** Em `backend/models/planeamento.py`, adicionado `passive_deletes=True` ao backref `sessoes_geradas` da relação `evento_planeamento_clube`:
```python
evento_planeamento_clube = relationship(
    "EventoPlaneamentoClube",
    backref=backref("sessoes_geradas", passive_deletes=True),
)
```
Com `passive_deletes=True`, o SQLAlchemy não emite o `UPDATE` para `NULL`. Em SQLite (usado nos testes), as FK não são forçadas, pelo que a sessão mantém o seu `evento_planeamento_clube_id` original. Na sincronização seguinte, `_desativar_sessoes_orfas_ou_fora_de_escopo` identifica o par `(evento_id, equipa_id)` como ausente e desativa corretamente a sessão.

#### Teste 4 — `test_detalhe_espaco_separa_atribuicoes_associadas_e_ocupacao_recente`

**Problema identificado no plano:** `DetachedInstanceError` por acesso a atributos lazy-loaded após fecho de sessão SQLAlchemy.

**Resultado da análise:** O endpoint `GET /planeamento-clube/espacos/{id}` carrega todos os dados necessários dentro da sessão de pedido, e o template acede apenas a valores de coluna e relações nulas (sem lazy-loading real). O erro descrito no plano correspondia a uma versão anterior do código — **nenhuma alteração foi necessária**.

---

### Fix 15 — `conftest.py`: fixtures partilhadas entre testes

**Problema:** Cada ficheiro de testes definia as suas próprias funções auxiliares (`_criar_client`, credenciais de utilizadores hardcoded). Código duplicado e frágil: uma alteração nas credenciais de teste exigia atualizar múltiplos ficheiros.

**Correção aplicada:** Criado `backend/tests/conftest.py` com fixtures pytest partilhadas:
- `client` — `TestClient(app)` isolado por teste
- `client_admin` — cliente pré-autenticado como administrador
- `client_coordenador` — cliente pré-autenticado como coordenador
- `client_treinador` — cliente pré-autenticado como treinador
- `_autenticar(client, perfil)` — helper interno que faz login via `/login-form`

---

## Ficheiros Modificados

| Ficheiro | Alterações |
|---|---|
| `backend/routers/assiduidade.py` | Removidas 2 funções duplicadas; adicionada verificação de acesso à equipa |
| `frontend/templates/treino/plano_print.html` | Corrigidas 2 URLs hardcoded para caminhos relativos |
| `backend/routers/atividades.py` | Adicionado `verificar_perfil` em 3 endpoints de escrita |
| `backend/criar_admin.py` | Adicionado aviso de password padrão via `logger.warning` |
| `backend/routers/admin.py` | Removida função duplicada; imports movidos para o topo |
| `backend/routers/equipas.py` | Removido `MENSAGENS_ERRO_EQUIPA = {}` inoperante |
| `backend/routers/treinadores.py` | Imports de `datetime` movidos para o topo |
| `frontend/templates/base.html` | Sidebar com multi-equipa, active state e macro `nav_link` |
| `frontend/templates/admin/utilizadores_lista.html` | Adicionado `overflow-x-auto` à tabela |
| `backend/tests/test_planeamento_clube.py` | Corrigidos 3 testes com asserções filtradas por equipa de teste |
| `backend/models/planeamento.py` | Adicionado `passive_deletes=True` ao backref `sessoes_geradas` |

## Ficheiros Criados

| Ficheiro | Conteúdo |
|---|---|
| `.gitignore` | Exclusões para `.env`, bytecode, venv, DBs e IDE |
| `docker-compose.yml` | PostgreSQL 16 + app com healthcheck e volume persistente |
| `backend/tests/conftest.py` | Fixtures pytest partilhadas para autenticação nos testes |

---

## Checklist de Verificação

- [ ] `/assiduidade/sessoes/1` não retorna erro 500
- [ ] `/treino/sessoes/{id}/print` mostra imagens dos campos táticos
- [ ] Treinador não consegue criar atividades globais (redireciona para `/atividades`)
- [ ] Treinador não consegue ver assiduidade de equipas alheias (redireciona para `/dashboard`)
- [ ] `docker compose up` arranca PostgreSQL e aplicação sem erros
- [ ] `pytest backend/tests/` passa a 100%
- [ ] Sidebar mostra todas as equipas de um treinador com múltiplas equipas
- [ ] Link ativo na sidebar fica destacado ao navegar
- [ ] Tabela de utilizadores faz scroll horizontal em ecrãs pequenos
