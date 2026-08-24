"""Exportações portáteis, limitadas aos dados de uma equipa."""

from datetime import date, datetime
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy.inspection import inspect as sa_inspect
from sqlalchemy.orm import Session

from auth_deps import exigir_coordenacao, exigir_operacao_desportiva, verificar_ou_negar_equipa
from database import Base, get_db
from models.assiduidade import RegistoAssiduidade
from models.documento_jogador import DocumentoJogador
from models.equipa import Equipa
from models.espaco_agenda import AgendaEspacoEquipa
from models.fisico import PlaneamentoFisico, TesteFisico
from models.jogador import Jogador, RegistoAntropometrico
from models.jogo import Convocado, Jogo, PlanoJogo
from models.planeamento import (
    ConteudoSessaoTreino, Macrociclo, Mesociclo, Microciclo,
    PlaneamentoAnualEquipa, SessaoTreino,
)
from models.treino import BlocoTreino, ExercicioPlano, PlanoTreino
from services.fotografia_jogador_service import caminho_fotografia
from services.auditoria_service import registar_auditoria

router = APIRouter(prefix="/exportacoes", tags=["exportacoes"])


def _valor_excel(valor):
    """Converte enums e datas para valores que o Excel consegue abrir."""
    if valor is None or isinstance(valor, (str, int, float, bool, date, datetime)):
        return valor
    return getattr(valor, "value", str(valor))


def _criar_excel(
    titulo: str,
    conjuntos: list[tuple[str, list]],
    excluir_por_folha: dict[str, set[str]] | None = None,
) -> bytes:
    livro = Workbook()
    livro.remove(livro.active)
    for nome, linhas in conjuntos:
        folha = livro.create_sheet(nome[:31])
        if not linhas:
            folha.append(["Sem registos"])
            continue
        excluidas = (excluir_por_folha or {}).get(nome, set())
        colunas = [
            coluna.key for coluna in sa_inspect(linhas[0]).mapper.column_attrs
            if coluna.key not in excluidas
        ]
        folha.append(colunas)
        for celula in folha[1]:
            celula.font = celula.font.copy(bold=True)
        for linha in linhas:
            folha.append([_valor_excel(getattr(linha, coluna)) for coluna in colunas])
        folha.freeze_panes = "A2"
        folha.auto_filter.ref = folha.dimensions
    resultado = BytesIO()
    livro.save(resultado)
    return resultado.getvalue()


def _adicionar_fotografias(zipado: ZipFile, jogadores: list[Jogador]) -> None:
    for jogador in jogadores:
        fotografia = caminho_fotografia(jogador.fotografia)
        if fotografia and fotografia.is_file():
            zipado.write(fotografia, f"Ficheiros/fotografias/{jogador.id}_{fotografia.name}")


@router.get("/equipas/{equipa_id}/dados")
def exportar_dados_equipa(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    """Descarrega um ZIP editável apenas com informação ligada à equipa indicada."""
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if equipa is None:  # Defesa adicional caso a equipa seja eliminada durante o pedido.
        verificar_ou_negar_equipa(utilizador, equipa_id, db)

    jogadores = db.query(Jogador).filter(Jogador.equipa_id == equipa_id).all()
    jogadores_ids = [jogador.id for jogador in jogadores]
    jogos = db.query(Jogo).filter(Jogo.equipa_id == equipa_id).all()
    jogos_ids = [jogo.id for jogo in jogos]
    anuais = db.query(PlaneamentoAnualEquipa).filter(PlaneamentoAnualEquipa.equipa_id == equipa_id).all()
    macros = db.query(Macrociclo).filter(Macrociclo.equipa_id == equipa_id).all()
    macros_ids = [macro.id for macro in macros]
    mesos = db.query(Mesociclo).filter(Mesociclo.macrociclo_id.in_(macros_ids)).all() if macros_ids else []
    mesos_ids = [meso.id for meso in mesos]
    micros = db.query(Microciclo).filter(Microciclo.mesociclo_id.in_(mesos_ids)).all() if mesos_ids else []
    micros_ids = [micro.id for micro in micros]
    sessoes = db.query(SessaoTreino).filter(SessaoTreino.microciclo_id.in_(micros_ids)).all() if micros_ids else []
    sessoes_ids = [sessao.id for sessao in sessoes]
    planos = db.query(PlanoTreino).filter(PlanoTreino.sessao_id.in_(sessoes_ids)).all() if sessoes_ids else []
    planos_ids = [plano.id for plano in planos]

    atletas = [
        ("Equipa e atletas", [("equipa", [equipa]), ("atletas", jogadores)]),
        ("Jogos", [
            ("jogos", jogos),
            ("convocados", db.query(Convocado).filter(Convocado.jogo_id.in_(jogos_ids)).all() if jogos_ids else []),
            ("planos_jogo", db.query(PlanoJogo).filter(PlanoJogo.jogo_id.in_(jogos_ids)).all() if jogos_ids else []),
        ]),
        ("Planeamento", [("anual", anuais), ("macrociclos", macros), ("mesociclos", mesos), ("microciclos", micros)]),
        ("Treinos", [
            ("sessoes", sessoes),
            ("planos", planos),
            ("blocos", db.query(BlocoTreino).filter(BlocoTreino.plano_id.in_(planos_ids)).all() if planos_ids else []),
            ("exercicios", db.query(ExercicioPlano).filter(ExercicioPlano.plano_id.in_(planos_ids)).all() if planos_ids else []),
            ("conteudos", db.query(ConteudoSessaoTreino).filter(ConteudoSessaoTreino.sessao_id.in_(sessoes_ids)).all() if sessoes_ids else []),
        ]),
        ("Atletas e assiduidade", [
            ("assiduidade", db.query(RegistoAssiduidade).filter(RegistoAssiduidade.sessao_id.in_(sessoes_ids)).filter(RegistoAssiduidade.jogador_id.in_(jogadores_ids)).all() if sessoes_ids and jogadores_ids else []),
            ("testes_fisicos", db.query(TesteFisico).filter(TesteFisico.jogador_id.in_(jogadores_ids)).all() if jogadores_ids else []),
            ("antropometria", db.query(RegistoAntropometrico).filter(RegistoAntropometrico.jogador_id.in_(jogadores_ids)).all() if jogadores_ids else []),
            ("documentos", db.query(DocumentoJogador).filter(DocumentoJogador.jogador_id.in_(jogadores_ids)).all() if jogadores_ids else []),
        ]),
        ("Agenda e fisico", [
            ("agenda_espacos", db.query(AgendaEspacoEquipa).filter(AgendaEspacoEquipa.equipa_id == equipa_id).all()),
            ("planeamento_fisico", db.query(PlaneamentoFisico).filter(PlaneamentoFisico.equipa_id == equipa_id).all()),
        ]),
    ]

    ficheiro = BytesIO()
    with ZipFile(ficheiro, "w", ZIP_DEFLATED) as zipado:
        for pasta, conjuntos in atletas:
            nome = pasta.lower().replace(" ", "_") + ".xlsx"
            zipado.writestr(f"{pasta}/{nome}", _criar_excel(pasta, conjuntos))
        _adicionar_fotografias(zipado, jogadores)
        zipado.writestr(
            "LEIA-ME.txt",
            "Exportação editável da equipa. Cada ficheiro Excel contém folhas independentes; "
            "alterar estes ficheiros não altera automaticamente os dados da plataforma.\n",
        )

    registar_auditoria(
        db, utilizador, "exportou", "dados_equipa", equipa_id,
        f"Exportação editável da equipa {equipa.nome}.", request,
    )
    db.commit()
    ficheiro.seek(0)
    nome_seguro = "".join(caracter if caracter.isalnum() else "_" for caracter in equipa.nome)
    return StreamingResponse(
        ficheiro,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="dados_equipa_{nome_seguro}.zip"'},
    )


@router.get("/clube/dados")
def exportar_dados_clube(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    """Descarrega todos os dados exportáveis do clube do utilizador."""
    clube = getattr(request.state, "clube_atual", None)
    if clube is None:
        raise HTTPException(status_code=403, detail="Seleciona um clube antes de exportar dados.")

    tabelas_excluidas = {"tokens_recuperacao_password"}
    colunas_sensiveis = {
        "utilizadores": {"password_hash", "sessao_versao"},
    }
    conjuntos = [("clube", [clube])]
    for mapper in sorted(Base.registry.mappers, key=lambda item: item.class_.__tablename__):
        modelo = mapper.class_
        nome_tabela = modelo.__tablename__
        if nome_tabela in tabelas_excluidas or not hasattr(modelo, "clube_id"):
            continue
        registos = db.query(modelo).filter(modelo.clube_id == clube.id).all()
        conjuntos.append((nome_tabela, registos))

    jogadores = db.query(Jogador).filter(Jogador.clube_id == clube.id).all()
    ficheiro = BytesIO()
    with ZipFile(ficheiro, "w", ZIP_DEFLATED) as zipado:
        zipado.writestr(
            "Dados_do_clube/dados_do_clube.xlsx",
            _criar_excel("Dados do clube", conjuntos, colunas_sensiveis),
        )
        _adicionar_fotografias(zipado, jogadores)
        zipado.writestr(
            "LEIA-ME.txt",
            "Exportação editável de todos os dados do clube. Credenciais, hashes de palavra-passe "
            "e tokens de recuperação são deliberadamente excluídos. Alterar os ficheiros não altera "
            "automaticamente os dados da plataforma.\n",
        )

    registar_auditoria(
        db, utilizador, "exportou", "dados_clube", clube.id,
        f"Exportação editável completa do clube {clube.nome_curto}.", request,
    )
    db.commit()
    ficheiro.seek(0)
    nome_seguro = "".join(caracter if caracter.isalnum() else "_" for caracter in clube.nome_curto)
    return StreamingResponse(
        ficheiro,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="dados_clube_{nome_seguro}.zip"'},
    )
