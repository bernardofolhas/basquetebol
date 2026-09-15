from sqlalchemy import Boolean, Column, Integer, String, Date, ForeignKey, Text
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import backref, relationship
from database import Base


class MedidaAntropometrica(TypeDecorator):
    """Lê instalações antigas varchar e expõe números quando são válidos."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return str(value) if value is not None else None

    def process_result_value(self, value, dialect):
        if value is None or value == "":
            return None
        try:
            return float(str(value).replace(",", "."))
        except (TypeError, ValueError):
            return value


class Jogador(Base):
    __tablename__ = "jogadores"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    # Informações básicas
    nome = Column(String, nullable=False)
    data_nascimento = Column(Date, nullable=True)
    naturalidade = Column(String, nullable=True)
    morada = Column(String, nullable=True)
    numero_camisola = Column(Integer, nullable=True)
    posicao = Column(String, nullable=True)
    posicao_secundaria = Column(String, nullable=True)
    fotografia = Column(String, nullable=True)
    ativo = Column(Boolean, nullable=False, default=True)

    # Contactos do jogador
    telefone = Column(String, nullable=True)
    email = Column(String, nullable=True)

    # Contactos dos pais
    nome_pai = Column(String, nullable=True)
    telefone_pai = Column(String, nullable=True)
    email_pai = Column(String, nullable=True)
    nome_mae = Column(String, nullable=True)
    telefone_mae = Column(String, nullable=True)
    email_mae = Column(String, nullable=True)

    # Informações desportivas (a preencher pelo treinador)
    resumo_tecnico = Column(Text, nullable=True)
    objetivos_medio_prazo = Column(Text, nullable=True)
    objetivos_longo_prazo = Column(Text, nullable=True)

    # Equipa actual
    equipa_id = Column(Integer, ForeignKey("equipas.id"), nullable=True)
    equipa = relationship("Equipa", backref="jogadores")
    # Inscrições
    inscricao_estado = Column(String, nullable=True)  # "pendente", "completa", "rejeitada"
    inscricao_observacoes = Column(Text, nullable=True)

    # Exames médicos
    exame_medico_data = Column(Date, nullable=True)
    exame_medico_validade = Column(Date, nullable=True)  # Data de validade
    exame_medico_estado = Column(String, nullable=True)  # "válido", "expirado", "pendente"
    exame_medico_observacoes = Column(Text, nullable=True)


class RegistoAntropometrico(Base):
    # Tabela separada para os registos antropométricos
    # Assim podemos guardar vários registos ao longo do tempo
    __tablename__ = "registos_antropometricos"
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)

    id = Column(Integer, primary_key=True, index=True)
    jogador_id = Column(Integer, ForeignKey("jogadores.id", ondelete="CASCADE"), nullable=False)
    data = Column(Date, nullable=False)
    altura = Column(MedidaAntropometrica, nullable=True)
    peso = Column(MedidaAntropometrica, nullable=True)
    envergadura = Column(MedidaAntropometrica, nullable=True)
    altura_sentado = Column(MedidaAntropometrica, nullable=True)

    # Relação com o jogador
    jogador = relationship(
        "Jogador",
        backref=backref("registos_antropometricos", cascade="all, delete-orphan", passive_deletes=True),
    )
