from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import Session as ORMSession, declarative_base, sessionmaker, with_loader_criteria
from config import config
from logging_config import obter_logger

logger = obter_logger(__name__)


def _criar_engine():
    """
    Cria a engine SQLAlchemy com opções simples e seguras para produção.
    """
    opcoes_engine = {
        "pool_pre_ping": True,
        "future": True,
    }

    if config.database_url.startswith("sqlite"):
        opcoes_engine["connect_args"] = {"check_same_thread": False}

    logger.info("A configurar ligação à base de dados.")
    return create_engine(config.database_url, **opcoes_engine)

# Cria o "motor" de ligação à base de dados a partir da configuração central.
engine = _criar_engine()

# Cria uma "fábrica" de sessões
# Uma sessão é uma conversa temporária com a base de dados
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    bind=engine,
)

# Base que todos os modelos vão herdar
# Um modelo é a representação em Python de uma tabela da base de dados
Base = declarative_base()


@event.listens_for(ORMSession, "do_orm_execute")
def _isolar_consultas_por_clube(execute_state):
    """Aplica isolamento a qualquer consulta ORM de um modelo com clube_id."""
    from clube_contexto import clube_atual_id

    atual = clube_atual_id()
    if atual is None or execute_state.execution_options.get("ignorar_clube"):
        return
    for mapper in tuple(Base.registry.mappers):
        modelo = mapper.class_
        if hasattr(modelo, "clube_id"):
            execute_state.statement = execute_state.statement.options(
                with_loader_criteria(
                    modelo,
                    lambda entidade: entidade.clube_id == atual,
                    include_aliases=True,
                )
            )


@event.listens_for(ORMSession, "before_flush")
def _sincronizar_volume_dos_treinos(session, _flush_context, _instances):
    """Calcula o volume sempre que uma sessão de treino é criada ou alterada."""
    from models.planeamento import SessaoTreino
    from services.volume_sessao_service import atualizar_volume_automatico

    for objeto in session.new.union(session.dirty):
        if isinstance(objeto, SessaoTreino):
            atualizar_volume_automatico(objeto)


@event.listens_for(ORMSession, "before_flush")
def _atribuir_e_validar_clube(session, flush_context, instances):
    """A pertença é imposta pelo servidor, nunca por campos do formulário."""
    from clube_contexto import clube_atual_id

    atual = clube_atual_id()
    if atual is None:
        # Compatibilidade para tarefas locais e testes de instalações com um só clube.
        ids = [linha[0] for linha in session.execute(text("SELECT id FROM clubes LIMIT 2"))] if Base.metadata.tables.get("clubes") is not None else []
        atual = ids[0] if len(ids) == 1 else None
    if atual is None:
        return
    for objeto in session.new:
        if hasattr(objeto, "clube_id"):
            informado = getattr(objeto, "clube_id", None)
            if informado not in (None, atual):
                raise PermissionError("O registo não pode ser criado noutro clube.")
            objeto.clube_id = atual
    for objeto in session.dirty:
        if hasattr(objeto, "clube_id") and getattr(objeto, "clube_id", None) != atual:
            # O superadministrador é global e, por isso, não pertence a um
            # clube. Também pode gerar auditoria global com clube_id nulo.
            perfil = getattr(objeto, "perfil", None)
            perfil_valor = getattr(perfil, "value", perfil)
            tabela = getattr(objeto, "__tablename__", "")
            if (
                getattr(objeto, "clube_id", None) is None
                and (
                    (tabela == "utilizadores" and perfil_valor == "superadministrador")
                    or tabela == "registos_auditoria"
                )
            ):
                continue
            raise PermissionError("O registo não pertence ao clube atual.")


def base_dados_disponivel() -> bool:
    """
    Confirma de forma leve se a base de dados está acessível.
    """
    try:
        with engine.connect() as ligacao:
            ligacao.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def validar_ligacao_base_dados() -> None:
    """
    Valida que a ligação à base de dados responde correctamente.
    """
    try:
        with engine.connect() as ligacao:
            ligacao.execute(text("SELECT 1"))
        logger.info("Ligação à base de dados validada com sucesso.")
    except Exception as exc:
        logger.exception("Falha ao ligar à base de dados. Verifica a DATABASE_URL e a disponibilidade do servidor.")
        raise RuntimeError("Não foi possível estabelecer ligação à base de dados.") from exc


def actualizar_estrutura_perfis() -> None:
    """Mantém o enum PostgreSQL compatível em instalações sem Alembic automático."""
    if engine.dialect.name != "postgresql" or not inspect(engine).has_table("utilizadores"):
        return
    with engine.begin() as ligacao:
        existe = ligacao.execute(text(
            "SELECT 1 FROM pg_enum "
            "WHERE enumtypid = 'perfilenum'::regtype AND enumlabel = 'secretaria'"
        )).first()
        if not existe:
            ligacao.execute(text("ALTER TYPE perfilenum ADD VALUE 'secretaria'"))
            logger.info("Perfil 'secretaria' adicionado ao enum da base de dados.")


def actualizar_estrutura_recuperacao_password() -> None:
    """Adiciona a versão de sessão a instalações anteriores."""
    inspector = inspect(engine)
    if not inspector.has_table("utilizadores"):
        return
    colunas = {coluna["name"] for coluna in inspector.get_columns("utilizadores")}
    if "sessao_versao" in colunas:
        return
    with engine.begin() as ligacao:
        if engine.dialect.name == "postgresql":
            ligacao.execute(text(
                "ALTER TABLE utilizadores ADD COLUMN IF NOT EXISTS sessao_versao INTEGER NOT NULL DEFAULT 0"
            ))
        else:
            ligacao.execute(text(
                "ALTER TABLE utilizadores ADD COLUMN sessao_versao INTEGER NOT NULL DEFAULT 0"
            ))
    logger.info("Versão de sessão adicionada aos utilizadores.")


def actualizar_estrutura_campos_desenho() -> None:
    """Adiciona gestão individual de campos táticos a instalações existentes."""
    inspector = inspect(engine)
    dialecto = engine.dialect.name
    if inspector.has_table("exercicios_plano"):
        colunas = {coluna["name"] for coluna in inspector.get_columns("exercicios_plano")}
        if "campos_ativos" not in colunas:
            with engine.begin() as ligacao:
                if dialecto == "postgresql":
                    ligacao.execute(text(
                        "ALTER TABLE exercicios_plano ADD COLUMN IF NOT EXISTS "
                        "campos_ativos VARCHAR NOT NULL DEFAULT '1,2'"
                    ))
                else:
                    ligacao.execute(text(
                        "ALTER TABLE exercicios_plano ADD COLUMN "
                        "campos_ativos VARCHAR NOT NULL DEFAULT '1,2'"
                    ))
                ligacao.execute(text(
                    "UPDATE exercicios_plano SET campos_ativos = CASE "
                    "WHEN desenho_3 IS NOT NULL AND desenho_4 IS NOT NULL THEN '1,2,3,4' "
                    "WHEN desenho_3 IS NOT NULL THEN '1,2,3' "
                    "WHEN desenho_4 IS NOT NULL THEN '1,2,4' ELSE '1,2' END"
                ))
            logger.info("Campos táticos ativos adicionados aos exercícios.")

    inspector = inspect(engine)
    if inspector.has_table("biblioteca_exercicios"):
        colunas = {coluna["name"] for coluna in inspector.get_columns("biblioteca_exercicios")}
        if "desenho_campo_completo" not in colunas:
            with engine.begin() as ligacao:
                if dialecto == "postgresql":
                    ligacao.execute(text(
                        "ALTER TABLE biblioteca_exercicios ADD COLUMN IF NOT EXISTS "
                        "desenho_campo_completo TEXT NULL"
                    ))
                else:
                    ligacao.execute(text(
                        "ALTER TABLE biblioteca_exercicios ADD COLUMN desenho_campo_completo TEXT NULL"
                    ))
            logger.info("Desenho de campo inteiro adicionado à biblioteca.")


def actualizar_estrutura_playbook() -> None:
    """Mantém instalações existentes compatíveis com imagens por passo."""
    inspector = inspect(engine)
    if not inspector.has_table("passos_setplay"):
        return
    colunas = {coluna["name"] for coluna in inspector.get_columns("passos_setplay")}
    if "imagem_coach" in colunas:
        return
    with engine.begin() as ligacao:
        if engine.dialect.name == "postgresql":
            ligacao.execute(text(
                "ALTER TABLE passos_setplay ADD COLUMN IF NOT EXISTS imagem_coach TEXT NULL"
            ))
        else:
            ligacao.execute(text(
                "ALTER TABLE passos_setplay ADD COLUMN imagem_coach TEXT NULL"
            ))
    logger.info("Imagem alternativa adicionada aos passos do playbook.")


def actualizar_estrutura_objetivos_planeamento() -> None:
    """Garante as cinco categorias simples de objetivos nos ciclos."""
    tabelas = ("macrociclos", "mesociclos", "microciclos")
    inspector = inspect(engine)
    dialecto = engine.dialect.name
    tipos = {"macrociclos": inspector.has_table("macrociclos"),
             "mesociclos": inspector.has_table("mesociclos"),
             "microciclos": inspector.has_table("microciclos")}
    if not any(tipos.values()):
        return
    with engine.begin() as ligacao:
        for tabela in tabelas:
            if not tipos[tabela]:
                continue
            colunas = {coluna["name"] for coluna in inspect(engine).get_columns(tabela)}
            for coluna in ("objetivos_gerais", "objetivos_ofensivos", "objetivos_defensivos"):
                if coluna not in colunas:
                    ligacao.execute(text(
                        f"ALTER TABLE {tabela} ADD COLUMN {coluna} TEXT"
                    ))


def actualizar_estrutura_planeamento_clube() -> None:
    """
    Garante compatibilidade mínima do esquema para evoluções recentes do
    módulo de planeamento do clube em bases já existentes.

    O projecto ainda não usa migrações formais, por isso fazemos aqui uma
    actualização incremental e idempotente das colunas/tabelas novas.
    """
    inspector = inspect(engine)

    if not inspector.has_table("eventos_planeamento_clube"):
        return

    colunas_eventos = {coluna["name"] for coluna in inspector.get_columns("eventos_planeamento_clube")}
    dialecto = engine.dialect.name

    with engine.begin() as ligacao:
        if dialecto == "postgresql":
            # Instalações antigas podem arrancar sem executar Alembic. Mantemos
            # o enum compatível com o modelo antes de aceitar novos eventos.
            for tipo in ("treino_fisico", "folga", "torneio", "viagem", "teste_fisico", "outro"):
                existe = ligacao.execute(text(
                    "SELECT 1 FROM pg_enum "
                    "WHERE enumtypid = 'tipoeventoplaneamentoclubeenum'::regtype "
                    "AND enumlabel = :tipo"
                ), {"tipo": tipo}).first()
                if not existe:
                    ligacao.execute(text(
                        f"ALTER TYPE tipoeventoplaneamentoclubeenum ADD VALUE '{tipo}'"
                    ))

            existe_treino_fisico = ligacao.execute(text(
                "SELECT 1 FROM pg_enum "
                "WHERE enumtypid = 'tipoocupacaoespacoenum'::regtype "
                "AND enumlabel = 'treino_fisico'"
            )).first()
            if not existe_treino_fisico:
                ligacao.execute(text(
                    "ALTER TYPE tipoocupacaoespacoenum ADD VALUE 'treino_fisico'"
                ))

        if "espaco_id" not in colunas_eventos:
            if dialecto == "postgresql":
                ligacao.execute(text(
                    "ALTER TABLE eventos_planeamento_clube "
                    "ADD COLUMN IF NOT EXISTS espaco_id INTEGER REFERENCES espacos_treino(id)"
                ))
            else:
                ligacao.execute(text(
                    "ALTER TABLE eventos_planeamento_clube "
                    "ADD COLUMN espaco_id INTEGER"
                ))
            logger.info("Coluna 'espaco_id' adicionada a eventos_planeamento_clube.")

        if "aplica_a_todas_equipas" not in colunas_eventos:
            if dialecto == "postgresql":
                ligacao.execute(text(
                    "ALTER TABLE eventos_planeamento_clube "
                    "ADD COLUMN IF NOT EXISTS aplica_a_todas_equipas BOOLEAN NOT NULL DEFAULT FALSE"
                ))
            else:
                ligacao.execute(text(
                    "ALTER TABLE eventos_planeamento_clube "
                    "ADD COLUMN aplica_a_todas_equipas BOOLEAN NOT NULL DEFAULT 0"
                ))
            logger.info("Coluna 'aplica_a_todas_equipas' adicionada a eventos_planeamento_clube.")

        for coluna, tabela in (
            ("macrociclo_id", "macrociclos"),
            ("mesociclo_id", "mesociclos"),
            ("microciclo_id", "microciclos"),
        ):
            if coluna in colunas_eventos:
                continue
            if dialecto == "postgresql":
                ligacao.execute(text(
                    f"ALTER TABLE eventos_planeamento_clube "
                    f"ADD COLUMN IF NOT EXISTS {coluna} INTEGER REFERENCES {tabela}(id) ON DELETE CASCADE"
                ))
            else:
                ligacao.execute(text(
                    f"ALTER TABLE eventos_planeamento_clube ADD COLUMN {coluna} INTEGER"
                ))
            logger.info("Coluna '%s' adicionada a eventos_planeamento_clube.", coluna)

    # Reinspecção depois de possíveis alterações.
    inspector = inspect(engine)
    if inspector.has_table("planos_semanais_clube"):
        colunas_semanais = {coluna["name"] for coluna in inspector.get_columns("planos_semanais_clube")}

        with engine.begin() as ligacao:
            if "ultima_sincronizacao_em" not in colunas_semanais:
                if dialecto == "postgresql":
                    ligacao.execute(text(
                        "ALTER TABLE planos_semanais_clube "
                        "ADD COLUMN IF NOT EXISTS ultima_sincronizacao_em TIMESTAMP NULL"
                    ))
                else:
                    ligacao.execute(text(
                        "ALTER TABLE planos_semanais_clube "
                        "ADD COLUMN ultima_sincronizacao_em TIMESTAMP NULL"
                    ))
                logger.info("Coluna 'ultima_sincronizacao_em' adicionada a planos_semanais_clube.")

            if "ultima_sincronizacao_por" not in colunas_semanais:
                if dialecto == "postgresql":
                    ligacao.execute(text(
                        "ALTER TABLE planos_semanais_clube "
                        "ADD COLUMN IF NOT EXISTS ultima_sincronizacao_por VARCHAR NULL"
                    ))
                else:
                    ligacao.execute(text(
                        "ALTER TABLE planos_semanais_clube "
                        "ADD COLUMN ultima_sincronizacao_por VARCHAR NULL"
                    ))
                logger.info("Coluna 'ultima_sincronizacao_por' adicionada a planos_semanais_clube.")

            if "ultima_sincronizacao_resumo" not in colunas_semanais:
                if dialecto == "postgresql":
                    ligacao.execute(text(
                        "ALTER TABLE planos_semanais_clube "
                        "ADD COLUMN IF NOT EXISTS ultima_sincronizacao_resumo TEXT NULL"
                    ))
                else:
                    ligacao.execute(text(
                        "ALTER TABLE planos_semanais_clube "
                        "ADD COLUMN ultima_sincronizacao_resumo TEXT NULL"
                    ))
                logger.info("Coluna 'ultima_sincronizacao_resumo' adicionada a planos_semanais_clube.")

    inspector = inspect(engine)
    if inspector.has_table("atribuicoes_espaco_semanais"):
        colunas_atribuicoes = {coluna["name"] for coluna in inspector.get_columns("atribuicoes_espaco_semanais")}
        if "treinador_id" not in colunas_atribuicoes:
            with engine.begin() as ligacao:
                if dialecto == "postgresql":
                    ligacao.execute(text(
                        "ALTER TABLE atribuicoes_espaco_semanais "
                        "ADD COLUMN IF NOT EXISTS treinador_id INTEGER REFERENCES treinadores(id)"
                    ))
                else:
                    ligacao.execute(text(
                        "ALTER TABLE atribuicoes_espaco_semanais ADD COLUMN treinador_id INTEGER"
                    ))
            logger.info("Coluna 'treinador_id' adicionada a atribuicoes_espaco_semanais.")

    inspector = inspect(engine)
    if not inspector.has_table("evento_planeamento_clube_equipa"):
        tabela = Base.metadata.tables.get("evento_planeamento_clube_equipa")
        if tabela is not None:
            tabela.create(bind=engine, checkfirst=True)
            logger.info("Tabela associativa 'evento_planeamento_clube_equipa' criada com sucesso.")

    inspector = inspect(engine)
    if not inspector.has_table("sessoes_treino"):
        return

    colunas_sessoes = {coluna["name"] for coluna in inspector.get_columns("sessoes_treino")}

    with engine.begin() as ligacao:
        if "hora_inicio" not in colunas_sessoes:
            if dialecto == "postgresql":
                ligacao.execute(text(
                    "ALTER TABLE sessoes_treino "
                    "ADD COLUMN IF NOT EXISTS hora_inicio VARCHAR NULL"
                ))
            else:
                ligacao.execute(text(
                    "ALTER TABLE sessoes_treino "
                    "ADD COLUMN hora_inicio VARCHAR NULL"
                ))
            logger.info("Coluna 'hora_inicio' adicionada a sessoes_treino.")

        if "hora_fim" not in colunas_sessoes:
            if dialecto == "postgresql":
                ligacao.execute(text(
                    "ALTER TABLE sessoes_treino "
                    "ADD COLUMN IF NOT EXISTS hora_fim VARCHAR NULL"
                ))
            else:
                ligacao.execute(text(
                    "ALTER TABLE sessoes_treino "
                    "ADD COLUMN hora_fim VARCHAR NULL"
                ))
            logger.info("Coluna 'hora_fim' adicionada a sessoes_treino.")

        if "origem" not in colunas_sessoes:
            if dialecto == "postgresql":
                ligacao.execute(text(
                    "ALTER TABLE sessoes_treino "
                    "ADD COLUMN IF NOT EXISTS origem VARCHAR NOT NULL DEFAULT 'manual'"
                ))
            else:
                ligacao.execute(text(
                    "ALTER TABLE sessoes_treino "
                    "ADD COLUMN origem VARCHAR NOT NULL DEFAULT 'manual'"
                ))
            logger.info("Coluna 'origem' adicionada a sessoes_treino.")

        if "plano_semanal_clube_id" not in colunas_sessoes:
            if dialecto == "postgresql":
                ligacao.execute(text(
                    "ALTER TABLE sessoes_treino "
                    "ADD COLUMN IF NOT EXISTS plano_semanal_clube_id INTEGER REFERENCES planos_semanais_clube(id)"
                ))
            else:
                ligacao.execute(text(
                    "ALTER TABLE sessoes_treino "
                    "ADD COLUMN plano_semanal_clube_id INTEGER"
                ))
            logger.info("Coluna 'plano_semanal_clube_id' adicionada a sessoes_treino.")

        if "evento_planeamento_clube_id" not in colunas_sessoes:
            if dialecto == "postgresql":
                ligacao.execute(text(
                    "ALTER TABLE sessoes_treino "
                    "ADD COLUMN IF NOT EXISTS evento_planeamento_clube_id INTEGER REFERENCES eventos_planeamento_clube(id)"
                ))
            else:
                ligacao.execute(text(
                    "ALTER TABLE sessoes_treino "
                    "ADD COLUMN evento_planeamento_clube_id INTEGER"
                ))
            logger.info("Coluna 'evento_planeamento_clube_id' adicionada a sessoes_treino.")

        if "sincronizada" not in colunas_sessoes:
            if dialecto == "postgresql":
                ligacao.execute(text(
                    "ALTER TABLE sessoes_treino "
                    "ADD COLUMN IF NOT EXISTS sincronizada BOOLEAN NOT NULL DEFAULT FALSE"
                ))
            else:
                ligacao.execute(text(
                    "ALTER TABLE sessoes_treino "
                    "ADD COLUMN sincronizada BOOLEAN NOT NULL DEFAULT 0"
                ))
            logger.info("Coluna 'sincronizada' adicionada a sessoes_treino.")

        if "alterada_manual" not in colunas_sessoes:
            if dialecto == "postgresql":
                ligacao.execute(text(
                    "ALTER TABLE sessoes_treino "
                    "ADD COLUMN IF NOT EXISTS alterada_manual BOOLEAN NOT NULL DEFAULT FALSE"
                ))
            else:
                ligacao.execute(text(
                    "ALTER TABLE sessoes_treino "
                    "ADD COLUMN alterada_manual BOOLEAN NOT NULL DEFAULT 0"
                ))
            logger.info("Coluna 'alterada_manual' adicionada a sessoes_treino.")

        if "ativa" not in colunas_sessoes:
            if dialecto == "postgresql":
                ligacao.execute(text(
                    "ALTER TABLE sessoes_treino "
                    "ADD COLUMN IF NOT EXISTS ativa BOOLEAN NOT NULL DEFAULT TRUE"
                ))
            else:
                ligacao.execute(text(
                    "ALTER TABLE sessoes_treino "
                    "ADD COLUMN ativa BOOLEAN NOT NULL DEFAULT 1"
                ))
            logger.info("Coluna 'ativa' adicionada a sessoes_treino.")

        if "estado" not in colunas_sessoes:
            if dialecto == "postgresql":
                ligacao.execute(text(
                    "ALTER TABLE sessoes_treino "
                    "ADD COLUMN IF NOT EXISTS estado VARCHAR NOT NULL DEFAULT 'planeada'"
                ))
            else:
                ligacao.execute(text(
                    "ALTER TABLE sessoes_treino "
                    "ADD COLUMN estado VARCHAR NOT NULL DEFAULT 'planeada'"
                ))
            logger.info("Coluna 'estado' adicionada a sessoes_treino.")

        if "tipo_treino" not in colunas_sessoes:
            if dialecto == "postgresql":
                ligacao.execute(text(
                    "ALTER TABLE sessoes_treino "
                    "ADD COLUMN IF NOT EXISTS tipo_treino VARCHAR NOT NULL DEFAULT 'normal'"
                ))
            else:
                ligacao.execute(text(
                    "ALTER TABLE sessoes_treino "
                    "ADD COLUMN tipo_treino VARCHAR NOT NULL DEFAULT 'normal'"
                ))
            logger.info("Coluna 'tipo_treino' adicionada a sessoes_treino.")

    inspector = inspect(engine)
    if inspector.has_table("biblioteca_exercicios"):
        colunas_bib = {coluna["name"] for coluna in inspector.get_columns("biblioteca_exercicios")}
        with engine.begin() as ligacao:
            if "desenho" not in colunas_bib:
                if dialecto == "postgresql":
                    ligacao.execute(text(
                        "ALTER TABLE biblioteca_exercicios "
                        "ADD COLUMN IF NOT EXISTS desenho TEXT NULL"
                    ))
                else:
                    ligacao.execute(text(
                        "ALTER TABLE biblioteca_exercicios "
                        "ADD COLUMN desenho TEXT NULL"
                    ))
                logger.info("Coluna 'desenho' adicionada a biblioteca_exercicios.")

    inspector = inspect(engine)
    if inspector.has_table("exercicios_plano"):
        colunas_exercicios = {coluna["name"] for coluna in inspector.get_columns("exercicios_plano")}
        if "rpe" not in colunas_exercicios:
            with engine.begin() as ligacao:
                if dialecto == "postgresql":
                    ligacao.execute(text(
                        "ALTER TABLE exercicios_plano "
                        "ADD COLUMN IF NOT EXISTS rpe DOUBLE PRECISION NULL"
                    ))
                else:
                    ligacao.execute(text(
                        "ALTER TABLE exercicios_plano "
                        "ADD COLUMN rpe FLOAT NULL"
                    ))
            logger.info("Coluna 'rpe' adicionada a exercicios_plano.")

    inspector = inspect(engine)
    if inspector.has_table("biblioteca_exercicios"):
        colunas_biblioteca = {coluna["name"] for coluna in inspector.get_columns("biblioteca_exercicios")}
        if "tags" not in colunas_biblioteca:
            with engine.begin() as ligacao:
                if dialecto == "postgresql":
                    ligacao.execute(text(
                        "ALTER TABLE biblioteca_exercicios "
                        "ADD COLUMN IF NOT EXISTS tags VARCHAR NULL"
                    ))
                else:
                    ligacao.execute(text(
                        "ALTER TABLE biblioteca_exercicios ADD COLUMN tags VARCHAR NULL"
                    ))
            logger.info("Coluna 'tags' adicionada a biblioteca_exercicios.")


def actualizar_estrutura_planeamento_equipa() -> None:
    """Liga instalações existentes ao novo planeamento anual de equipa."""
    inspector = inspect(engine)
    if not inspector.has_table("macrociclos") or not inspector.has_table("planeamentos_anuais_equipa"):
        return

    colunas = {coluna["name"] for coluna in inspector.get_columns("macrociclos")}
    if "planeamento_anual_equipa_id" not in colunas:
        with engine.begin() as ligacao:
            if engine.dialect.name == "postgresql":
                ligacao.execute(text(
                    "ALTER TABLE macrociclos ADD COLUMN IF NOT EXISTS "
                    "planeamento_anual_equipa_id INTEGER "
                    "REFERENCES planeamentos_anuais_equipa(id) ON DELETE CASCADE"
                ))
                ligacao.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_macrociclos_planeamento_anual_equipa_id "
                    "ON macrociclos (planeamento_anual_equipa_id)"
                ))
            else:
                ligacao.execute(text(
                    "ALTER TABLE macrociclos ADD COLUMN planeamento_anual_equipa_id INTEGER"
                ))
        logger.info("Ligação anual adicionada aos macrociclos.")

    if inspector.has_table("sessoes_treino"):
        colunas_sessoes = {coluna["name"] for coluna in inspector.get_columns("sessoes_treino")}
        if "min_psicologicos" not in colunas_sessoes:
            with engine.begin() as ligacao:
                if engine.dialect.name == "postgresql":
                    ligacao.execute(text(
                        "ALTER TABLE sessoes_treino "
                        "ADD COLUMN IF NOT EXISTS min_psicologicos INTEGER NOT NULL DEFAULT 0"
                    ))
                else:
                    ligacao.execute(text(
                        "ALTER TABLE sessoes_treino "
                        "ADD COLUMN min_psicologicos INTEGER NOT NULL DEFAULT 0"
                    ))
            logger.info("Coluna 'min_psicologicos' adicionada a sessoes_treino.")

    from models.planeamento import Macrociclo, PlaneamentoAnualEquipa
    from models.planeamento_clube import PlaneamentoClubeAnual

    db = SessionLocal()
    try:
        macros = db.query(Macrociclo).filter(Macrociclo.planeamento_anual_equipa_id.is_(None)).all()
        for macro in macros:
            ano_inicio = macro.data_inicio.year if macro.data_inicio.month >= 7 else macro.data_inicio.year - 1
            epoca = f"{ano_inicio}/{ano_inicio + 1}"
            anual = db.query(PlaneamentoAnualEquipa).filter(
                PlaneamentoAnualEquipa.equipa_id == macro.equipa_id,
                PlaneamentoAnualEquipa.epoca == epoca,
            ).first()
            if not anual:
                anual_clube = db.query(PlaneamentoClubeAnual).filter(
                    PlaneamentoClubeAnual.clube_id == macro.clube_id,
                    PlaneamentoClubeAnual.data_inicio <= macro.data_inicio,
                    PlaneamentoClubeAnual.data_fim >= macro.data_fim,
                ).first()
                anual = PlaneamentoAnualEquipa(
                    clube_id=macro.clube_id,
                    equipa_id=macro.equipa_id,
                    planeamento_clube_anual_id=anual_clube.id if anual_clube else None,
                    epoca=epoca,
                    titulo=f"Planeamento anual {epoca}",
                    data_inicio=macro.data_inicio,
                    data_fim=macro.data_fim,
                    objetivos_gerais=anual_clube.objetivos_gerais if anual_clube else None,
                )
                db.add(anual)
                db.flush()
            else:
                anual.data_inicio = min(anual.data_inicio, macro.data_inicio)
                anual.data_fim = max(anual.data_fim, macro.data_fim)
            macro.planeamento_anual_equipa_id = anual.id
        db.commit()
        if macros:
            logger.info("%s macrociclo(s) associados ao planeamento anual da equipa.", len(macros))
    finally:
        db.close()


def actualizar_estrutura_assiduidade() -> None:
    """Atualiza instalações antigas com o estado detalhado de assiduidade."""
    inspector = inspect(engine)
    if not inspector.has_table("assiduidade"):
        return

    colunas = {coluna["name"] for coluna in inspector.get_columns("assiduidade")}
    if "estado" in colunas:
        return

    dialecto = engine.dialect.name
    with engine.begin() as ligacao:
        if dialecto == "postgresql":
            ligacao.execute(text(
                "ALTER TABLE assiduidade "
                "ADD COLUMN IF NOT EXISTS estado VARCHAR NOT NULL DEFAULT 'ausente'"
            ))
        else:
            ligacao.execute(text(
                "ALTER TABLE assiduidade "
                "ADD COLUMN estado VARCHAR NOT NULL DEFAULT 'ausente'"
            ))
        ligacao.execute(text(
            "UPDATE assiduidade SET estado = "
            "CASE WHEN presente THEN 'presente' ELSE 'ausente' END"
        ))
    logger.info("Coluna 'estado' adicionada a assiduidade.")


def actualizar_estrutura_jogadores() -> None:
    """Adiciona suporte de fotografia a instalações anteriores às migrações."""
    inspector = inspect(engine)
    if not inspector.has_table("jogadores"):
        return
    colunas = {coluna["name"] for coluna in inspector.get_columns("jogadores")}
    if "fotografia" in colunas:
        return
    with engine.begin() as ligacao:
        if engine.dialect.name == "postgresql":
            ligacao.execute(text("ALTER TABLE jogadores ADD COLUMN IF NOT EXISTS fotografia VARCHAR NULL"))
        else:
            ligacao.execute(text("ALTER TABLE jogadores ADD COLUMN fotografia VARCHAR NULL"))
    logger.info("Coluna 'fotografia' adicionada a jogadores.")

# Função que abre e fecha sessões automaticamente
# O "yield" faz com que a sessão seja fechada no final de cada pedido
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
