"""Backups editáveis e isolados por clube e equipa."""

import json
import re
import unicodedata
from datetime import date, datetime, timezone
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response, StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from pypdf import PdfReader, PdfWriter
from sqlalchemy import and_, or_, select
from sqlalchemy.inspection import inspect as sa_inspect
from sqlalchemy.orm import Session
from template_config import Jinja2Templates

from auth import verificar_acesso_equipa
from auth_deps import exigir_autenticacao, exigir_coordenacao, exigir_operacao_desportiva, verificar_ou_negar_equipa
from database import get_db
from flash import set_flash
from models.avaliacao import AvaliacaoJogador, ParametroAvaliacao
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
from models.relatorio_exportacao import PredefinicaoRelatorio
from models.scouting import ScoutingAdversario, ScoutingAdversarioJogo, ScoutingJogador, STAT_FIELDS
from models.treinador import Treinador, treinador_equipa
from models.treino import BibliotecoExercicio, BlocoTreino, ExercicioPlano, ImportacaoPlanoTreino, PlanoTreino
from models.utilizador import Utilizador
from paths import STATIC_DIR, TEMPLATES_DIR
from services.auditoria_service import registar_auditoria
from services.fotografia_jogador_service import caminho_fotografia
from services.identidade_clube_service import caminho_ficheiro_logo
from services.desenho_service import imagem_estatica_data_uri
from services.pdf_service import content_disposition_pdf, preparar_contexto_pdf, renderizar_pdf

router = APIRouter(prefix="/exportacoes", tags=["exportacoes"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

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


def _juntar_pdfs(documentos: list[tuple[str, bytes]]) -> bytes:
    escritor = PdfWriter()
    for _, conteudo in documentos:
        leitor = PdfReader(BytesIO(conteudo))
        for pagina in leitor.pages:
            escritor.add_page(pagina)
    destino = BytesIO()
    escritor.write(destino)
    return destino.getvalue()


def _arquivar_pdfs(documentos: list[tuple[str, bytes]]) -> bytes:
    destino = BytesIO()
    with ZipFile(destino, "w", ZIP_DEFLATED) as arquivo:
        for indice, (nome, conteudo) in enumerate(documentos, start=1):
            arquivo.writestr(f"{indice:02d}_{_nome_seguro(nome, 'documento')}.pdf", conteudo)
    return destino.getvalue()


def _gerar_pdf_planeamento_selecionado(
    tipo: str,
    item_id: int,
    equipa_id: int,
    request: Request,
    db: Session,
    utilizador,
) -> tuple[str, bytes]:
    # As rotas individuais continuam a ser a fonte única dos dados e do design de cada PDF.
    from routers.planeamento import exportar_pdf_macrociclo, exportar_pdf_mesociclo, exportar_pdf_microciclo
    from routers.treino import exportar_pdf_plano

    if tipo == "macro":
        item = db.query(Macrociclo).filter(Macrociclo.id == item_id, Macrociclo.equipa_id == equipa_id).first()
        if not item:
            raise HTTPException(status_code=400, detail="Macrociclo inválido para esta equipa.")
        resposta = exportar_pdf_macrociclo(item.id, request, db, utilizador)
        nome = f"Macrociclo {item.numero}"
    elif tipo == "meso":
        item = db.query(Mesociclo).join(Macrociclo).filter(
            Mesociclo.id == item_id,
            Macrociclo.equipa_id == equipa_id,
        ).first()
        if not item:
            raise HTTPException(status_code=400, detail="Mesociclo inválido para esta equipa.")
        resposta = exportar_pdf_mesociclo(item.id, request, db, utilizador)
        nome = f"Mesociclo {item.numero}"
    elif tipo == "micro":
        item = db.query(Microciclo).join(Mesociclo).join(Macrociclo).filter(
            Microciclo.id == item_id,
            Macrociclo.equipa_id == equipa_id,
        ).first()
        if not item:
            raise HTTPException(status_code=400, detail="Microciclo inválido para esta equipa.")
        resposta = exportar_pdf_microciclo(item.id, request, db, utilizador)
        nome = f"Microciclo {item.numero}"
    elif tipo == "treino":
        item = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
            SessaoTreino.id == item_id,
            Macrociclo.equipa_id == equipa_id,
            SessaoTreino.ativa.is_(True),
            SessaoTreino.e_jogo.is_(False),
        ).first()
        if not item:
            raise HTTPException(status_code=400, detail="Treino inválido para esta equipa.")
        resposta = exportar_pdf_plano(item.id, request, db, utilizador)
        prefixo = "Treino físico" if (item.tipo_treino or "normal") == "fisico" else "Treino"
        nome = f"{prefixo} {item.numero_treino}" if item.numero_treino is not None else prefixo
    else:
        raise HTTPException(status_code=400, detail="Tipo de documento inválido.")

    if not isinstance(resposta, Response) or resposta.media_type != "application/pdf":
        raise HTTPException(status_code=400, detail=f"Não foi possível gerar {nome}.")
    return nome, bytes(resposta.body)


@router.get("/equipas/{equipa_id}/planeamento", response_class=HTMLResponse)
def selecionar_exportacao_planeamento(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse("/equipas", status_code=303)

    macros = db.query(Macrociclo).filter(Macrociclo.equipa_id == equipa_id).order_by(
        Macrociclo.numero.asc(), Macrociclo.data_inicio.asc(), Macrociclo.id.asc(),
    ).all()
    mesos = db.query(Mesociclo).join(Macrociclo).filter(Macrociclo.equipa_id == equipa_id).order_by(
        Macrociclo.numero.asc(), Mesociclo.numero.asc(), Mesociclo.data_inicio.asc(), Mesociclo.id.asc(),
    ).all()
    micros = db.query(Microciclo).join(Mesociclo).join(Macrociclo).filter(Macrociclo.equipa_id == equipa_id).order_by(
        Microciclo.numero.asc(), Microciclo.data_inicio.asc(), Microciclo.id.asc(),
    ).all()
    treinos = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
        Macrociclo.equipa_id == equipa_id,
        SessaoTreino.ativa.is_(True),
        SessaoTreino.e_jogo.is_(False),
    ).order_by(
        SessaoTreino.tipo_treino.asc(), SessaoTreino.numero_treino.asc(),
        SessaoTreino.data.asc(), SessaoTreino.hora_inicio.asc(), SessaoTreino.id.asc(),
    ).all()
    return templates.TemplateResponse(request, "exportacoes/planeamento_selecao.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "macrociclos": macros,
        "mesociclos": mesos,
        "microciclos": micros,
        "treinos": treinos,
    })


@router.post("/equipas/{equipa_id}/planeamento")
def exportar_planeamento_selecionado(
    equipa_id: int,
    request: Request,
    itens: list[str] = Form([]),
    formato: str = Form("pdf"),
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    verificar_ou_negar_equipa(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse("/equipas", status_code=303)
    if not itens:
        set_flash(request, "Seleciona pelo menos um documento para exportar.", "error")
        return RedirectResponse(f"/exportacoes/equipas/{equipa_id}/planeamento", status_code=303)
    if len(itens) > 80:
        raise HTTPException(status_code=400, detail="Seleciona no máximo 80 documentos de cada vez.")
    if formato not in {"pdf", "zip"}:
        raise HTTPException(status_code=400, detail="Formato de exportação inválido.")

    documentos: list[tuple[str, bytes]] = []
    vistos: set[tuple[str, int]] = set()
    for valor in itens:
        try:
            tipo, id_texto = valor.split(":", 1)
            chave = (tipo, int(id_texto))
        except (AttributeError, TypeError, ValueError):
            raise HTTPException(status_code=400, detail="Seleção de documentos inválida.")
        if chave in vistos:
            continue
        vistos.add(chave)
        documentos.append(_gerar_pdf_planeamento_selecionado(
            chave[0], chave[1], equipa_id, request, db, utilizador,
        ))

    nome_base = f"Planeamento {equipa.nome}"
    if formato == "zip":
        return Response(
            _arquivar_pdfs(documentos),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{_nome_seguro(nome_base)}.zip"'},
        )
    return Response(
        _juntar_pdfs(documentos),
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition_pdf(nome_base)},
    )


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


def _adicionar_planos_importados(
    zipado: ZipFile,
    importacoes: list[ImportacaoPlanoTreino],
    prefixo: str,
) -> None:
    for importacao in importacoes:
        zipado.writestr(
            f"{prefixo}/Ficheiros/Planos_importados/{importacao.id}_{_nome_seguro(importacao.nome_original)}",
            importacao.ficheiro,
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


def _conteudo_equipa(
    db: Session,
    equipa: Equipa,
) -> tuple[list[tuple[str, str, list]], list[Jogador], list[ImportacaoPlanoTreino]]:
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
    importacoes = db.query(ImportacaoPlanoTreino).filter(
        ImportacaoPlanoTreino.plano_id.in_(planos_ids)
    ).all() if planos_ids else []
    importacoes_metadados = [
        _registo_para_dict(importacao, {"ficheiro"}) for importacao in importacoes
    ]

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
            ("importacoes_plano_treino", importacoes_metadados),
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
            ("parametros_avaliacao", db.query(ParametroAvaliacao).filter(ParametroAvaliacao.equipa_id == equipa_id).all()),
            ("avaliacoes_jogadores", db.query(AvaliacaoJogador).filter(AvaliacaoJogador.equipa_id == equipa_id).all()),
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
    return temas, jogadores, importacoes


def _escrever_equipa(zipado: ZipFile, db: Session, equipa: Equipa, raiz: str) -> dict:
    temas, jogadores, importacoes = _conteudo_equipa(db, equipa)
    contagens = {}
    for pasta, titulo, conjuntos in temas:
        _adicionar_tema(zipado, f"{raiz}/{pasta}", titulo, conjuntos)
        contagens[pasta] = sum(len(linhas) for _, linhas in conjuntos)
    _adicionar_fotografias(zipado, jogadores, f"{raiz}/01_Plantel")
    _adicionar_planos_importados(zipado, importacoes, f"{raiz}/03_Treinos")
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


# ---------------------------------------------------------------------------
# Relatorios desportivos configuraveis
# ---------------------------------------------------------------------------

FORMATOS_RELATORIO = {
    "completo": {
        "nome": "Completo",
        "descricao": "Dossier detalhado para preparar, arquivar e partilhar com a equipa tecnica.",
    },
    "facil": {
        "nome": "Leitura facil",
        "descricao": "Resumo visual, direto e confortavel para consultar no telemovel ou no balneario.",
    },
    "a3": {
        "nome": "Poster A3",
        "descricao": "Uma pagina de grande formato apenas com as mensagens essenciais e sem dados confidenciais.",
    },
}


def _secao(chave: str, nome: str, descricao: str, formatos=("completo", "facil")) -> dict:
    return {"chave": chave, "nome": nome, "descricao": descricao, "formatos": formatos}


RELATORIOS_CONFIG = {
    "roster": {
        "nome": "Relatorio de plantel",
        "entidades": "jogadores",
        "secoes": [
            _secao("fotografia", "Fotografia", "Identificacao visual dos atletas.", ("completo", "facil", "a3")),
            _secao("identificacao", "Identificacao", "Nome, numero, posicao e idade.", ("completo", "facil", "a3")),
            _secao("fisico", "Perfil fisico", "Altura, peso e mao dominante.", ("completo", "facil")),
            _secao("estado", "Estado desportivo", "Estado atual no roster adversario.", ("completo",)),
            _secao("notas", "Notas tecnicas", "Observacoes e equipa anterior.", ("completo", "facil")),
            _secao("estatisticas", "Estatisticas", "Medias da epoca e indicadores principais.", ("completo", "facil")),
        ],
    },
    "scouting-individual": {
        "nome": "Scouting individual",
        "entidades": "atletas do adversario",
        "secoes": [
            _secao("identificacao", "Identificacao", "Numero, posicao, idade e perfil fisico.", ("completo", "facil", "a3")),
            _secao("fotografia", "Fotografia", "Referencia visual do atleta.", ("completo", "facil", "a3")),
            _secao("pontos_fortes", "Pontos fortes", "Caracteristicas que exigem maior atencao.", ("completo", "facil", "a3")),
            _secao("pontos_fracos", "Pontos a explorar", "Limitacoes e oportunidades identificadas.", ("completo", "facil", "a3")),
            _secao("tendencias", "Tendencias", "Movimentos, decisoes e comportamentos recorrentes.", ("completo", "facil")),
            _secao("zonas", "Zonas de acao", "Locais preferenciais e observacoes por zona.", ("completo", "facil")),
            _secao("estatisticas", "Estatisticas", "Medias da epoca e indicadores principais.", ("completo", "facil")),
            _secao("observacoes", "Observacoes", "Resumo tecnico individual.", ("completo",)),
            _secao("recomendacoes", "Recomendacoes", "Orientacoes praticas para o matchup.", ("completo", "facil", "a3")),
        ],
    },
    "scouting-coletivo": {
        "nome": "Scouting coletivo",
        "secoes": [
            _secao("identidade", "Identidade", "Perfil global, ritmo e contexto do adversario.", ("completo", "facil", "a3")),
            _secao("estatisticas", "Estatisticas coletivas", "Medias e lideres estatisticos.", ("completo", "facil")),
            _secao("cinco_rotacao", "Cinco e rotacoes", "Cinco inicial previsto e principais rotacoes.", ("completo", "facil", "a3")),
            _secao("ataque", "Ataque", "Pontos fortes, fragilidades e conceitos ofensivos.", ("completo", "facil", "a3")),
            _secao("defesa", "Defesa", "Comportamentos e opcoes defensivas esperadas.", ("completo", "facil", "a3")),
            _secao("jogadores_chave", "Jogadores-chave", "Lideres e prioridades individuais.", ("completo", "facil", "a3")),
            _secao("prioridades", "Prioridades", "Plano pratico para atacar e defender.", ("completo", "facil", "a3")),
            _secao("diagramas", "Diagramas", "Conceitos e momentos associados ao Playbook.", ("completo",)),
        ],
    },
    "plano-jogo": {
        "nome": "Plano de jogo",
        "secoes": [
            _secao("dados_jogo", "Dados do jogo", "Data, hora, local, competicao e adversario.", ("completo", "facil", "a3")),
            _secao("convocatoria", "Convocatoria", "Atletas convocados e informacao de encontro.", ("completo", "facil")),
            _secao("cinco_previsto", "Cinco e rotacoes", "Cinco inicial da equipa e previsao do adversario.", ("completo", "facil", "a3")),
            _secao("plano_ofensivo", "Plano ofensivo", "Chaves e movimentos prioritarios.", ("completo", "facil", "a3")),
            _secao("plano_defensivo", "Plano defensivo", "Coberturas e respostas por acao.", ("completo", "facil", "a3")),
            _secao("situacoes_especiais", "Situacoes especiais", "Decisoes para momentos especificos.", ("completo", "facil")),
            _secao("scouting", "Sintese do scouting", "Informacao coletiva importada do adversario.", ("completo", "facil")),
            _secao("mensagem", "Mensagem final", "Rotações, prioridades e mensagem curta para a equipa.", ("completo", "facil", "a3")),
        ],
    },
}

STAT_LABELS = {
    "minutos": "MIN",
    "pontos": "PTS",
    "fg_c": "FG convertidos",
    "fg_t": "FG tentados",
    "dois_c": "2P convertidos",
    "dois_t": "2P tentados",
    "tres_c": "3P convertidos",
    "tres_t": "3P tentados",
    "ll_c": "LL convertidos",
    "ll_t": "LL tentados",
    "ress_of": "Ressaltos ofensivos",
    "ress_def": "Ressaltos defensivos",
    "ress_total": "Ressaltos",
    "assistencias": "Assistências",
    "faltas": "Faltas",
    "turnovers": "Turnovers",
    "roubos": "Roubos",
    "desarmes": "Desarmes",
    "mais_menos": "+/-",
    "eficiencia": "Eficiência",
}

PERFIS_CONTACTOS = {"superadministrador", "administrador", "coordenador", "secretaria"}


def _perfil(utilizador) -> str:
    return getattr(getattr(utilizador, "perfil", None), "value", str(getattr(utilizador, "perfil", "")))


def _secoes_padrao(tipo: str, formato: str) -> list[str]:
    return [s["chave"] for s in RELATORIOS_CONFIG[tipo]["secoes"] if formato in s["formatos"]]


def _configuracao_relatorio(tipo: str, dados, utilizador) -> tuple[str, str, list[str]]:
    formato = dados.get("formato", "completo")
    if formato not in FORMATOS_RELATORIO:
        formato = "completo"
    orientacao = dados.get("orientacao", "paisagem" if formato == "a3" else "retrato")
    if orientacao not in {"retrato", "paisagem"}:
        orientacao = "retrato"
    validas = {s["chave"] for s in RELATORIOS_CONFIG[tipo]["secoes"]}
    escolhidas = [s for s in dados.getlist("secoes") if s in validas]
    ordem = [s for s in dados.get("ordem", "").split(",") if s in escolhidas]
    secoes = ordem + [s for s in escolhidas if s not in ordem]
    if not secoes:
        secoes = _secoes_padrao(tipo, formato)
    if tipo in {"roster", "scouting-individual"} and "fotografia" not in secoes:
        secoes.insert(0, "fotografia")
    if formato == "a3" or _perfil(utilizador) not in PERFIS_CONTACTOS:
        secoes = [s for s in secoes if s != "contactos"]
    return formato, orientacao, secoes


def _fotografia_embebida(url: str | None) -> str | None:
    caminho = caminho_fotografia(url)
    if not caminho or not caminho.is_file():
        return None
    mime = "image/png" if caminho.suffix.lower() == ".png" else "image/jpeg"
    return imagem_estatica_data_uri(caminho, mime)


def _idade(data_nascimento) -> int | None:
    if not data_nascimento:
        return None
    hoje = date.today()
    return hoje.year - data_nascimento.year - ((hoje.month, hoje.day) < (data_nascimento.month, data_nascimento.day))


def _alvo_relatorio(tipo: str, alvo_id: int, db: Session, utilizador):
    clube_id = utilizador.clube_id
    if tipo in {"roster", "scouting-individual", "scouting-coletivo"}:
        adversario = db.query(ScoutingAdversario).filter(ScoutingAdversario.id == alvo_id, ScoutingAdversario.clube_id == clube_id).first()
        if not adversario:
            raise HTTPException(404, "Adversario nao encontrado.")
        equipas = [ligacao.jogo.equipa for ligacao in adversario.jogos if ligacao.jogo and verificar_acesso_equipa(utilizador, ligacao.jogo.equipa_id, db)]
        if not equipas:
            raise HTTPException(403, "Sem acesso a este adversario.")
        return adversario, equipas[0], adversario.nome
    if tipo == "plano-jogo":
        jogo = db.query(Jogo).filter(Jogo.id == alvo_id, Jogo.clube_id == clube_id).first()
        if not jogo:
            raise HTTPException(404, "Jogo nao encontrado.")
        verificar_ou_negar_equipa(utilizador, jogo.equipa_id, db)
        return jogo, jogo.equipa, f"{jogo.equipa.nome} vs {jogo.adversario}"
    raise HTTPException(404, "Tipo de relatorio desconhecido.")


def _itens_por_categoria(itens) -> dict[str, list]:
    resultado: dict[str, list] = {}
    for relacao in itens or []:
        categoria = getattr(getattr(relacao, "item", None), "categoria", "outros")
        resultado.setdefault(categoria, []).append(relacao)
    return resultado


def _contexto_relatorio(tipo: str, alvo, equipa: Equipa, dados, db: Session) -> dict:
    contexto = {"tipo_relatorio": tipo, "equipa": equipa, "alvo": alvo}
    ids = {int(v) for v in dados.getlist("entidades") if str(v).isdigit()}
    stat_fields = [campo for campo in dados.getlist("estatisticas") if campo in STAT_FIELDS]
    if tipo == "roster":
        atletas = [j for j in alvo.jogadores if j.estado != "arquivado" and (not ids or j.id in ids)]
        contexto.update(
            atletas=sorted(atletas, key=lambda j: j.nome.lower()),
            fotografias={j.id: _fotografia_embebida(j.fotografia) for j in atletas},
            stat_fields=stat_fields,
            stat_labels=STAT_LABELS,
        )
    elif tipo == "scouting-individual":
        atletas = [j for j in alvo.jogadores if not ids or j.id in ids]
        contexto.update(
            atletas=atletas,
            fotografias={j.id: _fotografia_embebida(j.fotografia) for j in atletas},
            itens_atletas={j.id: _itens_por_categoria(j.itens) for j in atletas},
            stat_fields=stat_fields,
            stat_labels=STAT_LABELS,
        )
    elif tipo == "scouting-coletivo":
        contexto.update(
            adversario=alvo,
            fotografias={j.id: _fotografia_embebida(j.fotografia) for j in alvo.jogadores},
            itens_coletivos=_itens_por_categoria(alvo.itens_coletivos),
            cinco_previsto=[r for r in alvo.rotacao_prevista if r.papel == "titular"],
            rotacoes_previstas=[r for r in alvo.rotacao_prevista if r.papel != "titular"],
            stat_fields=stat_fields,
            stat_labels=STAT_LABELS,
        )
    else:
        plano = alvo.plano
        titulares_ids = [getattr(plano, f"titular_{i}", None) for i in range(1, 6)] if plano else []
        titulares = db.query(Jogador).filter(Jogador.id.in_([i for i in titulares_ids if i])).all() if any(titulares_ids) else []
        titulares_map = {j.id: j for j in titulares}
        titulares_ordenados = [titulares_map[i] for i in titulares_ids if i in titulares_map]
        ligacao = db.query(ScoutingAdversarioJogo).filter(ScoutingAdversarioJogo.jogo_id == alvo.id).first()
        adversario = ligacao.adversario if ligacao else None
        contexto.update(
            jogo=alvo,
            plano=plano,
            convocados=alvo.convocados,
            titulares=titulares_ordenados,
            fotografias_equipa={
                j.id: _fotografia_embebida(j.fotografia)
                for j in {c.jogador for c in alvo.convocados} | set(titulares_ordenados)
            },
            adversario=adversario,
            fotografias_adversario={
                j.id: _fotografia_embebida(j.fotografia)
                for j in (adversario.jogadores if adversario else [])
            },
            cinco_adversario=[r for r in adversario.rotacao_prevista if r.papel == "titular"] if adversario else [],
            itens_coletivos=_itens_por_categoria(adversario.itens_coletivos) if adversario else {},
        )
    return contexto


def _predefinicoes_relatorio(db: Session, utilizador, tipo: str, equipa_id: int) -> list[PredefinicaoRelatorio]:
    return db.query(PredefinicaoRelatorio).filter(
        PredefinicaoRelatorio.clube_id == utilizador.clube_id,
        PredefinicaoRelatorio.tipo == tipo,
        or_(
            and_(PredefinicaoRelatorio.ambito == "pessoal", PredefinicaoRelatorio.utilizador_id == utilizador.id),
            and_(PredefinicaoRelatorio.ambito == "equipa", PredefinicaoRelatorio.equipa_id == equipa_id),
        ),
    ).order_by(PredefinicaoRelatorio.ambito, PredefinicaoRelatorio.nome).all()


def _contexto_configurador(tipo: str, alvo_id: int, db: Session, utilizador, predefinicao_id: int | None = None) -> dict:
    alvo, equipa, alvo_nome = _alvo_relatorio(tipo, alvo_id, db, utilizador)
    predefinicoes = _predefinicoes_relatorio(db, utilizador, tipo, equipa.id)
    predefinicao = next((p for p in predefinicoes if p.id == predefinicao_id), None)
    selecionadas = json.loads(predefinicao.secoes) if predefinicao else _secoes_padrao(tipo, "completo")
    entidades = []
    if tipo == "roster":
        entidades = [j for j in alvo.jogadores if j.estado != "arquivado"]
    elif tipo == "scouting-individual":
        entidades = alvo.jogadores
    return {
        "utilizador": utilizador,
        "tipo": tipo,
        "alvo_id": alvo_id,
        "alvo_nome": alvo_nome,
        "equipa": equipa,
        "config": RELATORIOS_CONFIG[tipo],
        "formatos": FORMATOS_RELATORIO,
        "entidades": entidades,
        "predefinicoes": predefinicoes,
        "predefinicao": predefinicao,
        "selecionadas": selecionadas,
        "padroes": {f: _secoes_padrao(tipo, f) for f in FORMATOS_RELATORIO},
        "estatisticas_disponiveis": [(campo, STAT_LABELS[campo]) for campo in STAT_FIELDS]
        if any(secao["chave"] == "estatisticas" for secao in RELATORIOS_CONFIG[tipo]["secoes"])
        else [],
        "pode_ver_contactos": _perfil(utilizador) in PERFIS_CONTACTOS,
    }


@router.get("/relatorios/{tipo}/{alvo_id}", response_class=HTMLResponse)
def configurar_relatorio(
    tipo: str,
    alvo_id: int,
    request: Request,
    predefinicao_id: int | None = None,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    if tipo not in RELATORIOS_CONFIG:
        raise HTTPException(404, "Tipo de relatorio desconhecido.")
    return templates.TemplateResponse(
        request,
        "exportacoes/relatorio_configurar.html",
        _contexto_configurador(tipo, alvo_id, db, utilizador, predefinicao_id),
    )


@router.get("/relatorios/{tipo}/{alvo_id}/fragmento", response_class=HTMLResponse)
def fragmento_configurar_relatorio(
    tipo: str,
    alvo_id: int,
    request: Request,
    predefinicao_id: int | None = None,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_operacao_desportiva),
):
    if tipo not in RELATORIOS_CONFIG:
        raise HTTPException(404, "Tipo de relatorio desconhecido.")
    return templates.TemplateResponse(
        request,
        "exportacoes/_relatorio_formulario.html",
        _contexto_configurador(tipo, alvo_id, db, utilizador, predefinicao_id),
    )


def _gerar_relatorio(tipo: str, alvo_id: int, request: Request, dados, db: Session, utilizador, previsualizar: bool):
    if tipo not in RELATORIOS_CONFIG:
        raise HTTPException(404, "Tipo de relatorio desconhecido.")
    alvo, equipa, alvo_nome = _alvo_relatorio(tipo, alvo_id, db, utilizador)
    formato, orientacao, secoes = _configuracao_relatorio(tipo, dados, utilizador)
    contexto = _contexto_relatorio(tipo, alvo, equipa, dados, db)
    contexto.update(
        formato=formato,
        orientacao=orientacao,
        secoes=secoes,
        secoes_set=set(secoes),
        titulo_relatorio=RELATORIOS_CONFIG[tipo]["nome"],
        alvo_nome=alvo_nome,
        nome_autor=utilizador.nome,
        pode_ver_contactos=_perfil(utilizador) in PERFIS_CONTACTOS and formato != "a3",
    )
    template = f"relatorios/{tipo.replace('-', '_')}_{formato}.html"
    nome = f"{RELATORIOS_CONFIG[tipo]['nome']} - {alvo_nome} - {date.today().isoformat()}"
    if previsualizar:
        html = templates.get_template(template).render(preparar_contexto_pdf(request, contexto))
        return HTMLResponse(html)
    pdf = renderizar_pdf(request, template, contexto)
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": content_disposition_pdf(nome)})


@router.post("/relatorios/{tipo}/{alvo_id}/previsualizar")
async def previsualizar_relatorio(tipo: str, alvo_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_operacao_desportiva)):
    return _gerar_relatorio(tipo, alvo_id, request, await request.form(), db, utilizador, True)


@router.post("/relatorios/{tipo}/{alvo_id}/pdf")
async def descarregar_relatorio(tipo: str, alvo_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_operacao_desportiva)):
    return _gerar_relatorio(tipo, alvo_id, request, await request.form(), db, utilizador, False)


@router.post("/relatorios/{tipo}/{alvo_id}/predefinicoes")
async def guardar_predefinicao_relatorio(tipo: str, alvo_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_operacao_desportiva)):
    if tipo not in RELATORIOS_CONFIG:
        raise HTTPException(404, "Tipo de relatorio desconhecido.")
    _, equipa, _ = _alvo_relatorio(tipo, alvo_id, db, utilizador)
    dados = await request.form()
    nome = str(dados.get("nome_predefinicao", "")).strip()
    ambito = str(dados.get("ambito", "pessoal"))
    if not nome or ambito not in {"pessoal", "equipa"}:
        raise HTTPException(400, "Indica um nome e um ambito validos.")
    formato, orientacao, secoes = _configuracao_relatorio(tipo, dados, utilizador)
    filtro = [
        PredefinicaoRelatorio.clube_id == utilizador.clube_id,
        PredefinicaoRelatorio.tipo == tipo,
        PredefinicaoRelatorio.ambito == ambito,
        PredefinicaoRelatorio.nome == nome,
    ]
    if ambito == "pessoal":
        filtro.append(PredefinicaoRelatorio.utilizador_id == utilizador.id)
    else:
        filtro.append(PredefinicaoRelatorio.equipa_id == equipa.id)
    registo = db.query(PredefinicaoRelatorio).filter(*filtro).first()
    if not registo:
        registo = PredefinicaoRelatorio(
            clube_id=utilizador.clube_id,
            utilizador_id=utilizador.id if ambito == "pessoal" else None,
            equipa_id=equipa.id if ambito == "equipa" else None,
            tipo=tipo,
            ambito=ambito,
            nome=nome,
            protegido=False,
        )
        db.add(registo)
    registo.formato = formato
    registo.orientacao = orientacao
    registo.secoes = json.dumps(secoes)
    db.commit()
    return RedirectResponse(f"/exportacoes/relatorios/{tipo}/{alvo_id}?predefinicao_id={registo.id}", status_code=303)
