# Publicação na Railway

Este projeto é composto por uma aplicação FastAPI e uma base de dados PostgreSQL.
As fotografias de jogadores e os logótipos são ficheiros enviados pelos utilizadores,
pelo que precisam de armazenamento persistente.

## Serviços necessários

Cria no mesmo projeto Railway:

1. Um serviço PostgreSQL gerido.
2. Um serviço para a aplicação, ligado ao repositório GitHub.
3. Um volume persistente ligado ao serviço da aplicação.

Não uses o PostgreSQL do `docker-compose.yml` em produção. A Railway deve criar e
gerir a base de dados.

## Volume para fotografias e logótipos

No serviço da aplicação, cria um volume com o ponto de montagem:

```
/app/frontend/static/uploads
```

Sem este volume, os uploads desaparecem sempre que houver um novo deploy.

## Variáveis do serviço da aplicação

Define no painel Railway:

```
DATABASE_URL=<referência à DATABASE_URL do PostgreSQL Railway>
SECRET_KEY=<valor aleatório novo>
SESSION_SECRET_KEY=<outro valor aleatório novo>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480
SESSION_COOKIE_NAME=basquetebol_session
SESSION_COOKIE_SAME_SITE=lax
SESSION_COOKIE_HTTPS_ONLY=true
SESSION_COOKIE_MAX_AGE_SECONDS=28800
SESSION_COOKIE_DOMAIN=
APP_ENV=production
```

`SECRET_KEY` e `SESSION_SECRET_KEY` têm de ser diferentes. Nunca usar valores do
ficheiro `.env` antigo nem colocar estas variáveis no GitHub.

## Deploy e validação

1. Confirma que a Railway identifica o `Dockerfile` da raiz.
2. Gera um domínio Railway para o serviço da aplicação.
3. Aguarda o health check em `/ready` ficar saudável.
4. Verifica `https://<dominio>/health` e `https://<dominio>/ready`.
5. Faz login, carrega uma fotografia de teste e um logótipo de teste.
6. Gera pelo menos um PDF com desenho tático e confirma que imagens e cabeçalhos aparecem.
7. Faz um novo deploy e confirma que os ficheiros carregados continuam disponíveis.

## Backups

Configura backups da base de dados no painel Railway e testa uma restauração antes de
introduzir dados reais. O volume de uploads também deve ter backups configurados.
