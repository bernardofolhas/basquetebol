"""Backups editáveis e isolados por clube e equipa."""

import json
import re
import unicodedata
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy import and_, or_, select
from sqlalchemy.inspection import inspect as sa_inspect
from sqlalchemy.orm import Session

from auth_deps import exigir_coordenacao, exigir_operacao_desportiva, verificar_ou_negar_equipa
from database import get_db
from models.assiduidade import RegistoAssiduidade
from models.atividade import Atividade
from models.atribuicao_espaco_semanal import AtribuicaoEspacoSemanal
from models.auditoria import RegistoAuditoria
from models.documento_jogador import DocumentoJogador
from models.equipa import Equipa
from models.espaco_agenda import AgendaEspacoEquipa
from models.espaco_treino import DisponibilidadeEspacoTreino, EspacoTreino, IndisponibilidadeEspacoTreino
from models.fisico import PlaneamentoFisico, TesteFisico
from models.identidade_clube import IdentidadeClube
from models.indisponibilidade_treinador import IndisponibilidadeTreinador
from models.historico_planeamento import HistoricoPlaneamentoClube
from models.jogador import Jogador, RegistoAntropometrico
from models.jogo import Convocado, Jogo, PlanoJogo
from models.notificacao import Notificacao
from models.planeamento import (
    ConteudoSessaoTreino,
    Macrociclo,
    Mesociclo,
    Microciclo,
    PlaneamentoAnualEquipa,
    SessaoTreino,
)
from models.planeamento_clube import (
    EventoPlaneamentoClube,
    PlaneamentoClubeAnual,
    PlaneamentoClubeMensal,
    PlanoSemanalClube,
    evento_planeamento_clube_equipa,
)
from models.playbook import PassoSetPlay, Playbook, SetPlay
from models.treinador import Treinador, treinador_equipa
from models.treino import BibliotecoExercicio, BlocoTreino, ExercicioPlano, PlanoTreino
from models.utilizador import Utilizador
from paths import STATIC_DIR
from services.auditoria_service import registar_auditoria
from services.fotografia_jogador_service import caminho_fotografia
from services.identidade_clube_service import caminho_ficheiro_logo

router = APIRouter(prefix="/exportacoes", tags=["exportacoes"])

COLUNAS_SENSIVEIS = {"utilizadores": {"password_hash", "sessao_versao"}}
LIMITE_TEXTO_EXCEL = 32_000


def _nome_seguro(valor: str, fallback: str = "dados") -> str:
    normalizado = unicodedata.normalize("NFKD", valor or "")
    ascii_texto = normalizado.encode("ascii", "ignore").decode("ascii")
    nome = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_texto).strip("._-")
    return nome or fallback


def _valor_serializavel(valor):
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    if isinstance(valor, (date, datetime)):
        return valor.isoformat()
    return getattr(valor, "value", str(valor))


def _valor_excel(valor):
    """Mantém datas editáveis e neutraliza fórmulas introduzidas nos dados."""
    if valor is None or isinstance(valor, (int, float, bool, date, datetime)):
        return valor
    texto = str(getattr(valor, "value", valor))
    if texto.startswith(("=", "+", "-", "@")):
        texto = "'" + texto
    if len(texto) > LIMITE_TEXTO_EXCEL:
        return texto[:LIMITE_TEXTO_EXCEL] + "\n[Conteúdo integral no JSON desta pasta]"
    return texto


def _registo_para_dict(registo, excluir: set[str] | None = None) -> dict:
    if isinstance(registo, dict):
        return {str(chave): _valor_serializavel(valor) for chave, valor in registo.items()}
    excluidas = excluir or set()
    return {
        coluna.key: _valor_serializavel(getattr(registo, coluna.key))
        for coluna in sa_inspect(registo).mapper.column_attrs
        if coluna.key not in excluidas
    }


def _dados_conjunto(nome: str, linhas: list) -> list[dict]:
    return [_registo_para_dict(linha, COLUNAS_SENSIVEIS.get(nome, set())) for linha in linhas]


def _criar_excel(titulo: str, conjuntos: list[tuple[str, list]]) -> bytes:
    livro = Workbook()
    livro.remove(livro.active)
    livro.properties.title = titulo
    livro.properties.creator = "Plataforma de Gestão de Basquetebol"

    for nome, linhas in conjuntos:
        folha = livro.create_sheet(nome[:31])
        dados = _dados_conjunto(nome, linhas)
        if not dados:
            folha.append(["Sem registos"])
            folha["A1"].font = Font(bold=True, color="64748B")
            folha.column_dimensions["A"].width = 22
            continue

        colunas = list(dados[0].keys())
        folha.append(colunas)
        for celula in folha[1]:
            celula.font = Font(bold=True, color="FFFFFF")
            celula.fill = PatternFill("solid", fgColor="1E293B")
            celula.alignment = Alignment(vertical="center")
        folha.row_dimensions[1].height = 24
        for registo in dados:
            folha.append([_valor_excel(registo.get(coluna)) for coluna in colunas])

        for indice, coluna in enumerate(colunas, start=1):
            maior = max(len(str(coluna)), *(len(str(linha.get(coluna) or "")) for linha in dados))
            folha.column_dimensions[folha.cell(1, indice).column_letter].width = min(max(maior + 2, 12), 48)
        for linha in folha.iter_rows(min_row=2):
            for celula in linha:
                celula.alignment = Alignment(vertical="top", wrap_text=True)
        folha.freeze_panes = "A2"
        folha.auto_filter.ref = folha.dimensions

    resultado = BytesIO()
    livro.save(resultado)
    return resultado.getvalue()


def _adicionar_tema(zipado: ZipFile, pasta: str, titulo: str, conjuntos: list[tuple[str, list]]) -> None:
    nome = _nome_seguro(titulo).lower()
    zipado.writestr(f"{pasta}/{nome}.xlsx", _criar_excel(titulo, conjuntos))
    integral = {nome_folha: _dados_conjunto(nome_folha, linhas) for nome_folha, linhas in conjuntos}
    zipado.writestr(f"{pasta}/{nome}_integral.json", json.dumps(integral, ensure_ascii=False, indent=2))


def _adicionar_fotografias(zipado: ZipFile, jogadores: list[Jogador], prefixo: str) -> None:
    for jogador in jogadores:
        fotografia = caminho_fotografia(jogador.fotografia)
        if fotografia and fotografia.is_file():
            zipado.write(
                fotografia,
                f"{prefixo}/Ficheiros/Fotografias/{jogador.id}_{_nome_seguro(fotografia.name)}",
            )


def _adicionar_logos(zipado: ZipFile, clube, identidade: IdentidadeClube | None) -> None:
    urls = {
        "logo_principal_clube": clube.logo_principal,
        "logo_secundario_clube": clube.logo_secundario,
        "logo_principal_identidade": getattr(identidade, "logo_principal", None),
        "logo_secundario_identidade": getattr(identidade, "logo_secundario", None),
    }
    adicionados: set[Path] = set()
    for nome, url in urls.items():
        caminho = caminho_ficheiro_logo(STATIC_DIR, url)
        if caminho and caminho.is_file() and caminho not in adicionados:
            adicionados.add(caminho)
            zipado.write(caminho, f"00_Clube/Ficheiros/Logotipos/{nome}{caminho.suffix.lower()}")


def _linhas_associacao(db: Session, tabela, condicao) -> list[dict]:
    return [dict(linha) for linha in db.execute(select(tabela).where(condicao)).mappings().all()]


def _conteudo_equipa(db: Session, equipa: Equipa) -> tuple[list[tuple[str, str, list]], list[Jogador]]:
    equipa_id = equipa.id
    jogadores = db.query(Jogador).filter(Jogador.equipa_id == equipa_id).order_by(Jogador.nome).all()
    jogadores_ids = [jogador.id for jogador in jogadores]
    jogos = db.query(Jogo).filter(Jogo.equipa_id == equipa_id).order_by(Jogo.data).all()
    jogos_ids = [jogo.id for jogo in jogos]

    anuais = db.query(PlaneamentoAnualEquipa).filter(PlaneamentoAnualEquipa.equipa_id == equipa_id).all()
    macros = db.query(Macrociclo).filter(Macrociclo.equipa_id == equipa_id).order_by(Macrociclo.data_inicio).all()
    macros_ids = [macro.id for macro in macros]
    mesos = db.query(Mesociclo).filter(Mesociclo.macrociclo_id.in_(macros_ids)).order_by(Mesociclo.data_inicio).all() if macros_ids else []
    mesos_ids = [meso.id for meso in mesos]
    micros = db.query(Microciclo).filter(Microciclo.mesociclo_id.in_(mesos_ids)).order_by(Microciclo.data_inicio).all() if mesos_ids else []
    micros_ids = [micro.id for micro in micros]
    sessoes = db.query(SessaoTreino).filter(SessaoTreino.microciclo_id.in_(micros_ids)).order_by(SessaoTreino.data).all() if micros_ids else []
    sessoes_ids = [sessao.id for sessao in sessoes]
    planos = db.query(PlanoTreino).filter(PlanoTreino.sessao_id.in_(sessoes_ids)).all() if sessoes_ids else []
    planos_ids = [plano.id for plano in planos]

    relacoes_treinadores = _linhas_associacao(db, treinador_equipa, treinador_equipa.c.equipa_id == equipa_id)
    treinadores_ids = [linha["treinador_id"] for linha in relacoes_treinadores]
    treinadores = db.query(Treinador).filter(Treinador.id.in_(treinadores_ids)).order_by(Treinador.nome).all() if treinadores_ids else []
    utilizadores = db.query(Utilizador).filter(Utilizador.treinador_id.in_(treinadores_ids)).all() if treinadores_ids else []

    eventos_associados = select(evento_planeamento_clube_equipa.c.evento_id).where(
        evento_planeamento_clube_equipa.c.equipa_id == equipa_id
    )
    eventos = db.query(EventoPlaneamentoClube).filter(
        EventoPlaneamentoClube.clube_id == equipa.clube_id,
        or_(
            EventoPlaneamentoClube.equipa_id == equipa_id,
            EventoPlaneamentoClube.aplica_a_todas_equipas.is_(True),
            EventoPlaneamentoClube.id.in_(eventos_associados),
        ),
    ).order_by(EventoPlaneamentoClube.data).all()
    eventos_ids = [evento.id for evento in eventos]
    relacoes_eventos = _linhas_associacao(
        db, evento_planeamento_clube_equipa, evento_planeamento_clube_equipa.c.evento_id.in_(eventos_ids)
    ) if eventos_ids else []
    atividades_ids = [evento.atividade_id for evento in eventos if evento.atividade_id]

    playbooks = db.query(Playbook).filter(Playbook.equipa_id == equipa_id).all()
    playbooks_ids = [playbook.id for playbook in playbooks]
    setplays = db.query(SetPlay).filter(SetPlay.playbook_id.in_(playbooks_ids)).all() if playbooks_ids else []
    setplays_ids = [setplay.id for setplay in setplays]
    agenda_espacos = db.query(AgendaEspacoEquipa).filter(AgendaEspacoEquipa.equipa_id == equipa_id).all()
    atribuicoes_espacos = db.query(AtribuicaoEspacoSemanal).filter(
        AtribuicaoEspacoSemanal.equipa_id == equipa_id
    ).all()
    espacos_ids = {
        item.espaco_id for item in [*agenda_espacos, *atribuicoes_espacos] if item.espaco_id
    }
    espacos = db.query(EspacoTreino).filter(EspacoTreino.id.in_(espacos_ids)).all() if espacos_ids else []

    temas = [
        ("00_Equipa", "equipa_e_equipa_tecnica", [
            ("equipa", [equipa]), ("treinadores", treinadores),
            ("treinador_equipa", relacoes_treinadores), ("utilizadores", utilizadores),
        ]),
        ("01_Plantel", "plantel", [
            ("jogadores", jogadores),
            ("documentos_jogadores", db.query(DocumentoJogador).filter(DocumentoJogador.jogador_id.in_(jogadores_ids)).all() if jogadores_ids else []),
            ("registos_antropometricos", db.query(RegistoAntropometrico).filter(RegistoAntropometrico.jogador_id.in_(jogadores_ids)).all() if jogadores_ids else []),
            ("testes_fisicos", db.query(TesteFisico).filter(TesteFisico.jogador_id.in_(jogadores_ids)).all() if jogadores_ids else []),
        ]),
        ("02_Planeamento", "planeamento_da_equipa", [
            ("planeamentos_anuais_equipa", anuais), ("macrociclos", macros),
            ("mesociclos", mesos), ("microciclos", micros),
            ("eventos_planeamento_clube", eventos), ("evento_planeamento_equipas", relacoes_eventos),
            ("atividades", db.query(Atividade).filter(Atividade.id.in_(atividades_ids)).all() if atividades_ids else []),
        ]),
        ("03_Treinos", "treinos_e_planos", [
            ("sessoes_treino", sessoes),
            ("conteudos_sessao_treino", db.query(ConteudoSessaoTreino).filter(ConteudoSessaoTreino.sessao_id.in_(sessoes_ids)).all() if sessoes_ids else []),
            ("planos_treino", planos),
            ("blocos_treino", db.query(BlocoTreino).filter(BlocoTreino.plano_id.in_(planos_ids)).all() if planos_ids else []),
            ("exercicios_plano", db.query(ExercicioPlano).filter(ExercicioPlano.plano_id.in_(planos_ids)).all() if planos_ids else []),
            ("registos_assiduidade", db.query(RegistoAssiduidade).filter(RegistoAssiduidade.sessao_id.in_(sessoes_ids)).all() if sessoes_ids else []),
        ]),
        ("04_Jogos", "jogos_convocatorias_e_planos", [
            ("jogos", jogos),
            ("convocados", db.query(Convocado).filter(Convocado.jogo_id.in_(jogos_ids)).all() if jogos_ids else []),
            ("planos_jogo", db.query(PlanoJogo).filter(PlanoJogo.jogo_id.in_(jogos_ids)).all() if jogos_ids else []),
        ]),
        ("05_Preparacao_fisica", "preparacao_fisica", [
            ("planeamentos_fisicos", db.query(PlaneamentoFisico).filter(PlaneamentoFisico.equipa_id == equipa_id).all()),
        ]),
        ("06_Playbook", "playbook", [
            ("playbooks", playbooks), ("setplays", setplays),
            ("passos_setplay", db.query(PassoSetPlay).filter(PassoSetPlay.setplay_id.in_(setplays_ids)).all() if setplays_ids else []),
        ]),
        ("07_Agenda_e_espacos", "agenda_e_espacos", [
            ("espacos_treino", espacos),
            ("agenda_espaco_equipa", agenda_espacos),
            ("atribuicoes_espaco_semanais", atribuicoes_espacos),
        ]),
        ("08_Biblioteca", "biblioteca_de_exercicios_do_clube", [
            ("biblioteca_exercicios", db.query(BibliotecoExercicio).filter(BibliotecoExercicio.clube_id == equipa.clube_id).all()),
        ]),
    ]
    return temas, jogadores


def _escrever_equipa(zipado: ZipFile, db: Session, equipa: Equipa, raiz: str) -> dict:
    temas, jogadores = _conteudo_equipa(db, equipa)
    contagens = {}
    for pasta, titulo, conjuntos in temas:
        _adicionar_tema(zipado, f"{raiz}/{pasta}", titulo, conjuntos)
        contagens[pasta] = sum(len(linhas) for _, linhas in conjuntos)
    _adicionar_fotografias(zipado, jogadores, f"{raiz}/01_Plantel")
    return contagens


def _escrever_manifesto(zipado: ZipFile, clube, utilizador, equipas: list[dict], escopo: str) -> None:
    manifesto = {
        "formato_backup": "basquetebol-editavel-v2",
        "criado_em_utc": datetime.now(timezone.utc).isoformat(),
        "escopo": escopo,
        "clube": {"id": clube.id, "nome_oficial": clube.nome_oficial, "nome_curto": clube.nome_curto},
        "exportado_por": {"id": utilizador.id, "username": utilizador.username, "perfil": _valor_serializavel(utilizador.perfil)},
        "equipas": equipas,
        "seguranca": "Hashes de palavra-passe, versões de sessão e tokens de recuperação não são exportados.",
    }
    zipado.writestr("MANIFESTO.json", json.dumps(manifesto, ensure_ascii=False, indent=2))
    zipado.writestr(
        "LEIA-ME.txt",
        "BACKUP EDITÁVEL DA PLATAFORMA DE BASQUETEBOL\n\n"
        "Os dados estão separados por tema. Cada pasta contém um Excel para consulta e edição "
        "e um JSON integral que preserva conteúdos extensos, incluindo desenhos táticos.\n"
        "Alterar estes ficheiros não altera automaticamente a plataforma. Este pacote não inclui "
        "palavras-passe, tokens de recuperação ou chaves de sessão.\n",
    )


def _historico_do_clube(
    db: Session,
    anuais: list[PlaneamentoClubeAnual],
    mensais: list[PlaneamentoClubeMensal],
    semanais: list[PlanoSemanalClube],
) -> list[HistoricoPlaneamentoClube]:
    """Filtra a tabela histórica antiga, que ainda não tem clube_id."""
    grupos = {
        "planeamento_anual": [item.id for item in anuais],
        "planeamento_mensal": [item.id for item in mensais],
        "plano_semanal": [item.id for item in semanais],
    }
    filtros = [
        and_(
            HistoricoPlaneamentoClube.entidade == entidade,
            HistoricoPlaneamentoClube.entidade_id.in_(ids),
        )
        for entidade, ids in grupos.items()
        if ids
    ]
    if not filtros:
        return []
    return db.query(HistoricoPlaneamentoClube).filter(or_(*filtros)).order_by(
        HistoricoPlaneamentoClube.criado_em
    ).all()


@router.get("/equipas/{equipa_id}/dados")
def exportar_dados_equipa(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    """Descarrega um ZIP editável da equipa, limitado pelas permissões atuais."""
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if equipa is None:
        raise HTTPException(status_code=404, detail="Equipa não encontrada.")

    clube = getattr(request.state, "clube_atual", None)
    if clube is None or equipa.clube_id != clube.id:
        raise HTTPException(status_code=403, detail="A equipa não pertence ao clube selecionado.")

    ficheiro = BytesIO()
    raiz = f"Equipa_{equipa.id}_{_nome_seguro(equipa.nome)}"
    with ZipFile(ficheiro, "w", ZIP_DEFLATED) as zipado:
        identidade = db.query(IdentidadeClube).filter(IdentidadeClube.clube_id == clube.id).first()
        _adicionar_tema(
            zipado,
            "00_Clube",
            "identificacao_do_clube",
            [("clube", [clube]), ("identidade_clube", [identidade] if identidade else [])],
        )
        _adicionar_logos(zipado, clube, identidade)
        contagens = _escrever_equipa(zipado, db, equipa, raiz)
        _escrever_manifesto(
            zipado, clube, utilizador,
            [{"id": equipa.id, "nome": equipa.nome, "pasta": raiz, "contagens": contagens}],
            "equipa",
        )

    registar_auditoria(
        db, utilizador, "exportou", "backup_equipa", equipa_id,
        f"Backup editável completo da equipa {equipa.nome}.", request,
    )
    db.commit()
    ficheiro.seek(0)
    return StreamingResponse(
        ficheiro,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="backup_equipa_{_nome_seguro(equipa.nome)}.zip"'},
    )


@router.get("/clube/dados")
def exportar_dados_clube(
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_coordenacao),
):
    """Descarrega o clube por temas, com uma pasta detalhada por equipa."""
    clube = getattr(request.state, "clube_atual", None)
    if clube is None:
        raise HTTPException(status_code=403, detail="Seleciona um clube antes de exportar dados.")

    identidade = db.query(IdentidadeClube).filter(IdentidadeClube.clube_id == clube.id).first()
    equipas = db.query(Equipa).filter(Equipa.clube_id == clube.id).order_by(Equipa.nome).all()
    utilizadores = db.query(Utilizador).filter(Utilizador.clube_id == clube.id).order_by(Utilizador.nome).all()
    treinadores = db.query(Treinador).filter(Treinador.clube_id == clube.id).order_by(Treinador.nome).all()
    treinadores_ids = [treinador.id for treinador in treinadores]
    equipa_ids = [equipa.id for equipa in equipas]

    anuais = db.query(PlaneamentoClubeAnual).filter(PlaneamentoClubeAnual.clube_id == clube.id).all()
    mensais = db.query(PlaneamentoClubeMensal).filter(PlaneamentoClubeMensal.clube_id == clube.id).all()
    semanais = db.query(PlanoSemanalClube).filter(PlanoSemanalClube.clube_id == clube.id).all()
    eventos = db.query(EventoPlaneamentoClube).filter(EventoPlaneamentoClube.clube_id == clube.id).all()
    eventos_ids = [evento.id for evento in eventos]

    temas_gerais = [
        ("00_Clube", "identificacao_do_clube", [
            ("clube", [clube]), ("identidade_clube", [identidade] if identidade else []), ("equipas", equipas),
        ]),
        ("01_Utilizadores", "utilizadores_e_equipa_tecnica", [
            ("utilizadores", utilizadores), ("treinadores", treinadores),
            ("treinador_equipa", _linhas_associacao(db, treinador_equipa, treinador_equipa.c.equipa_id.in_(equipa_ids)) if equipa_ids else []),
            ("indisponibilidades_treinador", db.query(IndisponibilidadeTreinador).filter(IndisponibilidadeTreinador.treinador_id.in_(treinadores_ids)).all() if treinadores_ids else []),
        ]),
        ("02_Planeamento_do_clube", "planeamento_do_clube", [
            ("planeamentos_clube_anuais", anuais), ("planeamentos_clube_mensais", mensais),
            ("planos_semanais_clube", semanais), ("eventos_planeamento_clube", eventos),
            ("evento_planeamento_equipas", _linhas_associacao(db, evento_planeamento_clube_equipa, evento_planeamento_clube_equipa.c.evento_id.in_(eventos_ids)) if eventos_ids else []),
            ("atividades", db.query(Atividade).filter(Atividade.clube_id == clube.id).all()),
        ]),
        ("03_Espacos_e_horarios", "espacos_horarios_e_atribuicoes", [
            ("espacos_treino", db.query(EspacoTreino).filter(EspacoTreino.clube_id == clube.id).all()),
            ("disponibilidades_espaco_treino", db.query(DisponibilidadeEspacoTreino).filter(DisponibilidadeEspacoTreino.clube_id == clube.id).all()),
            ("indisponibilidades_espaco_treino", db.query(IndisponibilidadeEspacoTreino).filter(IndisponibilidadeEspacoTreino.clube_id == clube.id).all()),
            ("atribuicoes_espaco_semanais", db.query(AtribuicaoEspacoSemanal).filter(AtribuicaoEspacoSemanal.clube_id == clube.id).all()),
            ("agenda_espaco_equipa", db.query(AgendaEspacoEquipa).filter(AgendaEspacoEquipa.clube_id == clube.id).all()),
        ]),
        ("04_Biblioteca", "biblioteca_de_exercicios", [
            ("biblioteca_exercicios", db.query(BibliotecoExercicio).filter(BibliotecoExercicio.clube_id == clube.id).all()),
        ]),
        ("05_Auditoria_e_notificacoes", "auditoria_e_notificacoes", [
            ("registos_auditoria", db.query(RegistoAuditoria).filter(RegistoAuditoria.clube_id == clube.id).all()),
            ("historico_planeamento_clube", _historico_do_clube(db, anuais, mensais, semanais)),
            ("notificacoes", db.query(Notificacao).filter(Notificacao.clube_id == clube.id).all()),
        ]),
    ]

    ficheiro = BytesIO()
    manifesto_equipas = []
    with ZipFile(ficheiro, "w", ZIP_DEFLATED) as zipado:
        for pasta, titulo, conjuntos in temas_gerais:
            _adicionar_tema(zipado, pasta, titulo, conjuntos)
        _adicionar_logos(zipado, clube, identidade)
        for equipa in equipas:
            raiz = f"06_Equipas/Equipa_{equipa.id}_{_nome_seguro(equipa.nome)}"
            contagens = _escrever_equipa(zipado, db, equipa, raiz)
            manifesto_equipas.append({"id": equipa.id, "nome": equipa.nome, "pasta": raiz, "contagens": contagens})
        _escrever_manifesto(zipado, clube, utilizador, manifesto_equipas, "clube")

    registar_auditoria(
        db, utilizador, "exportou", "backup_clube", clube.id,
        f"Backup editável completo do clube {clube.nome_curto}.", request,
    )
    db.commit()
    ficheiro.seek(0)
    return StreamingResponse(
        ficheiro,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="backup_clube_{_nome_seguro(clube.nome_curto)}.zip"'},
    )
