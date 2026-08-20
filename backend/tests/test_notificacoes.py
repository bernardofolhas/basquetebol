from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from clube_contexto import definir_clube_atual, repor_clube_atual
from database import Base
from models.clube import Clube
from models.equipa import Equipa, EscalaoEnum, GeneroEnum
from models.notificacao import Notificacao
from models.treinador import Treinador
from models.utilizador import PerfilEnum, Utilizador
from services.notificacoes_service import criar_notificacoes_para_equipa


def test_envio_para_equipa_cria_aviso_apenas_para_os_seus_treinadores():
    db = sessionmaker(bind=create_engine("sqlite:///:memory:"))()
    Base.metadata.create_all(db.bind)
    token = definir_clube_atual(1)
    try:
        clube = Clube(id=1, nome_oficial="Clube Teste", nome_curto="Teste", identificador="teste")
        equipa = Equipa(id=1, clube_id=1, nome="Sub-18", escalao=EscalaoEnum.sub18, genero=GeneroEnum.feminino)
        treinador = Treinador(id=1, clube_id=1, nome="Treinador")
        treinador.equipas.append(equipa)
        utilizador = Utilizador(
            id=1, clube_id=1, nome="Treinador", username="treinador-aviso", email="treinador@teste.pt",
            password_hash="hash", perfil=PerfilEnum.treinador, treinador=treinador,
        )
        db.add_all([clube, equipa, treinador, utilizador])
        db.commit()

        total = criar_notificacoes_para_equipa(db, equipa, "Treino atualizado", "Pavilhão", "/calendario")
        db.commit()

        assert total == 1
        aviso = db.query(Notificacao).one()
        assert aviso.utilizador_id == utilizador.id
        assert aviso.lida is False
    finally:
        db.close()
        repor_clube_atual(token)
