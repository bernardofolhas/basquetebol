from sqlalchemy import Column, Integer, String, Date, Text, ForeignKey
from sqlalchemy.orm import relationship
from database import Base

class Atividade(Base):
    __tablename__ = "atividades"

    id = Column(Integer, primary_key=True, index=True)
    clube_id = Column(Integer, ForeignKey("clubes.id", ondelete="RESTRICT"), nullable=False, index=True)
    titulo = Column(String, nullable=False)
    data = Column(Date, nullable=False)
    local = Column(String, nullable=True)
    tipo = Column(String, nullable=True)  # Ex: "Formação", "Social", "Evento"
    descricao = Column(Text, nullable=True)
    observacoes = Column(Text, nullable=True)
