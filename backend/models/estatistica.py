from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import backref, relationship

from database import Base


class EventoEstatistica(Base):
    """Ação atómica de um jogo, sincronizável e anulável sem perder histórico."""

    __tablename__ = "eventos_estatistica"

    id = Column(Integer, primary_key=True, index=True)
    client_uid = Column(String(80), nullable=False, unique=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    equipa_id = Column(Integer, ForeignKey("equipas.id", ondelete="CASCADE"), nullable=False, index=True)
    jogo_id = Column(Integer, ForeignKey("jogos.id", ondelete="CASCADE"), nullable=False, index=True)
    jogador_id = Column(Integer, ForeignKey("jogadores.id", ondelete="SET NULL"), nullable=True, index=True)
    registado_por_id = Column(Integer, ForeignKey("utilizadores.id", ondelete="SET NULL"), nullable=True)
    lado = Column(String(16), nullable=False, default="equipa", server_default="equipa")
    tipo = Column(String(32), nullable=False, index=True)
    periodo = Column(Integer, nullable=False, default=1, server_default="1")
    segundos_restantes = Column(Integer, nullable=True)
    posicao_x = Column(Float, nullable=True)
    posicao_y = Column(Float, nullable=True)
    origem = Column(String(24), nullable=False, default="manual", server_default="manual", index=True)
    identificador_externo = Column(String(160), nullable=True)
    jogador_externo = Column(String(120), nullable=True)
    subtipo = Column(String(60), nullable=True)
    qualificadores = Column(Text, nullable=True)
    importacao_uid = Column(String(80), nullable=True, index=True)
    segundos_jogados_oficiais = Column(Integer, nullable=True)
    anulado = Column(Boolean, nullable=False, default=False, server_default="false")
    criado_em = Column(DateTime, nullable=False, default=datetime.now)
    atualizado_em = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    jogo = relationship(
        "Jogo",
        backref=backref("eventos_estatistica", cascade="all, delete-orphan", passive_deletes=True),
    )
    jogador = relationship("Jogador")
    registado_por = relationship("Utilizador")


class MapeamentoJogadorEstatistica(Base):
    """Associa um atleta de um fornecedor externo ao atleta local da equipa."""

    __tablename__ = "mapeamentos_jogadores_estatistica"
    __table_args__ = (
        UniqueConstraint(
            "equipa_id",
            "fornecedor",
            "identificador_externo",
            name="uq_mapeamento_estatistica_equipa_fornecedor_externo",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="CASCADE"), nullable=False, index=True)
    equipa_id = Column(Integer, ForeignKey("equipas.id", ondelete="CASCADE"), nullable=False, index=True)
    jogador_id = Column(Integer, ForeignKey("jogadores.id", ondelete="CASCADE"), nullable=False, index=True)
    fornecedor = Column(String(24), nullable=False, default="fiba", server_default="fiba")
    identificador_externo = Column(String(120), nullable=False)
    nome_externo = Column(String(160), nullable=True)
    numero_externo = Column(String(16), nullable=True)
    criado_em = Column(DateTime, nullable=False, default=datetime.now)
    atualizado_em = Column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    jogador = relationship("Jogador")
