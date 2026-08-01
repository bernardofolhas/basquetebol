# Plataforma de Gestão de Basquetebol

Aplicação web de gestão desportiva para clubes de basquetebol, construída com FastAPI, Jinja2 e SQLAlchemy. Suporta múltiplos perfis de utilizador (administrador, coordenador e treinador) com dashboards e permissões diferenciadas.

---

## Funcionalidades

### Gestão de Plantel
- **Equipas** — Criação e edição de equipas por escalão (Sub-8 a Sénior/Masters), género e seccionista
- **Treinadores** — Ficha completa com dados pessoais, número de cédula FPB e equipas associadas (relação N:N)
- **Jogadores** — Ficha com dados pessoais, contactos dos pais, posição, número de camisola, estado de inscrição, exame médico e registos antropométricos ao longo do tempo

### Planeamento Desportivo (por equipa)
- **Macrociclos** → **Mesociclos** → **Microciclos** → **Sessões de treino**, com objetivos táticos/técnicos/físicos/psicológicos em cada nível e campo de reflexão do treinador
- Cada sessão regista volume em minutos, intensidade RPE, distribuição de tempo por componente (técnica individual ofensiva/defensiva, tática individual, tática coletiva, físicos) e se é dia de jogo

### Plano de Treino
- Por sessão, o treinador preenche um plano estruturado em blocos (A, B, C, D)
- Cada exercício tem: hora, duração, nome, categoria, dois campos de desenho tático (imagem base64), organização e coaching points
- Biblioteca de exercícios reutilizáveis

### Jogos
- Calendário de jogos por equipa com resultado, adversário, competição e local (casa/fora)
- Convocatórias com hora/local de encontro e observações por jogador
- Plano de jogo: cinco inicial, rotações, chaves de ataque/defesa, movimentos ofensivos, estratégias defensivas específicas (bloqueio direto, handoff, indiretos, bola dentro, situações especiais)
- Impressão de convocatórias e planos de jogo

### Assiduidade
- Registo de presença/falta por jogador em cada sessão de treino, com motivo de falta

### Preparação Física
- Testes físicos por jogador (Yo-Yo, Sprint, CMJ, etc.) com resultado, unidade e data
- Planeamento físico semanal/mensal por equipa (resistência, velocidade, força, flexibilidade, coordenação)

### Planeamento do Clube (nível global)
- Hierarquia: **Planeamento Anual** → **Planeamentos Mensais** → **Planos Semanais** → **Eventos**
- Eventos suportados: treino de equipa, treino individual, jogo, atividade extra, evento de clube
- Associação de eventos a espaços de treino e equipas (incluindo "aplica a todas as equipas")
- **Atribuição de espaços semanais** com controlo de sobreposições e estados (rascunho / publicado / cancelado)
- **Sincronização** do plano semanal do clube com os microciclos das equipas — cria, atualiza ou inativa sessões automaticamente, respeitando alterações manuais dos treinadores
- Dashboard de sincronização com resumo visual do estado de cada sessão (manual, sincronizada, alterada manualmente, desatualizada, desativada)

### Espaços de Treino
- Cadastro de pavilhões, meio-campo, ginásios e outros espaços com capacidade e localização
- Mapa visual de ocupação semanal por espaço

### Calendário Global
- Vista agregada de todos os jogos do clube agrupados por mês

### Atividades
- Registo de atividades do clube (formação, social, evento, etc.)

### Dashboards
| Perfil | Dashboard |
|---|---|
| Treinador | Equipas próprias, próximos jogos/treinos, assiduidade recente, alertas da equipa |
| Coordenador | Visão global do clube, planeamento mensal atual, jogos e resultados, alertas |
| Administrador | Igual ao coordenador + total de utilizadores |
| Dashboard Clube | Visão operacional global (carga de treino, ocupação de espaços, planeado vs. executado, sincronização) |

### Operação e identidade
- Centro de tarefas pendentes por perfil, com ligações diretas para preparar, confirmar, registar e rever o trabalho.
- Navegação com equipa, época, período e próximo evento sempre visíveis.
- Identidade configurável do clube (nome, cores, época, rodapés e logótipos PNG/JPEG validados), aplicada à aplicação e aos documentos.
- Exportações PDF A4 para planeamentos, calendários, planos de treino, jogos, convocatórias, assiduidade, evolução, playbook e pendências administrativas.
- Plano de treino com blocos A-D, desenhos táticos sem deformação, RPE geral e RPE por exercício.

### Alertas Automáticos
- Exames médicos a expirar nos próximos 30 dias
- Inscrições de jogadores em estado "pendente"

### Administração
- Gestão de utilizadores (criar, editar, ativar/desativar, apagar) exclusiva para administrador
- Cada utilizador pode ser associado a um treinador

---

## Arquitetura

```
basquetebol/
├── backend/
│   ├── main.py                  # Entrada FastAPI, registo de routers
│   ├── config.py                # Configuração central (lê .env)
│   ├── database.py              # Engine SQLAlchemy, sessão, migrações incrementais
│   ├── auth.py                  # JWT, bcrypt, controlo de acesso por perfil/equipa
│   ├── paths.py                 # Caminhos absolutos do projecto
│   ├── logging_config.py        # Configuração de logging
│   ├── run.py                   # Ponto de entrada uvicorn
│   ├── criar_admin.py           # Script de bootstrap do utilizador admin
│   ├── models/                  # Modelos SQLAlchemy (uma tabela por ficheiro)
│   ├── routers/                 # Routers FastAPI (HTML + formulários)
│   ├── services/                # Lógica de negócio desacoplada dos routers
│   └── tests/                   # Testes automatizados com pytest
└── frontend/
    ├── templates/               # Templates Jinja2 (SSR)
    └── static/                  # CSS, JS, imagens
```

A aplicação é **Server-Side Rendering (SSR)** — o backend gera HTML completo via Jinja2. Não há API REST separada nem frontend SPA.

---

## Stack Técnica

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.13, FastAPI 0.135 |
| Templates | Jinja2 3.1 |
| ORM | SQLAlchemy 2.0 |
| Base de dados | SQLite (dev) / PostgreSQL (prod) |
| Autenticação | JWT (python-jose) + bcrypt + SessionMiddleware |
| Servidor HTTP | Uvicorn |
| CSS | Tailwind CSS (via CDN) |

---

## Modelos de Dados

```
utilizadores          — perfil: administrador | coordenador | treinador
treinadores           — dados pessoais, cédula FPB
treinador_equipa      — N:N treinadores ↔ equipas
equipas               — escalão, género
jogadores             — dados pessoais, pais, médicos, inscrição
registos_antropometricos — histórico de medidas por jogador

macrociclos           — bloco grande de planeamento por equipa
  mesociclos          — bloco médio (≈ mês)
    microciclos       — semana de treino
      sessoes_treino  — sessão individual (pode vir de plano manual ou global)
        planos_treino — plano detalhado com blocos de exercícios
          exercicios_plano — linha do plano (desenho, organização, coaching)
biblioteca_exercicios — exercícios reutilizáveis

jogos                 — calendário oficial por equipa
convocados            — jogadores convocados por jogo
planos_jogo           — 5 inicial, rotações, estratégias

assiduidade           — presença/falta por sessão/jogador
testes_fisicos        — resultados de testes por jogador
planeamentos_fisicos  — plano físico semanal/mensal por equipa

atividades            — atividades gerais do clube
espacos_treino        — pavilhões e outros espaços
identidade_clube      — nome, cores e logótipos usados na aplicação e nos PDFs

planeamentos_clube_anuais  — plano anual do clube
planeamentos_clube_mensais — desdobramento mensal
planos_semanais_clube      — semana operacional do clube
eventos_planeamento_clube  — evento concreto (treino, jogo, atividade...)
evento_planeamento_clube_equipa — N:N eventos ↔ equipas
atribuicoes_espaco_semanais — ocupação de espaço por evento/equipa
```

---

## Perfis e Permissões

| Acção | Administrador | Coordenador | Treinador |
|---|:---:|:---:|:---:|
| Gestão de utilizadores | ✓ | — | — |
| Equipas, treinadores, jogadores | ✓ | ✓ | equipas próprias |
| Planeamento por equipa | ✓ | ✓ | equipas próprias |
| Jogos e convocatórias | ✓ | ✓ | equipas próprias |
| Assiduidade e físico | ✓ | ✓ | equipas próprias |
| Planeamento global do clube | ✓ | ✓ | — |
| Dashboards operacionais do clube | ✓ | ✓ | — |

---

## Configuração

### Variáveis de ambiente (`.env`)

Copia `.env.example` para `.env` e preenche:

```env
DATABASE_URL=postgresql+psycopg2://utilizador:password@host:5432/basquetebol
SECRET_KEY=chave_jwt_super_secreta
SESSION_SECRET_KEY=chave_sessao_super_secreta
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480
SESSION_COOKIE_NAME=basquetebol_session
SESSION_COOKIE_SAME_SITE=lax
SESSION_COOKIE_HTTPS_ONLY=true
SESSION_COOKIE_MAX_AGE_SECONDS=28800
SESSION_COOKIE_DOMAIN=
APP_ENV=development   # ou production
```

Para desenvolvimento local com SQLite:

```env
DATABASE_URL=sqlite:///basquetebol.db
SECRET_KEY=qualquer_chave_local
SESSION_SECRET_KEY=qualquer_chave_local
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480
SESSION_COOKIE_NAME=basquetebol_session
SESSION_COOKIE_SAME_SITE=lax
SESSION_COOKIE_HTTPS_ONLY=false
SESSION_COOKIE_MAX_AGE_SECONDS=28800
SESSION_COOKIE_DOMAIN=
APP_ENV=development
```

Notas:
- Em `production`, `SESSION_SECRET_KEY` deve ser diferente de `SECRET_KEY`.
- `SESSION_COOKIE_SAME_SITE=none` so pode ser usado com `SESSION_COOKIE_HTTPS_ONLY=true`.

---

## Instalação e Execução Local

```bash
# Criar e activar ambiente virtual
python -m venv venv
source venv/bin/activate        # Linux/macOS
venv\Scripts\activate           # Windows

# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
cp .env.example .env
# editar .env

# Criar o utilizador administrador inicial
python backend/criar_admin.py

# Arrancar o servidor (com hot-reload em desenvolvimento)
python backend/run.py
```

A aplicação fica disponível em `http://localhost:8000`.

Credenciais iniciais: `admin` / `admin123` — **alterar imediatamente após o primeiro login**.

---

## Docker

Construir a imagem:

```bash
docker build -t basquetebol-app .
```

Executar com ficheiro `.env`:

```bash
docker run --rm -p 8000:8000 --env-file .env basquetebol-app
```

Executar com variáveis inline:

```bash
docker run --rm -p 8000:8000 \
  -e DATABASE_URL=postgresql+psycopg2://utilizador:password@host:5432/basquetebol \
  -e SECRET_KEY=chave_segura \
  -e SESSION_SECRET_KEY=outra_chave_segura \
  -e ALGORITHM=HS256 \
  -e ACCESS_TOKEN_EXPIRE_MINUTES=480 \
  -e APP_ENV=production \
  basquetebol-app
```

---

## Produção

- Usar **PostgreSQL** gerido pela plataforma (ex: Railway, Supabase, RDS)
- Definir `APP_ENV=production`
- Usar chaves `SECRET_KEY` e `SESSION_SECRET_KEY` distintas e aleatórias
- Configurar backups regulares da base de dados
- Os logs são emitidos em formato simples (timestamp + nível + mensagem), compatível com Docker e plataformas cloud

### Backup manual

Pode ser criado um backup local com:

```bash
python backend/backup.py
```

Em SQLite é copiado o ficheiro da base de dados. Em PostgreSQL é usado o
`pg_dump`; se necessário, define `PG_DUMP_BIN` com o caminho do executável e
`BACKUP_DIR` com a pasta de destino.

---

## Health Checks

| Endpoint | Descrição |
|---|---|
| `GET /health` | Confirma que o processo HTTP está vivo |
| `GET /ready` | Confirma que a base de dados está acessível |

Úteis como probes de saúde em deploy cloud (Kubernetes, Railway, Render, etc.).

---

## Testes

```bash
pytest backend/tests/
```

Os testes cobrem autenticação, navegação, operações CRUD, permissões, planeamento do clube e alertas.

---

## CI

Existe um workflow GitHub Actions em `.github/workflows/ci.yml` que instala dependências e corre `pytest` automaticamente em `push` e `pull request`.
