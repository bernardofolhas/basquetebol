"""Scouting técnico por jogo: adversário, respostas da equipa e auto-scouting."""

from datetime import datetime
import unicodedata

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import verificar_acesso_equipa
from auth_deps import exigir_scouting, verificar_ou_negar_equipa
from clube_contexto import clube_atual_id
from database import get_db
from flash import set_flash
from models.jogador import Jogador
from models.jogo import Jogo, PlanoJogo
from models.playbook import PassoSetPlay, Playbook, SetPlay
from models.scouting import (
    STAT_FIELDS,
    RelatorioScouting,
    ScoutingAcao,
    ScoutingAdversario,
    ScoutingAdversarioItem,
    ScoutingAdversarioJogo,
    ScoutingConceitoOfensivo,
    ScoutingEstatisticaJogo,
    ScoutingEstatisticaColetivaJogo,
    ScoutingFichaIndividual,
    ScoutingItemBiblioteca,
    ScoutingJogador,
    ScoutingJogadorAdversario,
    ScoutingJogadorItem,
    ScoutingLiderEstatistico,
    ScoutingMediaEpoca,
    ScoutingMediaColetiva,
    ScoutingMomentoPlaybook,
    ScoutingOpcoesDefensivas,
    ScoutingResultadoColetivo,
    ScoutingRotacaoPrevista,
    ScoutingZonaAcao,
)
from paths import TEMPLATES_DIR
from services.pdf_service import content_disposition_pdf, renderizar_pdf
from services.fotografia_jogador_service import apagar_fotografia, guardar_fotografia
from services.desenho_service import decompor_desenho_editavel
from template_config import Jinja2Templates


router = APIRouter(prefix="/scouting")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

ESTADOS = {"rascunho", "publicado", "revisto", "arquivado"}
CONFIANCAS = {"baixa", "média", "alta"}
POSICOES = ("Base", "Extremo", "Poste")
ESTADOS_JOGADOR = ("ativo", "lesionado", "dúvida", "ausente")
CATEGORIAS_BIBLIOTECA = {
    "caracteristica": "Características",
    "movimento": "Movimentos preferenciais",
    "estrategia": "Estratégias defensivas",
    "estatistica_coletiva": "Características estatísticas",
    "ataque_forte": "Ataque · pontos fortes",
    "ataque_fraco": "Ataque · pontos fracos",
    "defesa_forte": "Defesa · pontos fortes",
    "defesa_fraco": "Defesa · pontos fracos",
}
TIPOS_LIDERANCA = ("Melhor marcador", "Melhor ressaltador", "Melhor assistente", "Melhor lançador de 3 pontos", "Jogador mais utilizado", "Jogador mais eficiente", "Melhor defensor")
OPCOES_DEFENSIVAS = (
    ("bloqueio_central", "Bloqueios diretos centrais"),
    ("bloqueio_lateral", "Bloqueios diretos laterais"),
    ("bloqueio_indireto", "Bloqueios indiretos"),
    ("handoff", "Handoff"), ("bola_interior", "Defesa da bola interior"),
    ("alteracoes", "Alterações defensivas"),
)
ZONAS_CAMPO = (
    ("canto_esquerdo", "Canto esquerdo"), ("ala_esquerda", "Ala esquerda"),
    ("topo", "Topo"), ("ala_direita", "Ala direita"), ("canto_direito", "Canto direito"),
    ("poste_baixo_esquerdo", "Poste baixo esquerdo"), ("zona_central", "Zona central"),
    ("poste_baixo_direito", "Poste baixo direito"), ("aro", "Junto ao aro"),
)


def _normalizar(valor: str | None) -> str:
    texto = unicodedata.normalize("NFKD", (valor or "").strip().lower())
    return " ".join("".join(c for c in texto if not unicodedata.combining(c)).split())


def _clube_do_utilizador(utilizador) -> int:
    return clube_atual_id() if utilizador.perfil.value == "superadministrador" else utilizador.clube_id


def _float(valor) -> float | None:
    try:
        return float(str(valor).replace(",", ".")) if str(valor or "").strip() else None
    except ValueError:
        return None


def _int(valor) -> int | None:
    try:
        return int(valor) if str(valor or "").strip() else None
    except ValueError:
        return None


def _jogos_acessiveis(db: Session, utilizador) -> list[Jogo]:
    clube_id = _clube_do_utilizador(utilizador)
    jogos = db.query(Jogo).filter(Jogo.clube_id == clube_id).order_by(Jogo.data.desc()).all()
    return [jogo for jogo in jogos if verificar_acesso_equipa(utilizador, jogo.equipa_id, db)]


def _sincronizar_adversarios(db: Session, utilizador) -> None:
    clube_id = _clube_do_utilizador(utilizador)
    alterado = False
    for jogo in _jogos_acessiveis(db, utilizador):
        nome_normalizado = _normalizar(jogo.adversario)
        adversario = db.query(ScoutingAdversario).filter(
            ScoutingAdversario.clube_id == clube_id,
            ScoutingAdversario.nome_normalizado == nome_normalizado,
        ).first()
        if not adversario:
            adversario = ScoutingAdversario(clube_id=clube_id, nome=jogo.adversario.strip(), nome_normalizado=nome_normalizado)
            db.add(adversario)
            db.flush()
            alterado = True
        ligacao = db.query(ScoutingAdversarioJogo).filter(ScoutingAdversarioJogo.jogo_id == jogo.id).first()
        if not ligacao:
            db.add(ScoutingAdversarioJogo(clube_id=clube_id, adversario_id=adversario.id, jogo_id=jogo.id))
            alterado = True
    if alterado:
        db.commit()


def _adversario_acessivel(db: Session, adversario_id: int, utilizador) -> ScoutingAdversario | None:
    adversario = db.query(ScoutingAdversario).filter(ScoutingAdversario.id == adversario_id).first()
    if not adversario or adversario.clube_id != _clube_do_utilizador(utilizador):
        return None
    if not any(verificar_acesso_equipa(utilizador, ligacao.jogo.equipa_id, db) for ligacao in adversario.jogos if ligacao.jogo):
        return None
    return adversario


def _jogador_acessivel(db: Session, jogador_id: int, utilizador) -> ScoutingJogador | None:
    jogador = db.query(ScoutingJogador).filter(ScoutingJogador.id == jogador_id).first()
    return jogador if jogador and _adversario_acessivel(db, jogador.adversario_id, utilizador) else None


def _contexto_departamento(request, utilizador, adversario=None, **extra):
    contexto = {
        "utilizador": utilizador, "adversario": adversario, "equipa": None,
        "posicoes": POSICOES, "estados_jogador": ESTADOS_JOGADOR,
        "categorias_biblioteca": CATEGORIAS_BIBLIOTECA, "zonas_campo": ZONAS_CAMPO,
        "tipos_lideranca": TIPOS_LIDERANCA, "opcoes_defensivas_lista": OPCOES_DEFENSIVAS,
    }
    contexto.update(extra)
    return contexto


def _guardar_contexto_equipa(request: Request, equipa) -> None:
    """Mantém a navegação da equipa ativa dentro do departamento de Scouting."""
    if equipa:
        request.session["equipa_contexto_id"] = equipa.id
        request.session["equipa_contexto_nome"] = equipa.nome


def _sincronizar_resultados_coletivos(db: Session, adversario: ScoutingAdversario) -> None:
    alterado = False
    for ligacao in adversario.jogos:
        jogo = ligacao.jogo
        if not jogo or jogo.pontos_nos is None or jogo.pontos_adversario is None:
            continue
        resultado = db.query(ScoutingResultadoColetivo).filter(
            ScoutingResultadoColetivo.adversario_id == adversario.id,
            ScoutingResultadoColetivo.jogo_id == jogo.id,
        ).first()
        if not resultado:
            resultado = ScoutingResultadoColetivo(
                clube_id=adversario.clube_id, adversario_id=adversario.id, jogo_id=jogo.id,
                data=jogo.data, oponente=jogo.equipa.nome, em_casa=not jogo.em_casa,
            )
            db.add(resultado)
        resultado.pontos_marcados = jogo.pontos_adversario
        resultado.pontos_sofridos = jogo.pontos_nos
        resultado.competicao = jogo.competicao
        alterado = True
    if alterado:
        db.commit()


def _media_calculada(adversario: ScoutingAdversario) -> dict[str, float | None]:
    registos = list(adversario.estatisticas_coletivas)
    if not registos:
        return {campo: None for campo in STAT_FIELDS}
    media = {}
    for campo in STAT_FIELDS:
        valores = [getattr(registo, campo) for registo in registos if getattr(registo, campo) is not None]
        media[campo] = round(sum(valores) / len(valores), 1) if valores else None
    return media


def _garantir_configuracao_coletiva(
    db: Session,
    adversario: ScoutingAdversario,
) -> tuple[ScoutingMediaColetiva, ScoutingOpcoesDefensivas]:
    """Obtém os registos auxiliares sem depender do estado da relação ORM."""
    adversario_id = adversario.id
    clube_id = adversario.clube_id
    media = db.query(ScoutingMediaColetiva).filter(
        ScoutingMediaColetiva.adversario_id == adversario_id
    ).first()
    opcoes = db.query(ScoutingOpcoesDefensivas).filter(
        ScoutingOpcoesDefensivas.adversario_id == adversario_id
    ).first()
    if media and opcoes:
        return media, opcoes

    if not media:
        media = ScoutingMediaColetiva(
            clube_id=clube_id,
            adversario_id=adversario_id,
        )
        db.add(media)
    if not opcoes:
        opcoes = ScoutingOpcoesDefensivas(
            clube_id=clube_id,
            adversario_id=adversario_id,
        )
        db.add(opcoes)
    try:
        db.commit()
    except IntegrityError:
        # Dois pedidos simultâneos podem tentar preparar a página pela primeira vez.
        db.rollback()
        media = db.query(ScoutingMediaColetiva).filter(
            ScoutingMediaColetiva.adversario_id == adversario_id
        ).one()
        opcoes = db.query(ScoutingOpcoesDefensivas).filter(
            ScoutingOpcoesDefensivas.adversario_id == adversario_id
        ).one()
    return media, opcoes


def _playbook_scouting(db: Session, adversario: ScoutingAdversario) -> Playbook | None:
    ligacao = next((item for item in adversario.jogos if item.jogo and item.jogo.equipa), None)
    if not ligacao:
        return None
    equipa = ligacao.jogo.equipa
    base = db.query(Playbook).filter(Playbook.equipa_id == equipa.id).order_by(Playbook.id).first()
    if not base:
        base = Playbook(clube_id=adversario.clube_id, equipa_id=equipa.id, nome=f"Playbook — {equipa.nome}")
        db.add(base)
        db.flush()
    nome = f"Scouting · {adversario.nome}"
    playbook = db.query(Playbook).filter(Playbook.equipa_id == equipa.id, Playbook.nome == nome).first()
    if not playbook:
        playbook = Playbook(clube_id=adversario.clube_id, equipa_id=equipa.id, nome=nome, descricao="Área técnica interna do scouting coletivo.")
        db.add(playbook)
        db.flush()
    return playbook


def _criar_setplay_scouting(db: Session, adversario: ScoutingAdversario, titulo: str, observacoes: str | None, categoria: str) -> SetPlay | None:
    playbook = _playbook_scouting(db, adversario)
    if not playbook:
        return None
    setplay = SetPlay(
        clube_id=adversario.clube_id, playbook_id=playbook.id, nome=titulo,
        categoria=categoria, descricao=observacoes, origem="scouting", ordem=len(playbook.setplays),
    )
    db.add(setplay)
    db.flush()
    db.add(PassoSetPlay(clube_id=adversario.clube_id, setplay_id=setplay.id, ordem=0, observacao=observacoes))
    return setplay


def _preparar_preview(registos) -> None:
    for registo in registos:
        primeiro = registo.setplay.passos[0] if registo.setplay and registo.setplay.passos else None
        registo.preview_imagem = decompor_desenho_editavel(primeiro.desenho)[0] if primeiro and primeiro.desenho else None


def _jogo_plano_adversario(adversario: ScoutingAdversario, db: Session, utilizador, jogo_id: int | None = None) -> Jogo | None:
    jogos = [
        ligacao.jogo for ligacao in adversario.jogos
        if ligacao.jogo and verificar_acesso_equipa(utilizador, ligacao.jogo.equipa_id, db)
    ]
    if jogo_id:
        selecionado = next((jogo for jogo in jogos if jogo.id == jogo_id), None)
        if selecionado:
            return selecionado
    hoje = datetime.now().date()
    futuros = sorted((jogo for jogo in jogos if jogo.data >= hoje), key=lambda jogo: (jogo.data, jogo.hora or ""))
    return futuros[0] if futuros else (max(jogos, key=lambda jogo: jogo.data) if jogos else None)


def _itens_coletivos_texto(adversario: ScoutingAdversario, categoria: str, titulo: str) -> str | None:
    linhas = []
    for associacao in adversario.itens_coletivos:
        if associacao.item and associacao.item.categoria == categoria:
            detalhe = f" — {associacao.observacao}" if associacao.observacao else ""
            linhas.append(f"• {associacao.item.nome}{detalhe}")
    return f"{titulo}\n" + "\n".join(linhas) if linhas else None


def _preencher_se_vazio(plano: PlanoJogo, campo: str, blocos: list[str | None]) -> bool:
    if getattr(plano, campo):
        return False
    conteudo = "\n\n".join(bloco for bloco in blocos if bloco)
    if not conteudo:
        return False
    setattr(plano, campo, conteudo)
    return True


def _jogo_e_relatorio(db: Session, jogo_id: int, utilizador):
    jogo = db.query(Jogo).filter(Jogo.id == jogo_id).first()
    if not jogo:
        return None, None
    verificar_ou_negar_equipa(utilizador, jogo.equipa_id, db)
    relatorio = db.query(RelatorioScouting).filter(RelatorioScouting.jogo_id == jogo.id).first()
    if not relatorio:
        relatorio = RelatorioScouting(jogo_id=jogo.id)
        db.add(relatorio)
        db.commit()
        db.refresh(relatorio)
    return jogo, relatorio


def _obter_relatorio(db: Session, relatorio_id: int, utilizador):
    relatorio = db.query(RelatorioScouting).filter(RelatorioScouting.id == relatorio_id).first()
    if not relatorio or not relatorio.jogo:
        return None
    verificar_ou_negar_equipa(utilizador, relatorio.jogo.equipa_id, db)
    return relatorio


def _limpo(valor: str | None) -> str | None:
    valor = (valor or "").strip()
    return valor or None


def _contexto_pdf(request: Request, relatorio: RelatorioScouting, utilizador) -> dict:
    return {
        "utilizador": utilizador,
        "relatorio": relatorio,
        "jogo": relatorio.jogo,
        "equipa": relatorio.jogo.equipa,
        "nome_treinador": utilizador.nome,
        "data_exportacao": datetime.now().date(),
    }


@router.get("", response_class=HTMLResponse)
def departamento_scouting(
    request: Request,
    equipa_id: int | None = None,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_scouting),
):
    if equipa_id and verificar_acesso_equipa(utilizador, equipa_id, db):
        from models.equipa import Equipa
        equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
        _guardar_contexto_equipa(request, equipa)
    _sincronizar_adversarios(db, utilizador)
    acessiveis = []
    for adversario in db.query(ScoutingAdversario).filter(
        ScoutingAdversario.clube_id == _clube_do_utilizador(utilizador)
    ).order_by(ScoutingAdversario.nome).all():
        jogos = [ligacao.jogo for ligacao in adversario.jogos if ligacao.jogo and verificar_acesso_equipa(utilizador, ligacao.jogo.equipa_id, db)]
        if jogos:
            adversario.jogos_acessiveis = sorted(jogos, key=lambda jogo: jogo.data, reverse=True)
            acessiveis.append(adversario)
    return templates.TemplateResponse(request, "scouting/index.html", _contexto_departamento(
        request, utilizador, adversarios=acessiveis, total_jogadores=sum(len(item.jogadores) for item in acessiveis)
    ))


@router.get("/adversarios/{adversario_id}")
def abrir_adversario(adversario_id: int):
    return RedirectResponse(url=f"/scouting/adversarios/{adversario_id}/resumo", status_code=303)


@router.get("/adversarios/{adversario_id}/{separador}", response_class=HTMLResponse)
def separador_adversario(adversario_id: int, separador: str, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    if separador not in {"resumo", "roster", "individual", "coletivo", "plano-jogo", "relatorios"}:
        return RedirectResponse(url=f"/scouting/adversarios/{adversario_id}/resumo", status_code=303)
    adversario = _adversario_acessivel(db, adversario_id, utilizador)
    if not adversario:
        return RedirectResponse(url="/scouting", status_code=303)
    jogos = sorted([
        ligacao.jogo for ligacao in adversario.jogos
        if ligacao.jogo and verificar_acesso_equipa(utilizador, ligacao.jogo.equipa_id, db)
    ], key=lambda jogo: jogo.data, reverse=True)
    if separador == "roster":
        grupos = {posicao: [j for j in adversario.jogadores if j.posicao_principal == posicao] for posicao in POSICOES}
        return templates.TemplateResponse(request, "scouting/roster.html", _contexto_departamento(
            request, utilizador, adversario, separador=separador, grupos=grupos, jogos=jogos
        ))
    if separador == "individual":
        return templates.TemplateResponse(request, "scouting/individual_lista.html", _contexto_departamento(
            request, utilizador, adversario, separador=separador, jogadores=adversario.jogadores, jogos=jogos
        ))
    if separador == "resumo":
        return templates.TemplateResponse(request, "scouting/resumo.html", _contexto_departamento(
            request, utilizador, adversario, separador=separador, jogos=jogos
        ))
    if separador == "plano-jogo":
        jogo_id = _int(request.query_params.get("jogo_id"))
        jogo = _jogo_plano_adversario(adversario, db, utilizador, jogo_id)
        jogadores = (
            db.query(Jogador).filter(Jogador.equipa_id == jogo.equipa_id).order_by(Jogador.numero_camisola, Jogador.nome).all()
            if jogo else []
        )
        return templates.TemplateResponse(request, "scouting/plano_jogo.html", _contexto_departamento(
            request, utilizador, adversario, separador=separador, jogos=jogos, jogo=jogo,
            plano=jogo.plano if jogo else None, jogadores=jogadores,
            cinco_previsto=[item for item in adversario.rotacao_prevista if item.papel == "titular"],
            rotacoes_previstas=[item for item in adversario.rotacao_prevista if item.papel == "rotacao"],
        ))
    if separador == "coletivo":
        _sincronizar_resultados_coletivos(db, adversario)
        media_coletiva, opcoes_defensivas = _garantir_configuracao_coletiva(db, adversario)
        biblioteca = db.query(ScoutingItemBiblioteca).filter(
            ScoutingItemBiblioteca.clube_id == adversario.clube_id,
            ScoutingItemBiblioteca.categoria.in_(("estatistica_coletiva", "ataque_forte", "ataque_fraco", "defesa_forte", "defesa_fraco")),
        ).order_by(ScoutingItemBiblioteca.nome).all()
        media_calculada = _media_calculada(adversario)
        media_exibida = (
            {campo: getattr(media_coletiva, campo) for campo in STAT_FIELDS}
            if media_coletiva.usar_manual
            else media_calculada
        )
        resultados = [item for item in adversario.resultados if item.data][:5]
        itens_coletivos = [item for item in adversario.itens_coletivos if item.item]
        lideres = [item for item in adversario.lideres if item.jogador]
        conceitos = [item for item in adversario.conceitos_ofensivos if item.setplay]
        momentos = [item for item in adversario.momentos_playbook if item.setplay]
        rotacoes = [item for item in adversario.rotacao_prevista if item.jogador]
        _preparar_preview(conceitos)
        _preparar_preview(momentos)
        return templates.TemplateResponse(request, "scouting/coletivo.html", _contexto_departamento(
            request, utilizador, adversario, separador=separador, jogos=jogos,
            resultados=resultados, biblioteca=biblioteca,
            media_calculada=media_calculada, media_exibida=media_exibida, stat_fields=STAT_FIELDS,
            media_coletiva=media_coletiva, opcoes_defensivas=opcoes_defensivas,
            itens_coletivos=itens_coletivos, lideres=lideres,
            conceitos=conceitos, momentos=momentos,
            cinco_previsto=[item for item in rotacoes if item.papel == "titular"],
            rotacoes_previstas=[item for item in rotacoes if item.papel == "rotacao"],
        ))
    if separador == "relatorios":
        equipas_relatorio = list({jogo.equipa.id: jogo.equipa for jogo in jogos}.values())
        return templates.TemplateResponse(request, "scouting/relatorios.html", _contexto_departamento(
            request,
            utilizador,
            adversario,
            separador=separador,
            jogos=jogos,
            equipas_relatorio=equipas_relatorio,
        ))
    return templates.TemplateResponse(request, "scouting/em_desenvolvimento.html", _contexto_departamento(
        request, utilizador, adversario, separador=separador, titulo="Relatórios"
    ))


@router.get("/jogos/{jogo_id}/plano-jogo")
def abrir_plano_jogo_no_scouting(jogo_id: int, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    jogo = db.query(Jogo).filter(Jogo.id == jogo_id).first()
    if not jogo:
        return RedirectResponse(url="/scouting", status_code=303)
    verificar_ou_negar_equipa(utilizador, jogo.equipa_id, db)
    _sincronizar_adversarios(db, utilizador)
    ligacao = db.query(ScoutingAdversarioJogo).filter(ScoutingAdversarioJogo.jogo_id == jogo.id).first()
    if not ligacao:
        return RedirectResponse(url="/scouting", status_code=303)
    return RedirectResponse(
        url=f"/scouting/adversarios/{ligacao.adversario_id}/plano-jogo?jogo_id={jogo.id}",
        status_code=303,
    )


def _voltar_coletivo(adversario_id: int, ancora: str = ""):
    return RedirectResponse(url=f"/scouting/adversarios/{adversario_id}/coletivo{ancora}", status_code=303)


@router.post("/adversarios/{adversario_id}/coletivo/rotacao-prevista")
async def guardar_rotacao_prevista(adversario_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    adversario = _adversario_acessivel(db, adversario_id, utilizador)
    if not adversario:
        return RedirectResponse(url="/scouting", status_code=303)
    dados = await request.form()
    titulares = []
    for indice in range(1, 6):
        jogador_id = _int(dados.get(f"titular_{indice}"))
        if jogador_id and jogador_id not in titulares:
            titulares.append(jogador_id)
    rotacoes = [_int(valor) for valor in dados.getlist("rotacoes")]
    rotacoes = [jogador_id for jogador_id in rotacoes if jogador_id and jogador_id not in titulares]
    ids_validos = {jogador.id for jogador in adversario.jogadores}
    titulares = [jogador_id for jogador_id in titulares if jogador_id in ids_validos][:5]
    rotacoes = [jogador_id for jogador_id in rotacoes if jogador_id in ids_validos]
    db.query(ScoutingRotacaoPrevista).filter(ScoutingRotacaoPrevista.adversario_id == adversario.id).delete(synchronize_session=False)
    for papel, jogadores_ids in (("titular", titulares), ("rotacao", rotacoes)):
        for ordem, jogador_id in enumerate(jogadores_ids):
            db.add(ScoutingRotacaoPrevista(
                clube_id=adversario.clube_id, adversario_id=adversario.id,
                jogador_id=jogador_id, papel=papel, ordem=ordem,
            ))
    db.commit()
    set_flash(request, "Cinco inicial e rotações previstas atualizados.")
    return _voltar_coletivo(adversario.id, "#rotacao-prevista")


@router.post("/adversarios/{adversario_id}/plano-jogo/{jogo_id}/importar")
def importar_scouting_para_plano(adversario_id: int, jogo_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    adversario = _adversario_acessivel(db, adversario_id, utilizador)
    jogo = _jogo_plano_adversario(adversario, db, utilizador, jogo_id) if adversario else None
    if not adversario or not jogo:
        return RedirectResponse(url="/scouting", status_code=303)
    plano = jogo.plano or PlanoJogo(clube_id=jogo.clube_id, jogo_id=jogo.id)
    db.add(plano)
    conceitos = [
        f"• {elemento.setplay.nome}" + (f" — {elemento.setplay.descricao}" if elemento.setplay.descricao else "")
        for elemento in adversario.conceitos_ofensivos if elemento.setplay
    ]
    opcoes = adversario.opcoes_defensivas
    alterados = 0
    alterados += _preencher_se_vazio(plano, "chaves_ataque", [
        _itens_coletivos_texto(adversario, "defesa_fraco", "Fragilidades a explorar"),
        _itens_coletivos_texto(adversario, "defesa_forte", "Pontos fortes a evitar"),
    ])
    alterados += _preencher_se_vazio(plano, "chaves_defesa", [
        _itens_coletivos_texto(adversario, "ataque_forte", "Prioridades defensivas"),
        _itens_coletivos_texto(adversario, "ataque_fraco", "Fragilidades ofensivas do adversário"),
        "Conceitos ofensivos identificados\n" + "\n".join(conceitos) if conceitos else None,
    ])
    alterados += _preencher_se_vazio(plano, "movimentos_ofensivos", [
        _itens_coletivos_texto(adversario, "defesa_fraco", "Soluções sugeridas pelo scouting"),
    ])
    if opcoes:
        mapa = {
            "bloqueio_direto_lateral": (opcoes.bloqueio_lateral, opcoes.bloqueio_lateral_notas, "Bloqueio direto lateral"),
            "bloqueio_direto_central": (opcoes.bloqueio_central, opcoes.bloqueio_central_notas, "Bloqueio direto central"),
            "handoff": (opcoes.handoff, opcoes.handoff_notas, "Handoff"),
            "indiretos_entrada": (opcoes.bloqueio_indireto, opcoes.bloqueio_indireto_notas, "Bloqueios indiretos"),
            "bola_dentro": (opcoes.bola_interior, opcoes.bola_interior_notas, "Bola interior"),
            "situacoes_especiais": (opcoes.alteracoes, opcoes.alteracoes_notas, "Alterações defensivas"),
        }
        for campo, (utilizada, notas, titulo) in mapa.items():
            bloco = f"Scouting adversário — {titulo}: utilizada" + (f"\n{notas}" if notas else "") if utilizada else None
            alterados += _preencher_se_vazio(plano, campo, [bloco])
    db.commit()
    mensagem = f"Scouting importado para {alterados} campo(s) vazio(s) do plano." if alterados else "O plano já tinha conteúdo nos campos disponíveis; nada foi substituído."
    set_flash(request, mensagem)
    return RedirectResponse(url=f"/scouting/adversarios/{adversario.id}/plano-jogo?jogo_id={jogo.id}", status_code=303)


@router.post("/adversarios/{adversario_id}/coletivo/resultados")
async def adicionar_resultado_coletivo(adversario_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    adversario = _adversario_acessivel(db, adversario_id, utilizador)
    if not adversario:
        return RedirectResponse(url="/scouting", status_code=303)
    dados = await request.form()
    try:
        data_resultado = datetime.strptime(str(dados.get("data")), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        set_flash(request, "Indica uma data válida para o resultado.", "error")
        return _voltar_coletivo(adversario.id, "#resultados")
    oponente = _limpo(dados.get("oponente"))
    if not oponente:
        set_flash(request, "Indica o adversário desse jogo.", "error")
        return _voltar_coletivo(adversario.id, "#resultados")
    db.add(ScoutingResultadoColetivo(
        clube_id=adversario.clube_id, adversario_id=adversario.id, data=data_resultado,
        oponente=oponente, em_casa=dados.get("local") != "fora",
        pontos_marcados=_int(dados.get("pontos_marcados")), pontos_sofridos=_int(dados.get("pontos_sofridos")),
        competicao=_limpo(dados.get("competicao")),
    ))
    db.commit()
    set_flash(request, "Resultado adicionado ao histórico.")
    return _voltar_coletivo(adversario.id, "#resultados")


@router.post("/coletivo/resultados/{resultado_id}/eliminar")
def eliminar_resultado_coletivo(resultado_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    resultado = db.query(ScoutingResultadoColetivo).filter(ScoutingResultadoColetivo.id == resultado_id).first()
    adversario = _adversario_acessivel(db, resultado.adversario_id, utilizador) if resultado else None
    if not adversario:
        return RedirectResponse(url="/scouting", status_code=303)
    db.delete(resultado)
    db.commit()
    return _voltar_coletivo(adversario.id, "#resultados")


@router.post("/adversarios/{adversario_id}/coletivo/estatisticas")
async def guardar_estatistica_coletiva(adversario_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    adversario = _adversario_acessivel(db, adversario_id, utilizador)
    if not adversario:
        return RedirectResponse(url="/scouting", status_code=303)
    dados = await request.form()
    resultado_id = _int(dados.get("resultado_id"))
    resultado = db.query(ScoutingResultadoColetivo).filter(
        ScoutingResultadoColetivo.id == resultado_id,
        ScoutingResultadoColetivo.adversario_id == adversario.id,
    ).first()
    if not resultado:
        set_flash(request, "Seleciona um resultado válido.", "error")
        return _voltar_coletivo(adversario.id, "#estatisticas-coletivas")
    registo = db.query(ScoutingEstatisticaColetivaJogo).filter(
        ScoutingEstatisticaColetivaJogo.adversario_id == adversario.id,
        ScoutingEstatisticaColetivaJogo.resultado_id == resultado.id,
    ).first()
    if not registo:
        registo = ScoutingEstatisticaColetivaJogo(
            clube_id=adversario.clube_id, adversario_id=adversario.id,
            resultado_id=resultado.id, data=resultado.data,
        )
        db.add(registo)
    for campo in STAT_FIELDS:
        setattr(registo, campo, _float(dados.get(campo)))
    db.commit()
    set_flash(request, "Estatísticas coletivas guardadas e média recalculada.")
    return _voltar_coletivo(adversario.id, "#estatisticas-coletivas")


@router.post("/adversarios/{adversario_id}/coletivo/media")
async def guardar_media_coletiva(adversario_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    adversario = _adversario_acessivel(db, adversario_id, utilizador)
    if not adversario:
        return RedirectResponse(url="/scouting", status_code=303)
    dados = await request.form()
    media = adversario.media_coletiva or ScoutingMediaColetiva(clube_id=adversario.clube_id, adversario_id=adversario.id)
    db.add(media)
    media.usar_manual = dados.get("usar_manual") == "true"
    for campo in STAT_FIELDS:
        setattr(media, campo, _float(dados.get(campo)))
    db.commit()
    set_flash(request, "Configuração da média coletiva atualizada.")
    return _voltar_coletivo(adversario.id, "#estatisticas-coletivas")


@router.post("/adversarios/{adversario_id}/coletivo/itens")
async def associar_item_coletivo(adversario_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    adversario = _adversario_acessivel(db, adversario_id, utilizador)
    if not adversario:
        return RedirectResponse(url="/scouting", status_code=303)
    dados = await request.form()
    categorias = {"estatistica_coletiva", "ataque_forte", "ataque_fraco", "defesa_forte", "defesa_fraco"}
    categoria, nome = dados.get("categoria"), _limpo(dados.get("nome_novo"))
    item_id = _int(dados.get("item_id"))
    item = db.query(ScoutingItemBiblioteca).filter(ScoutingItemBiblioteca.id == item_id, ScoutingItemBiblioteca.clube_id == adversario.clube_id).first() if item_id else None
    if nome and categoria in categorias:
        normalizado = _normalizar(nome)
        item = db.query(ScoutingItemBiblioteca).filter(
            ScoutingItemBiblioteca.clube_id == adversario.clube_id,
            ScoutingItemBiblioteca.categoria == categoria,
            ScoutingItemBiblioteca.nome_normalizado == normalizado,
        ).first()
        if not item:
            item = ScoutingItemBiblioteca(clube_id=adversario.clube_id, categoria=categoria, nome=nome, nome_normalizado=normalizado)
            db.add(item)
            db.flush()
    if not item or item.categoria not in categorias:
        set_flash(request, "Seleciona uma característica válida ou cria uma nova.", "error")
    else:
        associacao = db.query(ScoutingAdversarioItem).filter(
            ScoutingAdversarioItem.adversario_id == adversario.id,
            ScoutingAdversarioItem.item_id == item.id,
        ).first()
        if not associacao:
            associacao = ScoutingAdversarioItem(clube_id=adversario.clube_id, adversario_id=adversario.id, item_id=item.id)
            db.add(associacao)
        associacao.observacao = _limpo(dados.get("observacao"))
        associacao.valor = _limpo(dados.get("valor"))
        associacao.ranking = _limpo(dados.get("ranking"))
        associacao.validade = _limpo(dados.get("validade"))
        db.commit()
        set_flash(request, "Característica associada ao adversário.")
    return _voltar_coletivo(adversario.id, "#leitura-coletiva")


@router.post("/coletivo/itens/{associacao_id}/eliminar")
def remover_item_coletivo(associacao_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    associacao = db.query(ScoutingAdversarioItem).filter(ScoutingAdversarioItem.id == associacao_id).first()
    adversario = _adversario_acessivel(db, associacao.adversario_id, utilizador) if associacao else None
    if not adversario:
        return RedirectResponse(url="/scouting", status_code=303)
    db.delete(associacao)
    db.commit()
    return _voltar_coletivo(adversario.id, "#leitura-coletiva")


@router.post("/adversarios/{adversario_id}/coletivo/lideres")
async def adicionar_lider(adversario_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    adversario = _adversario_acessivel(db, adversario_id, utilizador)
    if not adversario:
        return RedirectResponse(url="/scouting", status_code=303)
    dados = await request.form()
    jogador_id, tipo = _int(dados.get("jogador_id")), _limpo(dados.get("tipo_novo")) or _limpo(dados.get("tipo"))
    jogador = db.query(ScoutingJogador).filter(ScoutingJogador.id == jogador_id, ScoutingJogador.adversario_id == adversario.id).first()
    if not jogador or not tipo:
        set_flash(request, "Seleciona um atleta e indica o tipo de liderança.", "error")
    else:
        db.add(ScoutingLiderEstatistico(clube_id=adversario.clube_id, adversario_id=adversario.id, jogador_id=jogador.id, tipo=tipo, observacao=_limpo(dados.get("observacao"))))
        db.commit()
        set_flash(request, "Líder estatístico adicionado.")
    return _voltar_coletivo(adversario.id, "#lideres")


@router.post("/coletivo/lideres/{lider_id}/eliminar")
def eliminar_lider(lider_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    lider = db.query(ScoutingLiderEstatistico).filter(ScoutingLiderEstatistico.id == lider_id).first()
    adversario = _adversario_acessivel(db, lider.adversario_id, utilizador) if lider else None
    if not adversario:
        return RedirectResponse(url="/scouting", status_code=303)
    db.delete(lider)
    db.commit()
    return _voltar_coletivo(adversario.id, "#lideres")


@router.post("/adversarios/{adversario_id}/coletivo/opcoes-defensivas")
async def guardar_opcoes_defensivas(adversario_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    adversario = _adversario_acessivel(db, adversario_id, utilizador)
    if not adversario:
        return RedirectResponse(url="/scouting", status_code=303)
    dados = await request.form()
    opcoes = adversario.opcoes_defensivas or ScoutingOpcoesDefensivas(clube_id=adversario.clube_id, adversario_id=adversario.id)
    db.add(opcoes)
    for campo, _ in OPCOES_DEFENSIVAS:
        setattr(opcoes, campo, dados.get(campo) == "true")
        setattr(opcoes, f"{campo}_notas", _limpo(dados.get(f"{campo}_notas")))
    db.commit()
    set_flash(request, "Opções defensivas atualizadas.")
    return _voltar_coletivo(adversario.id, "#opcoes-defensivas")


async def _criar_elemento_desenhado(adversario, request, db, modelo, categoria, ancora):
    dados = await request.form()
    titulo = _limpo(dados.get("titulo"))
    if not titulo:
        set_flash(request, "Indica um título.", "error")
        return _voltar_coletivo(adversario.id, ancora)
    setplay = _criar_setplay_scouting(db, adversario, titulo, _limpo(dados.get("observacoes")), categoria)
    if not setplay:
        set_flash(request, "O adversário precisa de estar associado a uma equipa e a um jogo.", "error")
        return _voltar_coletivo(adversario.id, ancora)
    lista = adversario.conceitos_ofensivos if modelo is ScoutingConceitoOfensivo else adversario.momentos_playbook
    db.add(modelo(clube_id=adversario.clube_id, adversario_id=adversario.id, setplay_id=setplay.id, ordem=len(lista)))
    db.commit()
    return RedirectResponse(url=f"/playbook/studio/setplays/{setplay.id}", status_code=303)


@router.post("/adversarios/{adversario_id}/coletivo/conceitos")
async def criar_conceito_ofensivo(adversario_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    adversario = _adversario_acessivel(db, adversario_id, utilizador)
    if not adversario:
        return RedirectResponse(url="/scouting", status_code=303)
    return await _criar_elemento_desenhado(adversario, request, db, ScoutingConceitoOfensivo, "Scouting · Conceito ofensivo", "#conceitos")


@router.post("/adversarios/{adversario_id}/coletivo/momentos")
async def criar_momento_playbook(adversario_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    adversario = _adversario_acessivel(db, adversario_id, utilizador)
    if not adversario:
        return RedirectResponse(url="/scouting", status_code=303)
    return await _criar_elemento_desenhado(adversario, request, db, ScoutingMomentoPlaybook, "Scouting · Playbook adversário", "#playbook-coletivo")


def _modelo_elemento(tipo: str):
    if tipo == "conceito":
        return ScoutingConceitoOfensivo, "#conceitos"
    if tipo == "momento":
        return ScoutingMomentoPlaybook, "#playbook-coletivo"
    return None, None


@router.post("/coletivo/{tipo}/{elemento_id}/eliminar")
def eliminar_elemento_desenhado(tipo: str, elemento_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    modelo, ancora = _modelo_elemento(tipo)
    if modelo is None:
        return RedirectResponse(url="/scouting", status_code=303)
    elemento = db.query(modelo).filter(modelo.id == elemento_id).first()
    adversario = _adversario_acessivel(db, elemento.adversario_id, utilizador) if elemento else None
    if not adversario:
        return RedirectResponse(url="/scouting", status_code=303)
    setplay = elemento.setplay
    db.delete(elemento)
    db.flush()
    db.delete(setplay)
    db.commit()
    set_flash(request, "Elemento eliminado sem afetar os restantes.")
    return _voltar_coletivo(adversario.id, ancora)


@router.post("/coletivo/{tipo}/{elemento_id}/mover/{direcao}")
def mover_elemento_desenhado(tipo: str, elemento_id: int, direcao: str, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    modelo, ancora = _modelo_elemento(tipo)
    if modelo is None:
        return RedirectResponse(url="/scouting", status_code=303)
    elemento = db.query(modelo).filter(modelo.id == elemento_id).first()
    adversario = _adversario_acessivel(db, elemento.adversario_id, utilizador) if elemento else None
    if not adversario or direcao not in {"cima", "baixo"}:
        return RedirectResponse(url="/scouting", status_code=303)
    lista = list(adversario.conceitos_ofensivos if tipo == "conceito" else adversario.momentos_playbook)
    indice = next((i for i, item in enumerate(lista) if item.id == elemento.id), -1)
    destino = indice - 1 if direcao == "cima" else indice + 1
    if indice >= 0 and 0 <= destino < len(lista):
        lista[indice].ordem, lista[destino].ordem = lista[destino].ordem, lista[indice].ordem
        db.commit()
    return _voltar_coletivo(adversario.id, ancora)


@router.post("/adversarios/{adversario_id}/jogadores")
async def criar_jogador(adversario_id: int, request: Request, fotografia: UploadFile | None = File(None), db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    adversario = _adversario_acessivel(db, adversario_id, utilizador)
    if not adversario:
        return RedirectResponse(url="/scouting", status_code=303)
    dados = await request.form()
    nome = _limpo(dados.get("nome"))
    posicao = dados.get("posicao_principal")
    if not nome or posicao not in POSICOES:
        set_flash(request, "Preenche o nome e uma posição principal válida.", "error")
        return RedirectResponse(url=f"/scouting/adversarios/{adversario.id}/roster", status_code=303)
    try:
        foto = await guardar_fotografia(fotografia)
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url=f"/scouting/adversarios/{adversario.id}/roster", status_code=303)
    jogador = ScoutingJogador(
        clube_id=adversario.clube_id, adversario_id=adversario.id, fotografia=foto, nome=nome,
        numero=_limpo(dados.get("numero")), idade=_int(dados.get("idade")), posicao_principal=posicao,
        posicao_alternativa=dados.get("posicao_alternativa") if dados.get("posicao_alternativa") in POSICOES else None,
        altura_cm=_float(dados.get("altura_cm")), peso_kg=_float(dados.get("peso_kg")),
        equipa_anterior=_limpo(dados.get("equipa_anterior")),
        estado=dados.get("estado") if dados.get("estado") in ESTADOS_JOGADOR else "ativo",
        mao_dominante=_limpo(dados.get("mao_dominante")), observacoes=_limpo(dados.get("observacoes")),
    )
    db.add(jogador)
    db.flush()
    db.add(ScoutingFichaIndividual(clube_id=adversario.clube_id, jogador_id=jogador.id))
    db.add(ScoutingMediaEpoca(clube_id=adversario.clube_id, jogador_id=jogador.id))
    db.commit()
    set_flash(request, "Atleta adicionado ao roster e ficha individual criada.")
    return RedirectResponse(url=f"/scouting/adversarios/{adversario.id}/roster", status_code=303)


@router.post("/roster/{jogador_id}/guardar")
async def editar_jogador(jogador_id: int, request: Request, fotografia: UploadFile | None = File(None), db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    jogador = _jogador_acessivel(db, jogador_id, utilizador)
    if not jogador:
        return RedirectResponse(url="/scouting", status_code=303)
    dados = await request.form()
    nome = _limpo(dados.get("nome"))
    posicao = dados.get("posicao_principal")
    if not nome or posicao not in POSICOES:
        set_flash(request, "Preenche o nome e uma posição principal válida.", "error")
        return RedirectResponse(url=f"/scouting/adversarios/{jogador.adversario_id}/roster", status_code=303)
    try:
        nova_foto = await guardar_fotografia(fotografia)
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url=f"/scouting/adversarios/{jogador.adversario_id}/roster", status_code=303)
    foto_antiga = jogador.fotografia
    if dados.get("remover_fotografia") == "true":
        jogador.fotografia = None
    if nova_foto:
        jogador.fotografia = nova_foto
    jogador.nome, jogador.numero, jogador.idade = nome, _limpo(dados.get("numero")), _int(dados.get("idade"))
    jogador.posicao_principal = posicao
    jogador.posicao_alternativa = dados.get("posicao_alternativa") if dados.get("posicao_alternativa") in POSICOES else None
    jogador.altura_cm, jogador.peso_kg = _float(dados.get("altura_cm")), _float(dados.get("peso_kg"))
    jogador.equipa_anterior = _limpo(dados.get("equipa_anterior"))
    jogador.estado = dados.get("estado") if dados.get("estado") in ESTADOS_JOGADOR else "ativo"
    jogador.mao_dominante, jogador.observacoes = _limpo(dados.get("mao_dominante")), _limpo(dados.get("observacoes"))
    db.commit()
    if foto_antiga and (nova_foto or dados.get("remover_fotografia") == "true"):
        apagar_fotografia(foto_antiga)
    set_flash(request, "Dados do atleta atualizados.")
    return RedirectResponse(url=f"/scouting/adversarios/{jogador.adversario_id}/roster", status_code=303)


@router.post("/roster/{jogador_id}/eliminar")
def eliminar_jogador_roster(jogador_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    jogador = _jogador_acessivel(db, jogador_id, utilizador)
    if not jogador:
        return RedirectResponse(url="/scouting", status_code=303)
    adversario_id, foto = jogador.adversario_id, jogador.fotografia
    db.delete(jogador)
    db.commit()
    apagar_fotografia(foto)
    set_flash(request, "Atleta removido do roster.")
    return RedirectResponse(url=f"/scouting/adversarios/{adversario_id}/roster", status_code=303)


@router.get("/jogadores/{jogador_id}", response_class=HTMLResponse)
def ficha_individual(jogador_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    jogador = _jogador_acessivel(db, jogador_id, utilizador)
    if not jogador:
        return RedirectResponse(url="/scouting", status_code=303)
    if not jogador.ficha:
        db.add(ScoutingFichaIndividual(clube_id=jogador.clube_id, jogador_id=jogador.id))
    if not jogador.media_epoca:
        db.add(ScoutingMediaEpoca(clube_id=jogador.clube_id, jogador_id=jogador.id))
    db.commit()
    biblioteca = db.query(ScoutingItemBiblioteca).filter(ScoutingItemBiblioteca.clube_id == jogador.clube_id).order_by(ScoutingItemBiblioteca.nome).all()
    jogos = sorted([ligacao.jogo for ligacao in jogador.adversario.jogos if ligacao.jogo], key=lambda jogo: jogo.data, reverse=True)
    return templates.TemplateResponse(request, "scouting/individual.html", _contexto_departamento(
        request, utilizador, jogador.adversario, separador="individual", jogador=jogador, biblioteca=biblioteca,
        jogos=jogos, stat_fields=STAT_FIELDS
    ))


@router.post("/jogadores/{jogador_id}/resumo")
async def guardar_resumo_individual(jogador_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    jogador = _jogador_acessivel(db, jogador_id, utilizador)
    if not jogador:
        return RedirectResponse(url="/scouting", status_code=303)
    dados = await request.form()
    jogador.ficha.resumo = _limpo(dados.get("resumo"))
    db.commit()
    set_flash(request, "Resumo individual guardado.")
    return RedirectResponse(url=f"/scouting/jogadores/{jogador.id}", status_code=303)


@router.post("/jogadores/{jogador_id}/media")
async def guardar_media(jogador_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    jogador = _jogador_acessivel(db, jogador_id, utilizador)
    if not jogador:
        return RedirectResponse(url="/scouting", status_code=303)
    dados = await request.form()
    media = jogador.media_epoca or ScoutingMediaEpoca(clube_id=jogador.clube_id, jogador_id=jogador.id)
    db.add(media)
    for campo in STAT_FIELDS:
        setattr(media, campo, _float(dados.get(campo)))
    db.commit()
    set_flash(request, "Média da época atualizada.")
    return RedirectResponse(url=f"/scouting/jogadores/{jogador.id}#estatisticas", status_code=303)


@router.post("/jogadores/{jogador_id}/estatisticas")
async def guardar_estatistica(jogador_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    jogador = _jogador_acessivel(db, jogador_id, utilizador)
    if not jogador:
        return RedirectResponse(url="/scouting", status_code=303)
    dados = await request.form()
    jogo_id = _int(dados.get("jogo_id"))
    jogo = next((ligacao.jogo for ligacao in jogador.adversario.jogos if ligacao.jogo_id == jogo_id), None)
    if not jogo:
        set_flash(request, "Seleciona um jogo associado a este adversário.", "error")
        return RedirectResponse(url=f"/scouting/jogadores/{jogador.id}#estatisticas", status_code=303)
    registo = db.query(ScoutingEstatisticaJogo).filter(ScoutingEstatisticaJogo.jogador_id == jogador.id, ScoutingEstatisticaJogo.jogo_id == jogo.id).first()
    if not registo:
        registo = ScoutingEstatisticaJogo(clube_id=jogador.clube_id, jogador_id=jogador.id, jogo_id=jogo.id, data=jogo.data, adversario=jogo.equipa.nome, competicao=jogo.competicao)
        db.add(registo)
    for campo in STAT_FIELDS:
        setattr(registo, campo, _float(dados.get(campo)))
    db.commit()
    set_flash(request, "Estatísticas do jogo guardadas.")
    return RedirectResponse(url=f"/scouting/jogadores/{jogador.id}#estatisticas", status_code=303)


@router.post("/estatisticas/{estatistica_id}/eliminar")
def eliminar_estatistica(estatistica_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    registo = db.query(ScoutingEstatisticaJogo).filter(ScoutingEstatisticaJogo.id == estatistica_id).first()
    jogador = _jogador_acessivel(db, registo.jogador_id, utilizador) if registo else None
    if not jogador:
        return RedirectResponse(url="/scouting", status_code=303)
    db.delete(registo)
    db.commit()
    set_flash(request, "Registo estatístico eliminado.")
    return RedirectResponse(url=f"/scouting/jogadores/{jogador.id}#estatisticas", status_code=303)


@router.post("/jogadores/{jogador_id}/itens")
async def associar_item(jogador_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    jogador = _jogador_acessivel(db, jogador_id, utilizador)
    if not jogador:
        return RedirectResponse(url="/scouting", status_code=303)
    dados = await request.form()
    categoria, nome = dados.get("categoria"), _limpo(dados.get("nome_novo"))
    item_id = _int(dados.get("item_id"))
    item = db.query(ScoutingItemBiblioteca).filter(ScoutingItemBiblioteca.id == item_id, ScoutingItemBiblioteca.clube_id == jogador.clube_id).first() if item_id else None
    if nome and categoria in CATEGORIAS_BIBLIOTECA:
        normalizado = _normalizar(nome)
        item = db.query(ScoutingItemBiblioteca).filter(ScoutingItemBiblioteca.clube_id == jogador.clube_id, ScoutingItemBiblioteca.categoria == categoria, ScoutingItemBiblioteca.nome_normalizado == normalizado).first()
        if not item:
            item = ScoutingItemBiblioteca(clube_id=jogador.clube_id, categoria=categoria, nome=nome, nome_normalizado=normalizado)
            db.add(item)
            db.flush()
    if not item:
        set_flash(request, "Seleciona uma opção da biblioteca ou cria uma nova.", "error")
    elif not db.query(ScoutingJogadorItem).filter(ScoutingJogadorItem.jogador_id == jogador.id, ScoutingJogadorItem.item_id == item.id).first():
        db.add(ScoutingJogadorItem(clube_id=jogador.clube_id, jogador_id=jogador.id, item_id=item.id, observacao=_limpo(dados.get("observacao"))))
        db.commit()
        set_flash(request, "Informação associada à ficha.")
    return RedirectResponse(url=f"/scouting/jogadores/{jogador.id}#leitura", status_code=303)


@router.post("/itens-associados/{associacao_id}/eliminar")
def remover_item(associacao_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    associacao = db.query(ScoutingJogadorItem).filter(ScoutingJogadorItem.id == associacao_id).first()
    jogador = _jogador_acessivel(db, associacao.jogador_id, utilizador) if associacao else None
    if not jogador:
        return RedirectResponse(url="/scouting", status_code=303)
    db.delete(associacao)
    db.commit()
    return RedirectResponse(url=f"/scouting/jogadores/{jogador.id}#leitura", status_code=303)


@router.post("/itens-associados/{associacao_id}/guardar")
async def guardar_observacao_item(associacao_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    associacao = db.query(ScoutingJogadorItem).filter(ScoutingJogadorItem.id == associacao_id).first()
    jogador = _jogador_acessivel(db, associacao.jogador_id, utilizador) if associacao else None
    if not jogador:
        return RedirectResponse(url="/scouting", status_code=303)
    dados = await request.form()
    associacao.observacao = _limpo(dados.get("observacao"))
    db.commit()
    set_flash(request, "Observação atualizada.")
    return RedirectResponse(url=f"/scouting/jogadores/{jogador.id}#leitura", status_code=303)


@router.post("/jogadores/{jogador_id}/zonas")
async def guardar_zonas(jogador_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    jogador = _jogador_acessivel(db, jogador_id, utilizador)
    if not jogador:
        return RedirectResponse(url="/scouting", status_code=303)
    dados = await request.form()
    validas = {zona for zona, _ in ZONAS_CAMPO}
    selecionadas = [zona for zona in dados.getlist("zonas") if zona in validas]
    db.query(ScoutingZonaAcao).filter(ScoutingZonaAcao.jogador_id == jogador.id).delete(synchronize_session=False)
    for zona in selecionadas:
        db.add(ScoutingZonaAcao(clube_id=jogador.clube_id, jogador_id=jogador.id, zona=zona, observacao=_limpo(dados.get(f"observacao_{zona}"))))
    db.commit()
    set_flash(request, "Zonas de ação atualizadas.")
    return RedirectResponse(url=f"/scouting/jogadores/{jogador.id}#zonas", status_code=303)


@router.get("/jogos/{jogo_id}", response_class=HTMLResponse)
def pagina_scouting(
    jogo_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_scouting),
):
    jogo = db.query(Jogo).filter(Jogo.id == jogo_id).first()
    if not jogo:
        return RedirectResponse(url="/equipas", status_code=303)
    verificar_ou_negar_equipa(utilizador, jogo.equipa_id, db)
    _guardar_contexto_equipa(request, jogo.equipa)
    _sincronizar_adversarios(db, utilizador)
    ligacao = db.query(ScoutingAdversarioJogo).filter(ScoutingAdversarioJogo.jogo_id == jogo.id).first()
    if ligacao:
        return RedirectResponse(url=f"/scouting/adversarios/{ligacao.adversario_id}/resumo", status_code=303)
    return RedirectResponse(url="/scouting", status_code=303)


@router.post("/{relatorio_id}/guardar")
async def guardar_scouting(
    relatorio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_scouting),
):
    relatorio = _obter_relatorio(db, relatorio_id, utilizador)
    if not relatorio:
        return RedirectResponse(url="/equipas", status_code=303)
    dados = await request.form()
    campos = (
        "jogos_observados", "fontes", "identidade", "pontos_fortes", "vulnerabilidades",
        "ataque", "defesa", "transicao", "situacoes_especiais", "prioridades_defensivas",
        "prioridades_ofensivas", "primeiros_minutos", "plano_contingencia", "auto_scouting",
        "melhorias_prioritarias",
    )
    for campo in campos:
        setattr(relatorio, campo, _limpo(dados.get(campo)))
    confianca = dados.get("confianca")
    relatorio.confianca = confianca if confianca in CONFIANCAS else None
    db.commit()
    set_flash(request, "Scouting guardado.")
    return RedirectResponse(url=f"/scouting/jogos/{relatorio.jogo_id}", status_code=303)


@router.post("/{relatorio_id}/publicar")
def publicar_scouting(
    relatorio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_scouting),
):
    relatorio = _obter_relatorio(db, relatorio_id, utilizador)
    if not relatorio:
        return RedirectResponse(url="/equipas", status_code=303)
    relatorio.estado = "publicado"
    relatorio.publicado_em = datetime.now()
    db.commit()
    set_flash(request, "Scouting publicado para a equipa técnica.")
    return RedirectResponse(url=f"/scouting/jogos/{relatorio.jogo_id}", status_code=303)


@router.post("/{relatorio_id}/jogadores/novo")
def adicionar_jogador_adversario(
    relatorio_id: int,
    request: Request,
    nome: str = Form(""),
    numero: str = Form(""),
    posicao: str = Form(""),
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_scouting),
):
    relatorio = _obter_relatorio(db, relatorio_id, utilizador)
    if not relatorio:
        return RedirectResponse(url="/equipas", status_code=303)
    if not _limpo(nome):
        set_flash(request, "Indica o nome do atleta adversário.", "error")
    else:
        db.add(ScoutingJogadorAdversario(
            relatorio_id=relatorio.id,
            ordem=len(relatorio.jogadores_adversarios),
            nome=_limpo(nome), numero=_limpo(numero), posicao=_limpo(posicao),
        ))
        db.commit()
        set_flash(request, "Atleta adversário adicionado.")
    return RedirectResponse(url=f"/scouting/jogos/{relatorio.jogo_id}", status_code=303)


@router.post("/jogadores/{jogador_id}/guardar")
async def guardar_jogador_adversario(
    jogador_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_scouting),
):
    jogador = db.query(ScoutingJogadorAdversario).filter(ScoutingJogadorAdversario.id == jogador_id).first()
    if not jogador or not _obter_relatorio(db, jogador.relatorio_id, utilizador):
        return RedirectResponse(url="/equipas", status_code=303)
    dados = await request.form()
    for campo in ("numero", "nome", "posicao", "papel", "mao_dominante", "como_pontua", "tendencias", "pontos_fortes", "limitacoes", "como_defender", "como_atacar"):
        setattr(jogador, campo, _limpo(dados.get(campo)))
    jogador.nome = jogador.nome or "Atleta adversário"
    jogador.prioridade = dados.get("prioridade") == "true"
    jogador.partilhavel = dados.get("partilhavel") == "true"
    db.commit()
    set_flash(request, "Perfil adversário atualizado.")
    return RedirectResponse(url=f"/scouting/jogos/{jogador.relatorio.jogo_id}", status_code=303)


@router.post("/jogadores/{jogador_id}/eliminar")
def eliminar_jogador_adversario(jogador_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    jogador = db.query(ScoutingJogadorAdversario).filter(ScoutingJogadorAdversario.id == jogador_id).first()
    if not jogador or not _obter_relatorio(db, jogador.relatorio_id, utilizador):
        return RedirectResponse(url="/equipas", status_code=303)
    jogo_id = jogador.relatorio.jogo_id
    db.delete(jogador)
    db.commit()
    set_flash(request, "Atleta adversário removido.")
    return RedirectResponse(url=f"/scouting/jogos/{jogo_id}", status_code=303)


@router.post("/{relatorio_id}/acoes/nova")
def adicionar_acao(relatorio_id: int, request: Request, nome: str = Form(""), categoria: str = Form("Ataque"), db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    relatorio = _obter_relatorio(db, relatorio_id, utilizador)
    if not relatorio:
        return RedirectResponse(url="/equipas", status_code=303)
    if not _limpo(nome):
        set_flash(request, "Indica o nome da ação adversária.", "error")
    else:
        db.add(ScoutingAcao(relatorio_id=relatorio.id, ordem=len(relatorio.acoes), nome=_limpo(nome), categoria=_limpo(categoria) or "Ataque"))
        db.commit()
        set_flash(request, "Ação adversária adicionada.")
    return RedirectResponse(url=f"/scouting/jogos/{relatorio.jogo_id}", status_code=303)


@router.post("/acoes/{acao_id}/guardar")
async def guardar_acao(acao_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    acao = db.query(ScoutingAcao).filter(ScoutingAcao.id == acao_id).first()
    if not acao or not _obter_relatorio(db, acao.relatorio_id, utilizador):
        return RedirectResponse(url="/equipas", status_code=303)
    dados = await request.form()
    for campo in ("categoria", "nome", "descricao", "resposta"):
        setattr(acao, campo, _limpo(dados.get(campo)))
    acao.nome = acao.nome or "Ação adversária"
    acao.categoria = acao.categoria or "Ataque"
    acao.prioridade = dados.get("prioridade") == "true"
    acao.partilhavel = dados.get("partilhavel") == "true"
    db.commit()
    set_flash(request, "Ação atualizada.")
    return RedirectResponse(url=f"/scouting/jogos/{acao.relatorio.jogo_id}", status_code=303)


@router.post("/acoes/{acao_id}/eliminar")
def eliminar_acao(acao_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    acao = db.query(ScoutingAcao).filter(ScoutingAcao.id == acao_id).first()
    if not acao or not _obter_relatorio(db, acao.relatorio_id, utilizador):
        return RedirectResponse(url="/equipas", status_code=303)
    jogo_id = acao.relatorio.jogo_id
    db.delete(acao)
    db.commit()
    set_flash(request, "Ação removida.")
    return RedirectResponse(url=f"/scouting/jogos/{jogo_id}", status_code=303)


@router.get("/{relatorio_id}/pdf/{formato}")
def exportar_pdf_scouting(relatorio_id: int, formato: str, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_scouting)):
    relatorio = _obter_relatorio(db, relatorio_id, utilizador)
    if not relatorio:
        return RedirectResponse(url="/equipas", status_code=303)
    modelos = {
        "tecnico": ("scouting/pdf_tecnico.html", "Relatório de scouting"),
        "resumo": ("scouting/pdf_resumo_tecnico.html", "Resumo técnico"),
        "atletas-resumo": ("scouting/pdf_atletas_resumo.html", "Resumo para atletas"),
        "atletas": ("scouting/pdf_atletas.html", "Guia para atletas"),
    }
    if formato not in modelos:
        return RedirectResponse(url=f"/scouting/jogos/{relatorio.jogo_id}", status_code=303)
    modelo, titulo = modelos[formato]
    pdf = renderizar_pdf(request, modelo, _contexto_pdf(request, relatorio, utilizador))
    nome = f"{titulo} - {relatorio.jogo.equipa.nome} - {relatorio.jogo.adversario}".replace("/", "-")
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": content_disposition_pdf(nome)})
