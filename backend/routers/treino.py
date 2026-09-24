# ─────────────────────────────────────────────────────────────
# ROUTER DE PLANO DE TREINO
# Gere a criação e edição de planos de treino detalhados
# Cada sessão de treino pode ter um plano com vários exercícios
# organizados em blocos (A, B, C, D)
# ─────────────────────────────────────────────────────────────

from datetime import date, datetime
import json
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Request, UploadFile, Depends
from template_config import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from sqlalchemy.orm import Session

from auth import verificar_acesso_equipa
from auth_deps import AcessoNegado, exigir_autenticacao
from database import get_db
from flash import set_flash
from horarios import hora_eh_anterior, hora_valida, normalizar_hora
from models.equipa import Equipa
from models.assiduidade import ConvocacaoAssiduidade, RegistoAssiduidade
from models.jogador import Jogador, RegistoAntropometrico
from models.planeamento import Macrociclo, Mesociclo, Microciclo, SessaoTreino
from models.planeamento_clube import EventoPlaneamentoClube
from models.treino import (
    BibliotecoExercicio,
    BlocoTreino,
    ExercicioPlano,
    ImportacaoPlanoTreino,
    PlanoTreino,
)
from paths import STATIC_DIR, TEMPLATES_DIR
from services.desenho_service import (
    compor_desenho_sobre_campo,
    decompor_desenho_editavel,
    empacotar_desenho_editavel,
    imagem_estatica_data_uri,
)
from services.conteudos_sessao_service import construir_sugestoes_plano_treino
from services.horarios_exercicios import recalcular_horas_exercicios
from services.equipas_treino_service import (
    altura_jogador,
    gerar_equipas_equilibradas,
    jogador_e_interior,
    posicao_agrupamento,
    posicoes_jogador,
)
from services.assiduidade_service import calcular_pse_real
from services.mapa_conteudos_service import obter_sugestoes_conteudos_microciclo
from services.sincronizacao_ui import enriquecer_sessao_para_ui
from services.auditoria_service import registar_auditoria
from services.importacao_plano_treino_service import (
    CAMPOS_CATEGORIA,
    CATEGORIAS_EXERCICIO,
    ErroImportacaoPlano,
    MAX_FICHEIRO_BYTES,
    extrair_texto,
    interpretar_texto,
    normalizar_categoria,
    sincronizar_minutos_categorias,
    validar_ficheiro,
)
from services.numeracao_planeamento_service import renumerar_treinos_equipa
from services.pdf_service import content_disposition_pdf, renderizar_pdf
from services.planeamento_semanal_administrativo_service import obter_previsao_equipa, validar_local_sessao
from services.remocao_sessoes_service import eliminar_sessoes_treino
from services.sessao_workflow import (
    ESTADOS_SESSAO,
    normalizar_estado_sessao,
    opcoes_transicao_sessao,
    transicao_sessao_valida,
)
from services.escaloes_service import escalao_imediatamente_inferior_da_equipa

router = APIRouter(prefix="/treino")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

IMAGENS_CAMPO = {
    "meio": "campo_meio.png?v=20260908-madeira-1",
    "completo": "campo_completo.png?v=20260908-madeira-1",
}


def _configuracao_campo(numero: int) -> tuple[str, str, str]:
    tipo = "meio" if numero % 2 else "completo"
    indice_tipo = (numero + 1) // 2 if tipo == "meio" else numero // 2
    nome_tipo = "Campo meio" if tipo == "meio" else "Campo completo"
    label = nome_tipo if indice_tipo == 1 else f"{nome_tipo} {indice_tipo}"
    return tipo, label, IMAGENS_CAMPO[tipo]


def _carregar_json(valor: str | None, predefinido):
    try:
        dados = json.loads(valor) if valor else predefinido
    except (TypeError, ValueError, json.JSONDecodeError):
        return predefinido
    return dados


def _atletas_disponiveis_plano(db: Session, equipa: Equipa, sessao_id: int) -> list[Jogador]:
    plantel = db.query(Jogador).filter(
        Jogador.equipa_id == equipa.id,
        Jogador.clube_id == equipa.clube_id,
        Jogador.ativo.is_(True),
    ).order_by(Jogador.numero_camisola.asc().nullslast(), Jogador.nome).all()
    convocados = (
        db.query(Jogador)
        .join(ConvocacaoAssiduidade, ConvocacaoAssiduidade.jogador_id == Jogador.id)
        .filter(
            ConvocacaoAssiduidade.sessao_id == sessao_id,
            ConvocacaoAssiduidade.clube_id == equipa.clube_id,
            Jogador.clube_id == equipa.clube_id,
            Jogador.ativo.is_(True),
        )
        .order_by(Jogador.numero_camisola.asc().nullslast(), Jogador.nome)
        .all()
    )
    ids_plantel = {jogador.id for jogador in plantel}
    return plantel + [jogador for jogador in convocados if jogador.id not in ids_plantel]


def _atletas_escalhao_inferior_convocaveis(db: Session, equipa: Equipa, sessao_id: int) -> list[Jogador]:
    """Atletas do escalão imediatamente inferior, do mesmo género."""
    escalao_origem = escalao_imediatamente_inferior_da_equipa(equipa)
    if not escalao_origem:
        return []
    convocados_ids = db.query(ConvocacaoAssiduidade.jogador_id).filter(
        ConvocacaoAssiduidade.sessao_id == sessao_id,
        ConvocacaoAssiduidade.clube_id == equipa.clube_id,
    )
    return (
        db.query(Jogador)
        .join(Equipa, Jogador.equipa_id == Equipa.id)
        .filter(
            Jogador.clube_id == equipa.clube_id,
            Jogador.ativo.is_(True),
            Jogador.equipa_id != equipa.id,
            Equipa.escalao == escalao_origem,
            Equipa.genero == equipa.genero,
            ~Jogador.id.in_(convocados_ids),
        )
        .order_by(Jogador.numero_camisola.asc().nullslast(), Jogador.nome)
        .all()
    )


def _dados_atletas_plano(db: Session, equipa: Equipa, sessao_id: int) -> list[dict]:
    jogadores = _atletas_disponiveis_plano(db, equipa, sessao_id)
    ids = [jogador.id for jogador in jogadores]
    alturas = {}
    if ids:
        registos = db.query(RegistoAntropometrico).filter(
            RegistoAntropometrico.jogador_id.in_(ids),
        ).order_by(RegistoAntropometrico.data.desc(), RegistoAntropometrico.id.desc()).all()
        for registo in registos:
            if registo.jogador_id in alturas or registo.altura is None:
                continue
            try:
                alturas[registo.jogador_id] = float(registo.altura)
            except (TypeError, ValueError):
                continue
    return [
        {
            "id": jogador.id,
            "nome": jogador.nome,
            "numero": jogador.numero_camisola,
            "fotografia": jogador.fotografia,
            "posicao": jogador.posicao,
            "posicao_secundaria": jogador.posicao_secundaria,
            "equipa": jogador.equipa.nome if jogador.equipa else "Sem equipa",
            "convocado": jogador.equipa_id != equipa.id,
            "altura": alturas.get(jogador.id),
            "interior": jogador_e_interior(jogador.posicao),
        }
        for jogador in jogadores
    ]


def _ids_atletas_previstos(plano: PlanoTreino, atletas: list[dict]) -> list[int]:
    disponiveis = {int(atleta["id"]) for atleta in atletas}
    if plano.atletas_previstos is None:
        return [int(atleta["id"]) for atleta in atletas]
    dados = _carregar_json(plano.atletas_previstos, [])
    if not isinstance(dados, list):
        return []
    return [int(valor) for valor in dados if isinstance(valor, int) and not isinstance(valor, bool) and valor in disponiveis]


def _estado_equipas_guardado(
    plano: PlanoTreino,
    atletas_previstos_ids: list[int],
    atletas: list[dict] | None = None,
) -> dict | None:
    estado = _carregar_json(plano.equipas_aleatorias, None)
    if not isinstance(estado, dict):
        return None
    permitidos = set(atletas_previstos_ids)
    grupos_origem = estado.get("grupos")
    if not isinstance(grupos_origem, list):
        grupos_origem = [estado] if isinstance(estado.get("equipas"), list) else []
    grupos = []
    ids_usados = set()
    for indice_grupo, grupo in enumerate(grupos_origem, start=1):
        if not isinstance(grupo, dict) or not isinstance(grupo.get("equipas"), list):
            continue
        usados = set()
        equipas = []
        for indice_equipa, equipa in enumerate(grupo["equipas"], start=1):
            if not isinstance(equipa, dict) or not isinstance(equipa.get("slots"), list):
                continue
            slots = []
            for valor in equipa["slots"]:
                if valor is None:
                    slots.append(None)
                elif isinstance(valor, int) and not isinstance(valor, bool) and valor in permitidos and valor not in usados:
                    slots.append(valor)
                    usados.add(valor)
            equipas.append({"nome": f"Equipa {indice_equipa}", "slots": slots})
        if not equipas or usados != permitidos:
            continue
        grupo_id = grupo.get("id")
        if not isinstance(grupo_id, int) or isinstance(grupo_id, bool) or grupo_id < 1 or grupo_id in ids_usados:
            grupo_id = indice_grupo
            while grupo_id in ids_usados:
                grupo_id += 1
        ids_usados.add(grupo_id)
        tamanho = grupo.get("tamanho", 3)
        if tamanho not in {2, 3, 4, 5}:
            tamanho = 3
        grupos.append({
            "id": grupo_id,
            "nome": f"Agrupamento {len(grupos) + 1}",
            "tamanho": tamanho,
            "postes_por_equipa": grupo.get("postes_por_equipa", 1),
            "grandes_ids": [valor for valor in grupo.get("grandes_ids", []) if valor in permitidos],
            "posicoes_ids": {
                str(jogador_id): papel
                for chave, papel in (grupo.get("posicoes_ids") or {}).items()
                if isinstance(chave, str) and chave.isdigit()
                for jogador_id in [int(chave)]
                if jogador_id in permitidos and papel in {"Base", "Extremo", "Poste"}
            } if isinstance(grupo.get("posicoes_ids"), dict) else {},
            "equipas": equipas,
        })
    if not grupos:
        return None
    if atletas is not None:
        por_id = {int(atleta["id"]): atleta for atleta in atletas}
        for grupo in grupos:
            papeis = grupo["posicoes_ids"]
            for jogador_id in permitidos:
                atleta = por_id.get(jogador_id)
                if not atleta:
                    continue
                principal, secundaria = posicoes_jogador(atleta)
                papel = papeis.get(str(jogador_id))
                if principal or secundaria:
                    if papel not in {principal, secundaria}:
                        papeis[str(jogador_id)] = principal or secundaria
                elif altura_jogador(atleta) is None:
                    papeis.pop(str(jogador_id), None)
            grupo["grandes_ids"] = [
                jogador_id for jogador_id in grupo["grandes_ids"]
                if jogador_id not in por_id
                or (
                    papeis.get(str(jogador_id)) == "Poste"
                    if any(posicoes_jogador(por_id[jogador_id]))
                    else altura_jogador(por_id[jogador_id]) is not None
                )
            ]
    return {"grupos": grupos}


def _equipas_para_impressao(db: Session, equipa: Equipa, plano: PlanoTreino | None) -> list[dict]:
    """Resolve os atletas das equipas guardadas sem alterar a organização do treino."""
    if not plano:
        return []
    atletas = _dados_atletas_plano(db, equipa, plano.sessao_id)
    previstos_ids = _ids_atletas_previstos(plano, atletas)
    estado = _estado_equipas_guardado(plano, previstos_ids, atletas)
    if not estado:
        return []
    por_id = {int(atleta["id"]): atleta for atleta in atletas}
    resultado = []
    for indice_grupo, grupo in enumerate(estado["grupos"], start=1):
        grandes = set(grupo.get("grandes_ids", []))
        posicoes = grupo.get("posicoes_ids", {})
        equipas = []
        for indice_equipa, equipa_guardada in enumerate(grupo["equipas"], start=1):
            slots = []
            for jogador_id in equipa_guardada["slots"]:
                atleta = por_id.get(jogador_id) if jogador_id is not None else None
                papel = posicoes.get(str(jogador_id)) if atleta else None
                if atleta and not papel:
                    papel = "Poste" if jogador_id in grandes else posicao_agrupamento(atleta["posicao"])
                slots.append({"atleta": atleta, "posicao": papel})
            equipas.append({"nome": equipa_guardada.get("nome") or f"Equipa {indice_equipa}", "slots": slots})
        resultado.append({
            "nome": grupo.get("nome") or f"Agrupamento {indice_grupo}",
            "tamanho": grupo.get("tamanho", 3),
            "equipas": equipas,
        })
    return resultado


def _proximo_numero_campo(tipo: str, slots: list[int]) -> int:
    numero = 1 if tipo == "meio" else 2
    while numero in slots:
        numero += 2
    return numero


def _mapa_desenhos(exercicio: ExercicioPlano) -> dict[str, str]:
    try:
        dados = json.loads(getattr(exercicio, "desenhos_campos", None) or "{}")
    except (TypeError, ValueError):
        return {}
    return dados if isinstance(dados, dict) else {}


def _obter_desenho_campo(exercicio: ExercicioPlano, numero: int) -> str | None:
    desenho = _mapa_desenhos(exercicio).get(str(numero))
    if desenho is None and numero <= 4:
        desenho = getattr(exercicio, f"desenho_{numero}", None)
    return desenho


def _definir_desenho_campo(exercicio: ExercicioPlano, numero: int, desenho: str | None) -> None:
    desenhos = _mapa_desenhos(exercicio)
    if numero <= 4:
        setattr(exercicio, f"desenho_{numero}", desenho)
        desenhos.pop(str(numero), None)
    elif desenho is None:
        desenhos.pop(str(numero), None)
    else:
        desenhos[str(numero)] = desenho
    exercicio.desenhos_campos = json.dumps(desenhos, ensure_ascii=False, separators=(",", ":"))


def _slots_ativos(exercicio: ExercicioPlano) -> list[int]:
    valor = exercicio.campos_ativos
    if valor is None:
        adicionais = [int(numero) for numero in _mapa_desenhos(exercicio) if numero.isdigit() and int(numero) > 2]
        return [1, 2] + [numero for numero in (3, 4) if getattr(exercicio, f"desenho_{numero}", None)] + sorted(numero for numero in adicionais if numero > 4)
    slots = []
    for item in valor.split(","):
        if item.isdigit() and int(item) > 0 and int(item) not in slots:
            slots.append(int(item))
    return slots


def _definir_slots_ativos(exercicio: ExercicioPlano, slots: list[int]) -> None:
    normalizados = []
    for numero in slots:
        if numero > 0 and numero not in normalizados:
            normalizados.append(numero)
    exercicio.campos_ativos = ",".join(str(numero) for numero in normalizados)


def _campos_exercicio(exercicio: ExercicioPlano) -> list[dict]:
    campos = []
    for numero in _slots_ativos(exercicio):
        tipo, label, imagem = _configuracao_campo(numero)
        desenho, estado_desenho = decompor_desenho_editavel(_obter_desenho_campo(exercicio, numero))
        campos.append({
            "numero": numero,
            "tipo": tipo,
            "label": label,
            "imagem": imagem,
            "desenho": desenho,
            "estado_desenho": estado_desenho,
        })
    return campos


def _reordenar_exercicios_bloco(db: Session, plano_id: int, bloco: str) -> None:
    """Mantém a ordenação sequencial dos exercícios dentro de cada bloco."""
    exercicios = (
        db.query(ExercicioPlano)
        .filter(
            ExercicioPlano.plano_id == plano_id,
            ExercicioPlano.bloco == bloco,
        )
        .order_by(ExercicioPlano.ordem.asc(), ExercicioPlano.id.asc())
        .all()
    )
    for indice, exercicio in enumerate(exercicios, start=1):
        exercicio.ordem = indice


def _reordenar_blocos(db: Session, plano_id: int) -> None:
    blocos = db.query(BlocoTreino).filter(BlocoTreino.plano_id == plano_id).order_by(BlocoTreino.ordem, BlocoTreino.id).all()
    for indice, bloco in enumerate(blocos, 1):
        bloco.ordem = indice


def _construir_resumo_blocos(plano: PlanoTreino | None) -> list[dict]:
    """Resume o conteúdo de cada bloco para o cabeçalho da ficha."""
    resumo = []
    exercicios = list(plano.exercicios or []) if plano else []
    blocos = list(plano.blocos or []) if plano else []
    for bloco_dinamico in blocos:
        exercicios_bloco = [ex for ex in exercicios if ex.bloco_id == bloco_dinamico.id]
        resumo.append({
            "bloco": bloco_dinamico.nome,
            "bloco_id": bloco_dinamico.id,
            "total": len(exercicios_bloco),
            "minutos": sum(ex.minutos or 0 for ex in exercicios_bloco),
            "categorias": sorted({ex.categoria for ex in exercicios_bloco if ex.categoria}),
        })
    for bloco in ["A", "B", "C", "D"]:
        exercicios_bloco = [ex for ex in exercicios if not ex.bloco_id and (ex.bloco or "A") == bloco]
        if exercicios_bloco:
            resumo.append({"bloco": bloco, "bloco_id": None, "total": len(exercicios_bloco), "minutos": sum(ex.minutos or 0 for ex in exercicios_bloco), "categorias": sorted({ex.categoria for ex in exercicios_bloco if ex.categoria})})
    return resumo


def _contexto_impressao_plano(request, sessao, equipa, plano, utilizador, db: Session | None = None) -> dict:
    """Prepara uma ficha estável para HTML de impressão e WeasyPrint."""
    caminho_campo_meio = STATIC_DIR / "campos" / "campo_meio.png"
    caminho_campo_completo = STATIC_DIR / "campos" / "campo_completo.png"
    exercicios_por_bloco = {f"d{bloco.id}": [] for bloco in plano.blocos} if plano else {}
    exercicios = list(plano.exercicios or []) if plano else []
    nome_treinador = getattr(getattr(utilizador, "treinador", None), "nome", None)
    if not nome_treinador and getattr(equipa, "treinadores", None):
        nome_treinador = equipa.treinadores[0].nome
    for exercicio in exercicios:
        bloco = f"d{exercicio.bloco_id}" if exercicio.bloco_id else (exercicio.bloco or "A")
        if bloco not in exercicios_por_bloco and not exercicio.bloco_id:
            exercicios_por_bloco[bloco] = []
        if bloco in exercicios_por_bloco:
            campos_pdf = []
            for campo in _campos_exercicio(exercicio):
                caminho = caminho_campo_meio if campo["tipo"] == "meio" else caminho_campo_completo
                campos_pdf.append({
                    **campo,
                    "imagem_composta": compor_desenho_sobre_campo(caminho, campo["desenho"]),
                })
            setattr(exercicio, "campos_pdf", campos_pdf)
            exercicios_por_bloco[bloco].append(exercicio)

    usa_blocos = bool(plano and plano.blocos)
    resumo_blocos = _construir_resumo_blocos(plano)
    return {
        "utilizador": utilizador,
        "sessao": sessao,
        "equipa": equipa,
        "plano": plano,
        "exercicios_por_bloco": exercicios_por_bloco,
        "resumo_blocos": [item for item in resumo_blocos if item["bloco_id"] is not None] if usa_blocos else [],
        "blocos_ui": ([{"key": f"d{bloco.id}", "id": bloco.id, "nome": bloco.nome, "tipo": bloco.tipo, "legado": False} for bloco in plano.blocos] if plano else []) + [{"key": letra, "id": None, "nome": "Exercícios sem bloco", "tipo": None, "legado": True} for letra in ["A", "B", "C", "D"] if letra in exercicios_por_bloco],
        "exercicios_lista": sorted(exercicios, key=lambda ex: (ex.ordem or 0, ex.id or 0)),
        "usa_blocos": usa_blocos,
        "total_exercicios": len(exercicios),
        "volume_planeado": sum(ex.minutos or 0 for ex in exercicios),
        "rpe_geral": sessao.intensidade_rpe,
        "campo_meio_data_uri": imagem_estatica_data_uri(caminho_campo_meio),
        "campo_completo_data_uri": imagem_estatica_data_uri(caminho_campo_completo),
        "identidade": getattr(request.state, "identidade_clube", {}),
        "nome_treinador": nome_treinador or utilizador.nome,
        "equipas_treino": _equipas_para_impressao(db, equipa, plano) if db else [],
    }


def _obter_equipa_id_por_sessao(db: Session, sessao_id: int) -> int | None:
    """Resolve a equipa associada a uma sessão de treino."""
    sessao = db.query(SessaoTreino).filter(SessaoTreino.id == sessao_id).first()
    if not sessao or not sessao.microciclo or not sessao.microciclo.mesociclo or not sessao.microciclo.mesociclo.macrociclo:
        return None
    return sessao.microciclo.mesociclo.macrociclo.equipa_id


def _obter_equipa_id_por_plano(db: Session, plano_id: int) -> int | None:
    """Resolve a equipa associada a um plano de treino."""
    plano = db.query(PlanoTreino).filter(PlanoTreino.id == plano_id).first()
    if not plano:
        return None
    return _obter_equipa_id_por_sessao(db, plano.sessao_id)


def _obter_equipa_id_por_exercicio(db: Session, exercicio_id: int) -> int | None:
    """Resolve a equipa associada a um exercício do plano."""
    exercicio = db.query(ExercicioPlano).filter(ExercicioPlano.id == exercicio_id).first()
    if not exercicio:
        return None
    return _obter_equipa_id_por_plano(db, exercicio.plano_id)


def _verificar_acesso_treino(utilizador, equipa_id: int | None, db: Session) -> None:
    """Valida se o utilizador pode aceder ao treino; lança AcessoNegado se não."""
    if not equipa_id or not verificar_acesso_equipa(utilizador, equipa_id, db):
        raise AcessoNegado("/equipas")


def _marcar_sessao_como_alterada_manual(sessao: SessaoTreino | None):
    """Assinala que a sessão originada do planeamento global foi mexida manualmente."""
    if not sessao or sessao.origem != "planeamento_global":
        return
    sessao.alterada_manual = True
    sessao.sincronizada = False


def _validar_intervalo_horario(hora_inicio: str | None, hora_fim: str | None) -> str | None:
    """Garante coerência mínima no horário da sessão."""
    if not hora_valida(hora_inicio) or not hora_valida(hora_fim):
        return "As horas do treino devem estar no formato HH:MM."
    hora_inicio_normalizada = normalizar_hora(hora_inicio)
    hora_fim_normalizada = normalizar_hora(hora_fim)
    if hora_inicio_normalizada and hora_fim_normalizada and not hora_eh_anterior(
        hora_inicio_normalizada,
        hora_fim_normalizada,
    ):
        return "A hora de início tem de ser anterior à hora de término."
    return None


def _normalizar_rpe(valor: str | None) -> float | None:
    """Converte e valida um RPE numa escala de 1 a 10."""
    if not valor or not valor.strip():
        return None
    try:
        rpe = float(valor.replace(",", "."))
    except ValueError:
        raise ValueError("O RPE deve ser um número entre 1 e 10.")
    if not 1 <= rpe <= 10:
        raise ValueError("O RPE deve estar entre 1 e 10.")
    return rpe


def _normalizar_minutos(valor: str | None) -> int | None:
    """Converte a duração de um exercício e evita erros 500 em formulários manuais."""
    if not valor or not valor.strip():
        return None
    try:
        minutos = int(valor)
    except (TypeError, ValueError) as erro:
        raise ValueError("Os minutos devem ser um número inteiro entre 1 e 240.") from erro
    if not 1 <= minutos <= 240:
        raise ValueError("Os minutos devem estar entre 1 e 240.")
    return minutos


def _duracao_prevista_minutos(sessao: SessaoTreino) -> int | None:
    if not sessao.hora_inicio or not sessao.hora_fim:
        return None
    try:
        inicio_h, inicio_m = map(int, sessao.hora_inicio.split(":"))
        fim_h, fim_m = map(int, sessao.hora_fim.split(":"))
    except (TypeError, ValueError):
        return None
    duracao = (fim_h * 60 + fim_m) - (inicio_h * 60 + inicio_m)
    return duracao if duracao > 0 else None


def _somar_minutos_hora(hora: str | None, minutos: int | None) -> str | None:
    """Soma uma duração a uma hora válida e devolve HH:MM."""
    hora_normalizada = normalizar_hora(hora, permitir_vazio=False)
    if not hora_normalizada or minutos is None or minutos < 0:
        return hora_normalizada
    hora_h, hora_m = map(int, hora_normalizada.split(":"))
    total = (hora_h * 60 + hora_m + minutos) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def _hora_sugerida_exercicio(sessao: SessaoTreino, exercicios: list[ExercicioPlano]) -> str | None:
    """Sugere o início seguinte ao término cronologicamente mais tardio."""
    hora_inicio = normalizar_hora(sessao.hora_inicio, permitir_vazio=False)
    if not exercicios:
        return hora_inicio

    if hora_inicio:
        inicio_h, inicio_m = map(int, hora_inicio.split(":"))
        inicio_minutos = inicio_h * 60 + inicio_m
        terminos = []
        for exercicio in exercicios:
            hora_exercicio = normalizar_hora(exercicio.hora, permitir_vazio=False)
            if not hora_exercicio:
                continue
            hora_h, hora_m = map(int, hora_exercicio.split(":"))
            minutos_exercicio = hora_h * 60 + hora_m
            deslocamento = (minutos_exercicio - inicio_minutos) % (24 * 60)
            terminos.append(deslocamento + max(exercicio.minutos or 0, 0))
        if terminos:
            return _somar_minutos_hora(hora_inicio, max(terminos))

    if hora_inicio:
        return _somar_minutos_hora(hora_inicio, sum(ex.minutos or 0 for ex in exercicios))

    exercicios_com_hora = [
        exercicio for exercicio in exercicios
        if normalizar_hora(exercicio.hora, permitir_vazio=False)
    ]
    if exercicios_com_hora:
        ultimo = max(
            exercicios_com_hora,
            key=lambda ex: normalizar_hora(ex.hora, permitir_vazio=False),
        )
        return _somar_minutos_hora(ultimo.hora, ultimo.minutos)
    return None


def _aplicar_ordem_e_horas_exercicios(
    plano: PlanoTreino,
    exercicios_ordenados: list[ExercicioPlano],
) -> str | None:
    """Guarda a sequência visual e recalcula cada início a partir da sessão."""
    hora_corrente = normalizar_hora(
        plano.sessao.hora_inicio or plano.hora_inicio,
        permitir_vazio=False,
    )
    for indice, exercicio in enumerate(exercicios_ordenados, start=1):
        exercicio.ordem = indice
        if hora_corrente:
            exercicio.hora = hora_corrente
            hora_corrente = _somar_minutos_hora(hora_corrente, exercicio.minutos)
    return hora_corrente


def _normalizar_bloco(bloco: str | None) -> str:
    valor = (bloco or "A").strip().upper()
    if valor not in {"A", "B", "C", "D"}:
        raise ValueError("O bloco do exercício deve ser A, B, C ou D.")
    return valor


def _dados_importacao(importacao: ImportacaoPlanoTreino) -> dict:
    try:
        dados = json.loads(importacao.dados_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        dados = {}
    base = interpretar_texto("")
    base.update(dados if isinstance(dados, dict) else {})
    base["cabecalho"] = {**interpretar_texto("")["cabecalho"], **(base.get("cabecalho") or {})}
    base["exercicios"] = base.get("exercicios") or []
    return base


def _obter_importacao(db: Session, importacao_id: int) -> ImportacaoPlanoTreino | None:
    return db.query(ImportacaoPlanoTreino).filter(ImportacaoPlanoTreino.id == importacao_id).first()


def _importacao_ativa(plano: PlanoTreino) -> ImportacaoPlanoTreino | None:
    """Devolve apenas o documento que representa atualmente a ficha importada."""
    return next((item for item in plano.importacoes if item.estado == "aplicada"), None)


def _resumo_setores(sessao: SessaoTreino) -> list[dict]:
    return [
        {
            "codigo": categoria,
            "campo": campo,
            "minutos": getattr(sessao, campo, 0) or 0,
        }
        for categoria, campo in CAMPOS_CATEGORIA.items()
    ]


def _texto_previsualizacao(importacao: ImportacaoPlanoTreino | None, limite: int = 30_000) -> str:
    if not importacao or not importacao.texto_extraido:
        return "Não foi possível gerar uma pré-visualização textual. Descarrega o original para o consultar."
    texto = importacao.texto_extraido.strip()
    if len(texto) <= limite:
        return texto
    return f"{texto[:limite].rstrip()}\n\n[Pré-visualização limitada. Descarrega o original para consultar o restante conteúdo.]"


def _repor_ficha_importada(db: Session, plano: PlanoTreino) -> None:
    """Repõe o conteúdo técnico sem remover a sessão logística do calendário."""
    sessao = plano.sessao
    for exercicio in list(plano.exercicios):
        db.delete(exercicio)
    db.flush()
    for bloco in list(plano.blocos):
        db.delete(bloco)
    for conteudo in list(sessao.conteudos):
        db.delete(conteudo)

    plano.hora_inicio = None
    plano.escalao = None
    plano.objectivos = None
    plano.reflexao = None
    sessao.volume_minutos = 0
    sessao.intensidade_rpe = 0
    sessao.reflexao = None
    sessao.estado = "planeada"
    for campo in CAMPOS_CATEGORIA.values():
        setattr(sessao, campo, 0)


def _aplicar_importacao_automaticamente(
    db: Session,
    importacao: ImportacaoPlanoTreino,
    dados: dict,
) -> int:
    """Transforma imediatamente os dados reconhecidos numa ficha editável."""
    plano = importacao.plano
    sessao = plano.sessao
    cabecalho = dados.get("cabecalho") or {}

    # O documento importado passa a representar a ficha técnica atual.
    for exercicio in list(plano.exercicios):
        db.delete(exercicio)
    db.flush()
    for bloco in list(plano.blocos):
        db.delete(bloco)
    db.flush()

    novos: list[ExercicioPlano] = []
    ordens: dict[str, int] = {}
    for indice, item in enumerate((dados.get("exercicios") or [])[:200], start=1):
        categoria = normalizar_categoria(str(item.get("categoria") or ""))
        try:
            minutos = _normalizar_minutos(str(item.get("minutos") or ""))
        except ValueError:
            minutos = None
        try:
            rpe = _normalizar_rpe(str(item.get("rpe") or ""))
        except ValueError:
            rpe = None
        try:
            bloco = _normalizar_bloco(str(item.get("bloco") or "A"))
        except ValueError:
            bloco = "A"
        nome = str(item.get("nome") or "").strip() or f"Exercício {indice}"
        ordens[bloco] = ordens.get(bloco, 0) + 1
        novos.append(ExercicioPlano(
            plano_id=plano.id,
            bloco=bloco,
            ordem=ordens[bloco],
            nome=nome[:255],
            categoria=categoria,
            hora=normalizar_hora(str(item.get("hora") or "")) or None,
            minutos=minutos,
            rpe=rpe,
            organizacao=str(item.get("organizacao") or "").strip() or None,
            coaching_points=str(item.get("coaching_points") or "").strip() or None,
            campos_ativos="",
        ))
    db.add_all(novos)
    db.flush()

    data_anterior = sessao.data
    data_texto = str(cabecalho.get("data") or "").strip()
    if data_texto:
        try:
            data_importada = datetime.strptime(data_texto, "%Y-%m-%d").date()
            if sessao.microciclo.data_inicio <= data_importada <= sessao.microciclo.data_fim:
                sessao.data = data_importada
        except ValueError:
            pass

    hora_inicio = normalizar_hora(str(cabecalho.get("hora_inicio") or ""))
    hora_fim = normalizar_hora(str(cabecalho.get("hora_fim") or ""))
    if not _validar_intervalo_horario(hora_inicio, hora_fim):
        sessao.hora_inicio = hora_inicio
        sessao.hora_fim = hora_fim
        plano.hora_inicio = hora_inicio
    if str(cabecalho.get("local") or "").strip():
        sessao.local = str(cabecalho["local"]).strip()[:255]
    if str(cabecalho.get("escalao") or "").strip():
        plano.escalao = str(cabecalho["escalao"]).strip()[:255]
    if str(cabecalho.get("objectivos") or "").strip():
        plano.objectivos = str(cabecalho["objectivos"]).strip()

    try:
        rpe_geral = _normalizar_rpe(str(cabecalho.get("rpe_geral") or ""))
    except ValueError:
        rpe_geral = None
    try:
        volume_importado = int(str(cabecalho.get("volume_minutos") or "").strip())
        if not 0 <= volume_importado <= 600:
            volume_importado = None
    except (TypeError, ValueError):
        volume_importado = None
    sessao.intensidade_rpe = rpe_geral
    sessao.volume_minutos = volume_importado if volume_importado is not None else sum(item.minutos or 0 for item in novos)
    sincronizar_minutos_categorias(plano, db)
    _marcar_sessao_como_alterada_manual(sessao)

    for anterior in plano.importacoes:
        if anterior.id != importacao.id and anterior.estado == "aplicada":
            anterior.estado = "arquivada"
    importacao.estado = "aplicada"
    importacao.atualizado_em = datetime.now()
    sessao.estado = "planeada"
    if sessao.data != data_anterior:
        renumerar_treinos_equipa(db, sessao.microciclo.mesociclo.macrociclo.equipa_id)
    return len(novos)


@router.get("/equipas/{equipa_id}/planos", response_class=HTMLResponse)
def listar_planos_treino_equipa(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    """Apresenta todas as sessões de treino como acesso direto aos respetivos planos."""
    _verificar_acesso_treino(utilizador, equipa_id, db)
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas", status_code=303)

    sessoes = db.query(SessaoTreino).join(Microciclo).join(Mesociclo).join(Macrociclo).filter(
        Macrociclo.equipa_id == equipa_id,
        SessaoTreino.ativa.is_(True),
        SessaoTreino.e_jogo.is_(False),
    ).order_by(
        Macrociclo.planeamento_anual_equipa_id.asc(),
        SessaoTreino.tipo_treino.asc(),
        SessaoTreino.numero_treino.asc(),
        SessaoTreino.data.asc(),
        SessaoTreino.hora_inicio.asc(),
        SessaoTreino.id.asc(),
    ).all()
    sessoes_ui = [enriquecer_sessao_para_ui(sessao) for sessao in sessoes]
    hoje = date.today()
    sessoes_hoje = [sessao for sessao in sessoes_ui if sessao.data == hoje]
    sessoes_restantes = [sessao for sessao in sessoes_ui if sessao.data != hoje]
    return templates.TemplateResponse(request, "treino/lista_equipa.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "sessoes": sessoes_ui,
        "sessoes_hoje": sessoes_hoje,
        "sessoes_restantes": sessoes_restantes,
        "hoje": hoje,
    })


# ─────────────────────────────────────────
# PÁGINA DO PLANO DE TREINO DE UMA SESSÃO
# URL: GET /treino/sessoes/{sessao_id}
# ─────────────────────────────────────────
@router.get("/sessoes/{sessao_id}", response_class=HTMLResponse)
def pagina_plano_treino(sessao_id: int, request: Request, db: Session = Depends(get_db),
                        utilizador=Depends(exigir_autenticacao)):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_sessao(db, sessao_id), db)

    sessao = db.query(SessaoTreino).filter(SessaoTreino.id == sessao_id).first()
    if not sessao:
        return RedirectResponse(url="/equipas")
    sessao = enriquecer_sessao_para_ui(sessao)

    equipa = sessao.microciclo.mesociclo.macrociclo.equipa

    plano = db.query(PlanoTreino).filter(PlanoTreino.sessao_id == sessao_id).first()

    if not plano:
        plano = PlanoTreino(sessao_id=sessao_id)
        db.add(plano)
        db.commit()
        db.refresh(plano)

    exercicios_por_bloco = {f"d{bloco.id}": [] for bloco in plano.blocos}
    for ex in plano.exercicios:
        setattr(ex, "campos_ui", _campos_exercicio(ex))
        bloco = f"d{ex.bloco_id}" if ex.bloco_id else (ex.bloco or "A")
        exercicios_por_bloco.setdefault(bloco, []).append(ex)

    espacos_disponiveis = obter_previsao_equipa(db, equipa.id, sessao.data, sessao.data)
    validacao_local = validar_local_sessao(db, sessao, equipa.id)

    volume_planeado = sum(ex.minutos or 0 for ex in plano.exercicios)
    registos_pse = db.query(RegistoAssiduidade).filter(
        RegistoAssiduidade.sessao_id == sessao_id,
        RegistoAssiduidade.rpe_individual.isnot(None),
    ).all()
    pse_real = calcular_pse_real(registos_pse)
    carga_real = (
        round((volume_planeado or 0) * pse_real, 1)
        if pse_real is not None else None
    )
    duracao_prevista = _duracao_prevista_minutos(sessao)
    importacao_ativa = _importacao_ativa(plano)
    modo_edicao_importacao = bool(importacao_ativa and request.query_params.get("editar") == "1")
    conteudos_previstos = construir_sugestoes_plano_treino(sessao)
    prioridades_microciclo = obter_sugestoes_conteudos_microciclo(db, sessao.microciclo)
    nomes_previstos = {
        item["descricao"].strip().casefold()
        for grupo in conteudos_previstos["grupos"]
        for item in grupo["itens"]
    }
    prioridades_microciclo["itens"] = [
        item for item in prioridades_microciclo["itens"]
        if item["nome"].strip().casefold() not in nomes_previstos
    ]
    atletas_treino = _dados_atletas_plano(db, equipa, sessao.id)
    atletas_previstos_ids = _ids_atletas_previstos(plano, atletas_treino)
    equipas_treino_estado = _estado_equipas_guardado(plano, atletas_previstos_ids, atletas_treino)
    return templates.TemplateResponse(request, "treino/plano.html", {
        "utilizador": utilizador,
        "sessao": sessao,
        "equipa": equipa,
        "plano": plano,
        "exercicios_por_bloco": exercicios_por_bloco,
        "espacos_disponiveis": espacos_disponiveis,
        "validacao_local": validacao_local,
        "categorias_exercicio": CATEGORIAS_EXERCICIO,
        "resumo_blocos": _construir_resumo_blocos(plano),
        "blocos_ui": [{"key": f"d{bloco.id}", "id": bloco.id, "nome": bloco.nome, "tipo": bloco.tipo, "legado": False} for bloco in plano.blocos] + [{"key": letra, "id": None, "nome": f"Bloco {letra}", "tipo": "Legado", "legado": True} for letra in ["A", "B", "C", "D"] if letra in exercicios_por_bloco],
        "total_exercicios": len(plano.exercicios),
        "volume_planeado": volume_planeado,
        "pse_real": pse_real,
        "carga_real": carga_real,
        "pse_real_respostas": len(registos_pse),
        "duracao_prevista": duracao_prevista,
        "diferenca_duracao": volume_planeado - duracao_prevista if duracao_prevista is not None else None,
        "estados_sessao": opcoes_transicao_sessao(sessao.estado),
        "importacoes_plano": list(plano.importacoes[:5]),
        "importacao_ativa": importacao_ativa,
        "modo_edicao_importacao": modo_edicao_importacao,
        "previsualizacao_importacao": _texto_previsualizacao(importacao_ativa),
        "resumo_setores": _resumo_setores(sessao),
        "conteudos_previstos": conteudos_previstos,
        "prioridades_microciclo": prioridades_microciclo,
        "hora_sugerida_exercicio": _hora_sugerida_exercicio(sessao, list(plano.exercicios)),
        "atletas_treino": atletas_treino,
        "atletas_escalhao_inferior_convocaveis": _atletas_escalhao_inferior_convocaveis(db, equipa, sessao.id),
        "escalao_inferior_convocavel": escalao_imediatamente_inferior_da_equipa(equipa),
        "atletas_previstos_ids": atletas_previstos_ids,
        "equipas_treino_estado": equipas_treino_estado,
    })


@router.post("/planos/{plano_id}/atletas-previstos")
async def guardar_atletas_previstos(
    plano_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, plano_id), db)
    plano = db.query(PlanoTreino).filter(PlanoTreino.id == plano_id).first()
    if not plano:
        return JSONResponse({"sucesso": False, "erro": "Plano de treino não encontrado."}, status_code=404)
    try:
        dados = await request.json()
    except (TypeError, ValueError, json.JSONDecodeError):
        return JSONResponse({"sucesso": False, "erro": "A seleção enviada não é válida."}, status_code=400)
    ids = dados.get("jogador_ids") if isinstance(dados, dict) else None
    if not isinstance(ids, list) or any(isinstance(valor, bool) or not isinstance(valor, int) for valor in ids):
        return JSONResponse({"sucesso": False, "erro": "A seleção enviada não é válida."}, status_code=422)
    if len(ids) != len(set(ids)):
        return JSONResponse({"sucesso": False, "erro": "Cada atleta só pode ser selecionado uma vez."}, status_code=422)

    equipa = plano.sessao.microciclo.mesociclo.macrociclo.equipa
    disponiveis = {atleta["id"] for atleta in _dados_atletas_plano(db, equipa, plano.sessao_id)}
    if not set(ids).issubset(disponiveis):
        return JSONResponse({"sucesso": False, "erro": "A seleção contém atletas indisponíveis para este treino."}, status_code=403)
    plano.atletas_previstos = json.dumps(ids)
    plano.equipas_aleatorias = None
    _marcar_sessao_como_alterada_manual(plano.sessao)
    db.commit()
    return JSONResponse({
        "sucesso": True,
        "mensagem": f"{len(ids)} atleta(s) previsto(s) guardado(s).",
        "jogador_ids": ids,
    })


@router.post("/planos/{plano_id}/convocar-escalhao-inferior")
@router.post("/planos/{plano_id}/convocar-sub18", include_in_schema=False)
async def convocar_atletas_escalhao_inferior(
    plano_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, plano_id), db)
    plano = db.query(PlanoTreino).filter(PlanoTreino.id == plano_id).first()
    if not plano:
        return JSONResponse({"sucesso": False, "erro": "Plano de treino não encontrado."}, status_code=404)
    try:
        dados = await request.json()
    except (TypeError, ValueError, json.JSONDecodeError):
        return JSONResponse({"sucesso": False, "erro": "A convocatória enviada não é válida."}, status_code=400)
    ids = dados.get("jogador_ids") if isinstance(dados, dict) else None
    if not isinstance(ids, list) or not ids or any(isinstance(valor, bool) or not isinstance(valor, int) for valor in ids):
        return JSONResponse({"sucesso": False, "erro": "Seleciona pelo menos um atleta do escalão inferior."}, status_code=422)

    equipa = plano.sessao.microciclo.mesociclo.macrociclo.equipa
    convocaveis = {jogador.id: jogador for jogador in _atletas_escalhao_inferior_convocaveis(db, equipa, plano.sessao_id)}
    if len(ids) != len(set(ids)) or not set(ids).issubset(convocaveis):
        return JSONResponse({"sucesso": False, "erro": "A seleção contém atletas do escalão inferior indisponíveis."}, status_code=422)

    anteriores = None if plano.atletas_previstos is None else _carregar_json(plano.atletas_previstos, [])
    for jogador_id in ids:
        db.add(ConvocacaoAssiduidade(
            clube_id=equipa.clube_id,
            sessao_id=plano.sessao_id,
            jogador_id=jogador_id,
        ))
    db.flush()
    atletas = _dados_atletas_plano(db, equipa, plano.sessao_id)
    if anteriores is None:
        previstos_ids = [atleta["id"] for atleta in atletas]
    else:
        previstos_ids = _ids_atletas_previstos(plano, atletas)
        previstos_ids.extend(jogador_id for jogador_id in ids if jogador_id not in previstos_ids)
        plano.atletas_previstos = json.dumps(previstos_ids)
    plano.equipas_aleatorias = None
    _marcar_sessao_como_alterada_manual(plano.sessao)
    db.commit()
    adicionados = [atleta for atleta in atletas if atleta["id"] in ids]
    return JSONResponse({
        "sucesso": True,
        "mensagem": f"{len(adicionados)} atleta(s) convocado(s) e selecionado(s).",
        "adicionados": adicionados,
        "jogador_ids": previstos_ids,
    })


@router.post("/planos/{plano_id}/equipas-aleatorias/gerar")
async def gerar_equipas_aleatorias(
    plano_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, plano_id), db)
    plano = db.query(PlanoTreino).filter(PlanoTreino.id == plano_id).first()
    if not plano:
        return JSONResponse({"sucesso": False, "erro": "Plano de treino não encontrado."}, status_code=404)
    try:
        dados = await request.json()
        tamanho = int(dados.get("tamanho"))
        postes = int(dados.get("postes_por_equipa", 2 if tamanho == 5 else 1))
        grupo_id = int(dados["grupo_id"]) if dados.get("grupo_id") is not None else None
    except (TypeError, ValueError, json.JSONDecodeError):
        return JSONResponse({"sucesso": False, "erro": "Escolhe uma configuração válida."}, status_code=422)

    equipa = plano.sessao.microciclo.mesociclo.macrociclo.equipa
    atletas = _dados_atletas_plano(db, equipa, plano.sessao_id)
    previstos = set(_ids_atletas_previstos(plano, atletas))
    selecionados = [atleta for atleta in atletas if atleta["id"] in previstos]
    try:
        equipas_geradas = gerar_equipas_equilibradas(selecionados, tamanho, postes)
    except ValueError as erro:
        return JSONResponse({"sucesso": False, "erro": str(erro)}, status_code=422)
    estado = _estado_equipas_guardado(plano, list(previstos), atletas) or {"grupos": []}
    grupos = estado["grupos"]
    if grupo_id is None:
        grupo_id = max((grupo["id"] for grupo in grupos), default=0) + 1
        grupo = {"id": grupo_id, "nome": f"Agrupamento {len(grupos) + 1}", **equipas_geradas}
        grupos.append(grupo)
    else:
        grupo_atual = next((grupo for grupo in grupos if grupo["id"] == grupo_id), None)
        if not grupo_atual:
            return JSONResponse({"sucesso": False, "erro": "Agrupamento não encontrado."}, status_code=404)
        grupo = {"id": grupo_id, "nome": grupo_atual["nome"], **equipas_geradas}
        grupos[grupos.index(grupo_atual)] = grupo
    plano.equipas_aleatorias = json.dumps(estado, ensure_ascii=False)
    _marcar_sessao_como_alterada_manual(plano.sessao)
    db.commit()
    return JSONResponse({"sucesso": True, "mensagem": "Agrupamento gerado.", "grupo": grupo, "estado": estado})


@router.post("/planos/{plano_id}/equipas-aleatorias")
async def guardar_organizacao_equipas(
    plano_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, plano_id), db)
    plano = db.query(PlanoTreino).filter(PlanoTreino.id == plano_id).first()
    if not plano:
        return JSONResponse({"sucesso": False, "erro": "Plano de treino não encontrado."}, status_code=404)
    try:
        dados = await request.json()
    except (TypeError, ValueError, json.JSONDecodeError):
        return JSONResponse({"sucesso": False, "erro": "A organização enviada não é válida."}, status_code=400)
    equipas_recebidas = dados.get("equipas") if isinstance(dados, dict) else None
    if not isinstance(equipas_recebidas, list) or not equipas_recebidas:
        return JSONResponse({"sucesso": False, "erro": "A organização enviada não é válida."}, status_code=422)

    equipa = plano.sessao.microciclo.mesociclo.macrociclo.equipa
    atletas = _dados_atletas_plano(db, equipa, plano.sessao_id)
    previstos = set(_ids_atletas_previstos(plano, atletas))
    recebidos = []
    equipas = []
    for indice, slots in enumerate(equipas_recebidas):
        if not isinstance(slots, list) or any(
            valor is not None and (isinstance(valor, bool) or not isinstance(valor, int)) for valor in slots
        ):
            return JSONResponse({"sucesso": False, "erro": "Uma das equipas contém dados inválidos."}, status_code=422)
        recebidos.extend(valor for valor in slots if valor is not None)
        equipas.append({"nome": f"Equipa {indice + 1}", "slots": slots})
    if len(recebidos) != len(set(recebidos)) or set(recebidos) != previstos:
        return JSONResponse({"sucesso": False, "erro": "Todos os atletas previstos devem aparecer uma única vez."}, status_code=422)

    estado = _estado_equipas_guardado(plano, list(previstos), atletas)
    if not estado:
        return JSONResponse({"sucesso": False, "erro": "Agrupamento não encontrado."}, status_code=404)
    try:
        grupo_id = int(dados.get("grupo_id")) if dados.get("grupo_id") is not None else estado["grupos"][0]["id"]
    except (TypeError, ValueError):
        return JSONResponse({"sucesso": False, "erro": "Agrupamento inválido."}, status_code=422)
    grupo = next((item for item in estado["grupos"] if item["id"] == grupo_id), None)
    if not grupo:
        return JSONResponse({"sucesso": False, "erro": "Agrupamento não encontrado."}, status_code=404)
    grupo["equipas"] = equipas
    plano.equipas_aleatorias = json.dumps(estado, ensure_ascii=False)
    _marcar_sessao_como_alterada_manual(plano.sessao)
    db.commit()
    return JSONResponse({"sucesso": True, "mensagem": "Organização das equipas guardada.", "estado": estado})


@router.post("/planos/{plano_id}/equipas-aleatorias/{grupo_id}/eliminar")
def eliminar_agrupamento_equipas(
    plano_id: int,
    grupo_id: int,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, plano_id), db)
    plano = db.query(PlanoTreino).filter(PlanoTreino.id == plano_id).first()
    if not plano:
        return JSONResponse({"sucesso": False, "erro": "Plano de treino não encontrado."}, status_code=404)
    equipa = plano.sessao.microciclo.mesociclo.macrociclo.equipa
    atletas = _dados_atletas_plano(db, equipa, plano.sessao_id)
    previstos = _ids_atletas_previstos(plano, atletas)
    estado = _estado_equipas_guardado(plano, previstos, atletas)
    if not estado or not any(grupo["id"] == grupo_id for grupo in estado["grupos"]):
        return JSONResponse({"sucesso": False, "erro": "Agrupamento não encontrado."}, status_code=404)
    estado["grupos"] = [grupo for grupo in estado["grupos"] if grupo["id"] != grupo_id]
    for indice, grupo in enumerate(estado["grupos"], start=1):
        grupo["nome"] = f"Agrupamento {indice}"
    plano.equipas_aleatorias = json.dumps(estado, ensure_ascii=False) if estado["grupos"] else None
    _marcar_sessao_como_alterada_manual(plano.sessao)
    db.commit()
    return JSONResponse({"sucesso": True, "mensagem": "Agrupamento eliminado.", "estado": estado})


@router.post("/planos/{plano_id}/importacoes")
async def importar_plano_treino(
    plano_id: int,
    request: Request,
    ficheiro: UploadFile = File(...),
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    """Guarda o original e transforma-o imediatamente numa ficha editável."""
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, plano_id), db)
    plano = db.query(PlanoTreino).filter(PlanoTreino.id == plano_id).first()
    if not plano:
        return RedirectResponse(url="/equipas", status_code=303)

    conteudo = await ficheiro.read(MAX_FICHEIRO_BYTES + 1)
    try:
        nome, tipo_mime = validar_ficheiro(ficheiro.filename or "", ficheiro.content_type, conteudo)
        texto_extraido, confianca, avisos_extracao = extrair_texto(nome, conteudo)
        dados = interpretar_texto(texto_extraido)
        avisos = avisos_extracao + list(dados.get("avisos") or [])
    except ErroImportacaoPlano as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url=f"/treino/sessoes/{plano.sessao_id}", status_code=303)

    importacao = ImportacaoPlanoTreino(
        clube_id=plano.clube_id,
        plano_id=plano.id,
        utilizador_id=utilizador.id,
        nome_original=nome,
        tipo_mime=tipo_mime,
        tamanho_bytes=len(conteudo),
        ficheiro=conteudo,
        texto_extraido=texto_extraido or None,
        dados_json=json.dumps(dados, ensure_ascii=False),
        estado="aplicada",
        confianca=confianca,
        aviso="\n".join(dict.fromkeys(aviso for aviso in avisos if aviso)) or None,
    )
    db.add(importacao)
    db.flush()
    total_exercicios = _aplicar_importacao_automaticamente(db, importacao, dados)
    registar_auditoria(
        db,
        utilizador,
        "importar_plano_treino",
        "ImportacaoPlanoTreino",
        importacao.id,
        f"Ficheiro {nome} importado automaticamente com {total_exercicios} exercício(s).",
        request,
    )
    db.commit()
    set_flash(request, f"Plano importado: {total_exercicios} exercício(s) reconhecido(s). Podes editar todos os dados.")
    return RedirectResponse(url=f"/treino/sessoes/{plano.sessao_id}", status_code=303)


@router.get("/importacoes/{importacao_id}", response_class=HTMLResponse)
def rever_importacao_plano(
    importacao_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    importacao = _obter_importacao(db, importacao_id)
    if not importacao:
        return RedirectResponse(url="/equipas", status_code=303)
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, importacao.plano_id), db)
    plano = importacao.plano
    equipa = plano.sessao.microciclo.mesociclo.macrociclo.equipa
    return templates.TemplateResponse(request, "treino/importacao_rever.html", {
        "utilizador": utilizador,
        "importacao": importacao,
        "dados": _dados_importacao(importacao),
        "plano": plano,
        "sessao": plano.sessao,
        "equipa": equipa,
        "categorias_exercicio": CATEGORIAS_EXERCICIO,
        "blocos_plano": list(plano.blocos),
    })


@router.get("/importacoes/{importacao_id}/ficheiro")
def descarregar_ficheiro_importado(
    importacao_id: int,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    importacao = _obter_importacao(db, importacao_id)
    if not importacao:
        return RedirectResponse(url="/equipas", status_code=303)
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, importacao.plano_id), db)
    nome = quote(importacao.nome_original, safe="")
    return Response(
        content=importacao.ficheiro,
        media_type=importacao.tipo_mime,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{nome}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/importacoes/{importacao_id}/previsualizacao")
def previsualizar_ficheiro_importado(
    importacao_id: int,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    """Mostra apenas formatos que o navegador consegue apresentar com segurança."""
    importacao = _obter_importacao(db, importacao_id)
    if not importacao:
        return RedirectResponse(url="/equipas", status_code=303)
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, importacao.plano_id), db)
    tipos_permitidos = {"application/pdf", "image/png", "image/jpeg"}
    if importacao.tipo_mime not in tipos_permitidos:
        return RedirectResponse(url=f"/treino/importacoes/{importacao.id}", status_code=303)
    nome = quote(importacao.nome_original, safe="")
    return Response(
        content=importacao.ficheiro,
        media_type=importacao.tipo_mime,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{nome}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )


@router.post("/importacoes/{importacao_id}/reinterpretar")
async def reinterpretar_importacao_plano(
    importacao_id: int,
    request: Request,
    texto_extraido: str = Form(""),
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    importacao = _obter_importacao(db, importacao_id)
    if not importacao:
        return RedirectResponse(url="/equipas", status_code=303)
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, importacao.plano_id), db)
    if importacao.estado == "aplicada":
        set_flash(request, "Esta importação já foi aplicada e fica preservada no histórico.", "error")
        return RedirectResponse(url=f"/treino/importacoes/{importacao.id}", status_code=303)
    dados = interpretar_texto(texto_extraido)
    importacao.texto_extraido = texto_extraido.strip() or None
    importacao.dados_json = json.dumps(dados, ensure_ascii=False)
    importacao.aviso = "\n".join(dados.get("avisos") or []) or None
    db.commit()
    set_flash(request, "Texto novamente interpretado. Revê os campos antes de aplicar.")
    return RedirectResponse(url=f"/treino/importacoes/{importacao.id}", status_code=303)


@router.post("/importacoes/{importacao_id}/aplicar")
async def aplicar_importacao_plano(
    importacao_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    importacao = _obter_importacao(db, importacao_id)
    if not importacao:
        return RedirectResponse(url="/equipas", status_code=303)
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, importacao.plano_id), db)
    if importacao.estado == "aplicada":
        set_flash(request, "Esta importação já foi aplicada. Não pode ser aplicada duas vezes.", "error")
        return RedirectResponse(url=f"/treino/importacoes/{importacao.id}", status_code=303)

    plano = importacao.plano
    sessao = plano.sessao
    form = await request.form()
    destino_erro = f"/treino/importacoes/{importacao.id}"
    try:
        data_texto = str(form.get("data") or "").strip()
        nova_data = datetime.strptime(data_texto, "%Y-%m-%d").date() if data_texto else sessao.data
        if not sessao.microciclo.data_inicio <= nova_data <= sessao.microciclo.data_fim:
            raise ValueError(
                "A data deve permanecer dentro do microciclo "
                f"({sessao.microciclo.data_inicio.strftime('%d/%m/%Y')} a "
                f"{sessao.microciclo.data_fim.strftime('%d/%m/%Y')})."
            )
        hora_inicio = normalizar_hora(str(form.get("hora_inicio") or ""))
        hora_fim = normalizar_hora(str(form.get("hora_fim") or ""))
        erro_horario = _validar_intervalo_horario(hora_inicio, hora_fim)
        if erro_horario:
            raise ValueError(erro_horario)
        rpe_geral = _normalizar_rpe(str(form.get("rpe_geral") or ""))
        volume_texto = str(form.get("volume_minutos") or "").strip()
        volume_informado = int(volume_texto) if volume_texto else None
        if volume_informado is not None and not 1 <= volume_informado <= 600:
            raise ValueError("O volume total deve estar entre 1 e 600 minutos.")
    except (TypeError, ValueError) as erro:
        set_flash(request, f"Corrige o cabeçalho: {erro}", "error")
        return RedirectResponse(url=destino_erro, status_code=303)

    nomes = form.getlist("exercicio_nome")
    blocos = form.getlist("exercicio_bloco")
    categorias = form.getlist("exercicio_categoria")
    horas = form.getlist("exercicio_hora")
    minutos = form.getlist("exercicio_minutos")
    rpes = form.getlist("exercicio_rpe")
    organizacoes = form.getlist("exercicio_organizacao")
    coaching = form.getlist("exercicio_coaching_points")
    total_linhas = max((len(nomes), len(blocos), len(categorias), len(horas), len(minutos), len(rpes)), default=0)
    if total_linhas > 200:
        set_flash(request, "Cada importação pode ter no máximo 200 exercícios.", "error")
        return RedirectResponse(url=destino_erro, status_code=303)
    novos = []
    ordens: dict[str, int] = {}
    blocos_validos = {bloco.id for bloco in plano.blocos}

    try:
        for indice in range(total_linhas):
            valor = lambda lista, padrao="": str(lista[indice] if indice < len(lista) else padrao).strip()
            nome = valor(nomes)
            minutos_exercicio = _normalizar_minutos(valor(minutos))
            categoria_texto = valor(categorias)
            categoria = normalizar_categoria(categoria_texto) if categoria_texto else None
            if categoria_texto and not categoria:
                raise ValueError(f"A categoria da linha {indice + 1} não é válida.")
            if not any((nome, minutos_exercicio, categoria, valor(horas), valor(rpes), valor(organizacoes), valor(coaching))):
                continue
            if not nome:
                nome = f"Exercício {indice + 1}"
            bloco_ref = valor(blocos, "A") or "A"
            bloco_id = None
            bloco_legado = None
            if bloco_ref.startswith("d"):
                bloco_id = int(bloco_ref[1:])
                if bloco_id not in blocos_validos:
                    raise ValueError(f"O bloco da linha {indice + 1} já não existe.")
            else:
                bloco_legado = _normalizar_bloco(bloco_ref)
            rpe = _normalizar_rpe(valor(rpes))
            chave_ordem = bloco_ref
            ordens[chave_ordem] = ordens.get(chave_ordem, 0) + 1
            novos.append(ExercicioPlano(
                plano_id=plano.id,
                bloco=bloco_legado,
                bloco_id=bloco_id,
                ordem=ordens[chave_ordem],
                nome=nome[:255],
                categoria=categoria,
                hora=normalizar_hora(valor(horas)) or None,
                minutos=minutos_exercicio,
                rpe=rpe,
                organizacao=valor(organizacoes) or None,
                coaching_points=valor(coaching) or None,
                campos_ativos="",
            ))
    except (TypeError, ValueError) as erro:
        set_flash(request, f"Corrige os exercícios: {erro}", "error")
        return RedirectResponse(url=destino_erro, status_code=303)

    modo = str(form.get("modo") or "adicionar")
    if modo == "substituir":
        for exercicio in list(plano.exercicios):
            db.delete(exercicio)
        db.flush()
    else:
        # Ao adicionar, as novas ordens continuam depois das já existentes.
        for exercicio in novos:
            if exercicio.bloco_id:
                exercicio.ordem += db.query(ExercicioPlano).filter(ExercicioPlano.plano_id == plano.id, ExercicioPlano.bloco_id == exercicio.bloco_id).count()
            else:
                exercicio.ordem += db.query(ExercicioPlano).filter(ExercicioPlano.plano_id == plano.id, ExercicioPlano.bloco == exercicio.bloco).count()
    db.add_all(novos)
    db.flush()

    data_anterior = sessao.data
    sessao.data = nova_data
    sessao.local = str(form.get("local") or "").strip() or None
    sessao.hora_inicio = hora_inicio
    sessao.hora_fim = hora_fim
    sessao.intensidade_rpe = rpe_geral
    sessao.volume_minutos = volume_informado if volume_informado is not None else sum(item.minutos or 0 for item in novos)
    plano.hora_inicio = hora_inicio
    plano.escalao = str(form.get("escalao") or "").strip() or None
    plano.objectivos = str(form.get("objectivos") or "").strip() or None
    _marcar_sessao_como_alterada_manual(sessao)
    db.expire(plano, ["exercicios"])
    sincronizar_minutos_categorias(plano, db)
    if nova_data != data_anterior:
        renumerar_treinos_equipa(db, plano.sessao.microciclo.mesociclo.macrociclo.equipa_id)

    for anterior in plano.importacoes:
        if anterior.id != importacao.id and anterior.estado == "aplicada":
            anterior.estado = "arquivada"
    importacao.estado = "aplicada"
    importacao.atualizado_em = datetime.now()
    sessao.estado = "planeada"
    registar_auditoria(
        db,
        utilizador,
        "aplicar_importacao_plano_treino",
        "ImportacaoPlanoTreino",
        importacao.id,
        f"Aplicados {len(novos)} exercícios em modo {modo}.",
        request,
    )
    db.commit()
    set_flash(request, f"Plano importado e confirmado: {len(novos)} exercício(s) aplicado(s).")
    return RedirectResponse(url=f"/treino/sessoes/{sessao.id}", status_code=303)


@router.post("/importacoes/{importacao_id}/eliminar")
async def eliminar_importacao_plano(
    importacao_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    importacao = _obter_importacao(db, importacao_id)
    if not importacao:
        return RedirectResponse(url="/equipas", status_code=303)
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, importacao.plano_id), db)

    plano = importacao.plano
    sessao_id = plano.sessao_id
    nome_original = importacao.nome_original
    foi_aplicada = importacao.estado == "aplicada"
    if foi_aplicada:
        _repor_ficha_importada(db, plano)
        # Compatibilidade com planos antigos que possam ter mais de uma importação ativa.
        for anterior in plano.importacoes:
            if anterior.id != importacao.id and anterior.estado == "aplicada":
                anterior.estado = "arquivada"

    detalhe_auditoria = (
        f"Importação {nome_original} eliminada e ficha técnica reposta a zero."
        if foi_aplicada
        else f"Importação {nome_original} eliminada antes de ser aplicada."
    )
    registar_auditoria(
        db,
        utilizador,
        "eliminar_importacao_plano_treino",
        "ImportacaoPlanoTreino",
        importacao.id,
        detalhe_auditoria,
        request,
    )
    db.delete(importacao)
    db.commit()
    if foi_aplicada:
        set_flash(request, "Importação eliminada. A ficha de treino ficou novamente vazia.")
    else:
        set_flash(request, "Importação eliminada sem alterar a ficha de treino.")
    return RedirectResponse(url=f"/treino/sessoes/{sessao_id}", status_code=303)


@router.post("/planos/{plano_id}/eliminar")
async def eliminar_plano_treino(
    plano_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    """Apaga apenas a ficha; a sessão prevista mantém-se disponível para recomeçar."""
    equipa_id = _obter_equipa_id_por_plano(db, plano_id)
    _verificar_acesso_treino(utilizador, equipa_id, db)
    plano = db.query(PlanoTreino).filter(PlanoTreino.id == plano_id).first()
    if not plano:
        return RedirectResponse(url="/equipas", status_code=303)
    sessao_id = plano.sessao_id
    for campo in CAMPOS_CATEGORIA.values():
        setattr(plano.sessao, campo, 0)
    db.delete(plano)
    db.commit()
    set_flash(request, "Plano de treino eliminado. A sessão mantém a data, local e horário para criares uma nova ficha.")
    return RedirectResponse(url=f"/treino/sessoes/{sessao_id}", status_code=303)


@router.post("/sessoes/{sessao_id}/eliminar")
async def eliminar_sessao_treino(
    sessao_id: int,
    request: Request,
    retorno: str = Form(""),
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    """Elimina definitivamente o treino, incluindo a respetiva ficha."""
    equipa_id = _obter_equipa_id_por_sessao(db, sessao_id)
    _verificar_acesso_treino(utilizador, equipa_id, db)
    sessao = db.query(SessaoTreino).filter(SessaoTreino.id == sessao_id).first()
    if not sessao:
        return RedirectResponse(url="/equipas", status_code=303)

    microciclo_id = sessao.microciclo_id
    evento = sessao.evento_planeamento_clube
    eliminar_sessoes_treino(db, [sessao])
    if evento and not evento.plano_semanal_id:
        evento_persistido = db.query(EventoPlaneamentoClube).filter(
            EventoPlaneamentoClube.id == evento.id,
        ).first()
        if evento_persistido:
            db.delete(evento_persistido)
    db.commit()
    set_flash(request, "Treino eliminado definitivamente do planeamento e do calendário.")

    destino = retorno if retorno.startswith("/") and not retorno.startswith("//") else f"/planeamento/microciclos/{microciclo_id}"
    return RedirectResponse(url=destino, status_code=303)


@router.post("/sessoes/{sessao_id}/estado")
async def atualizar_estado_sessao(
    sessao_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    estado: str = Form(...),
):
    """Avança ou reabre uma sessão dentro do fluxo operacional permitido."""
    equipa_id = _obter_equipa_id_por_sessao(db, sessao_id)
    _verificar_acesso_treino(utilizador, equipa_id, db)
    sessao = db.query(SessaoTreino).filter(SessaoTreino.id == sessao_id).first()
    if not sessao:
        return RedirectResponse(url="/equipas", status_code=303)

    novo_estado = (estado or "").strip().lower()
    estado_atual = normalizar_estado_sessao(getattr(sessao, "estado", None))
    if novo_estado not in ESTADOS_SESSAO:
        set_flash(request, "Estado da sessão inválido.", "error")
        return RedirectResponse(url=f"/treino/sessoes/{sessao_id}", status_code=303)
    if novo_estado != estado_atual and not transicao_sessao_valida(estado_atual, novo_estado):
        set_flash(
            request,
            f"Não é possível passar diretamente de {estado_atual} para {novo_estado}.",
            "error",
        )
        return RedirectResponse(url=f"/treino/sessoes/{sessao_id}", status_code=303)

    sessao.estado = novo_estado
    db.commit()
    set_flash(request, "Estado da sessão atualizado.")
    return RedirectResponse(url=f"/treino/sessoes/{sessao_id}", status_code=303)


# ─────────────────────────────────────────
# GUARDAR CABEÇALHO DO PLANO
# URL: POST /treino/planos/{plano_id}/cabecalho
# ─────────────────────────────────────────
@router.post("/planos/{plano_id}/cabecalho")
async def guardar_cabecalho(
    plano_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    hora_inicio: str = Form(""),
    hora_fim: str = Form(""),
    local: str = Form(""),
    escalao: str = Form(""),
    objectivos: str = Form(""),
    intensidade_rpe: str = Form(""),
    data_sessao: str = Form("", alias="data"),
):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, plano_id), db)

    plano = db.query(PlanoTreino).filter(PlanoTreino.id == plano_id).first()
    if plano:
        form = await request.form()
        erro_horario = _validar_intervalo_horario(hora_inicio or None, hora_fim or None)
        if erro_horario:
            set_flash(request, erro_horario, "error")
            return RedirectResponse(url=f"/treino/sessoes/{plano.sessao_id}", status_code=303)
        try:
            rpe_geral = _normalizar_rpe(intensidade_rpe)
            nova_data = plano.sessao.data
            if "data" in form and data_sessao:
                nova_data = None
                for formato in ("%d/%m/%Y", "%Y-%m-%d"):
                    try:
                        nova_data = datetime.strptime(data_sessao, formato).date()
                        break
                    except ValueError:
                        continue
                if nova_data is None:
                    raise ValueError("A data deve estar no formato dd/mm/aaaa.")
                if not plano.sessao.microciclo.data_inicio <= nova_data <= plano.sessao.microciclo.data_fim:
                    raise ValueError(
                        "A data deve permanecer dentro do microciclo "
                        f"({plano.sessao.microciclo.data_inicio.strftime('%d/%m/%Y')} a "
                        f"{plano.sessao.microciclo.data_fim.strftime('%d/%m/%Y')})."
                    )

            volume_novo = plano.sessao.volume_minutos
            if "volume_minutos" in form:
                volume_texto = str(form.get("volume_minutos") or "").strip()
                volume_novo = int(volume_texto) if volume_texto else 0
                if not 0 <= volume_novo <= 600:
                    raise ValueError("O volume total deve estar entre 0 e 600 minutos.")

            setores_novos = {}
            for campo in CAMPOS_CATEGORIA.values():
                if campo not in form:
                    continue
                valor_texto = str(form.get(campo) or "").strip()
                valor = int(valor_texto) if valor_texto else 0
                if not 0 <= valor <= 600:
                    raise ValueError("Os tempos por setor devem estar entre 0 e 600 minutos.")
                setores_novos[campo] = valor
            if setores_novos and volume_novo is not None and sum(setores_novos.values()) > volume_novo:
                raise ValueError("A soma dos tempos por setor não pode ultrapassar o volume total.")
        except ValueError as erro:
            set_flash(request, str(erro), "error")
            return RedirectResponse(url=f"/treino/sessoes/{plano.sessao_id}", status_code=303)
        hora_inicio = normalizar_hora(hora_inicio)
        hora_fim = normalizar_hora(hora_fim)

        _marcar_sessao_como_alterada_manual(plano.sessao)
        plano.hora_inicio = hora_inicio
        plano.escalao = escalao or None
        plano.objectivos = objectivos or None
        if plano.sessao:
            data_anterior = plano.sessao.data
            plano.sessao.data = nova_data
            plano.sessao.local = local or None
            plano.sessao.hora_inicio = hora_inicio
            plano.sessao.hora_fim = hora_fim
            plano.sessao.intensidade_rpe = rpe_geral
            plano.sessao.volume_minutos = volume_novo
            for campo, valor in setores_novos.items():
                setattr(plano.sessao, campo, valor)
            if nova_data != data_anterior:
                renumerar_treinos_equipa(db, plano.sessao.microciclo.mesociclo.macrociclo.equipa_id)
            recalcular_horas_exercicios(plano)

            # O cabeçalho é a fonte de verdade para o horário do treino.
            # Quando a sessão veio da agenda do clube, sincroniza também o
            # evento e todas as sessões/plano que lhe estão ligados.
            evento_origem = plano.sessao.evento_planeamento_clube
            if evento_origem:
                evento_origem.hora_inicio = hora_inicio
                evento_origem.hora_fim = hora_fim
                for atribuicao in evento_origem.atribuicoes_espaco:
                    atribuicao.hora_inicio = hora_inicio
                    atribuicao.hora_fim = hora_fim
                for sessao_ligada in evento_origem.sessoes_geradas:
                    sessao_ligada.hora_inicio = hora_inicio
                    sessao_ligada.hora_fim = hora_fim
                    if sessao_ligada.plano_treino:
                        sessao_ligada.plano_treino.hora_inicio = hora_inicio
                        recalcular_horas_exercicios(sessao_ligada.plano_treino)
            elif plano.sessao.plano_semanal_clube:
                equipa_id = plano.sessao.microciclo.mesociclo.macrociclo.equipa_id
                for atribuicao in plano.sessao.plano_semanal_clube.atribuicoes_espacos:
                    if atribuicao.equipa_id == equipa_id and atribuicao.data == nova_data:
                        atribuicao.hora_inicio = hora_inicio
                        atribuicao.hora_fim = hora_fim
        db.commit()
        set_flash(request, "Dados do plano de treino atualizados.")

    return RedirectResponse(url=f"/treino/sessoes/{plano.sessao_id}", status_code=303)


@router.post("/planos/{plano_id}/blocos")
async def criar_bloco(plano_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao), nome: str = Form(...), tipo: str = Form("")):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, plano_id), db)
    plano = db.query(PlanoTreino).filter(PlanoTreino.id == plano_id).first()
    if not plano or not nome.strip():
        set_flash(request, "Indica um nome para o bloco.", "error")
        return RedirectResponse(url=f"/treino/sessoes/{plano.sessao_id if plano else ''}", status_code=303)
    db.add(BlocoTreino(plano_id=plano.id, nome=nome.strip(), tipo=tipo.strip() or None, ordem=len(plano.blocos) + 1))
    _marcar_sessao_como_alterada_manual(plano.sessao)
    db.commit()
    set_flash(request, "Bloco criado. Já podes adicionar exercícios.")
    return RedirectResponse(url=f"/treino/sessoes/{plano.sessao_id}", status_code=303)


@router.post("/blocos/{bloco_id}/editar")
async def editar_bloco(bloco_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao), nome: str = Form(...), tipo: str = Form(""), ordem: int = Form(1)):
    bloco = db.query(BlocoTreino).filter(BlocoTreino.id == bloco_id).first()
    if not bloco:
        return RedirectResponse(url="/equipas", status_code=303)
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, bloco.plano_id), db)
    bloco.nome, bloco.tipo, bloco.ordem = nome.strip() or bloco.nome, tipo.strip() or None, max(1, ordem)
    _reordenar_blocos(db, bloco.plano_id)
    db.commit()
    set_flash(request, "Bloco atualizado.")
    return RedirectResponse(url=f"/treino/sessoes/{bloco.plano.sessao_id}", status_code=303)


@router.post("/blocos/{bloco_id}/duplicar")
async def duplicar_bloco(bloco_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao)):
    bloco = db.query(BlocoTreino).filter(BlocoTreino.id == bloco_id).first()
    if not bloco:
        return RedirectResponse(url="/equipas", status_code=303)
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, bloco.plano_id), db)
    copia = BlocoTreino(plano_id=bloco.plano_id, nome=f"{bloco.nome} (cópia)", tipo=bloco.tipo, ordem=len(bloco.plano.blocos) + 1)
    db.add(copia); db.flush()
    for ex in bloco.exercicios:
        db.add(ExercicioPlano(plano_id=ex.plano_id, bloco_id=copia.id, ordem=ex.ordem, hora=ex.hora, minutos=ex.minutos, rpe=ex.rpe, nome=ex.nome, categoria=ex.categoria, desenho_1=ex.desenho_1, desenho_2=ex.desenho_2, desenho_3=ex.desenho_3, desenho_4=ex.desenho_4, desenhos_campos=ex.desenhos_campos, campos_ativos=ex.campos_ativos, organizacao=ex.organizacao, coaching_points=ex.coaching_points))
    db.flush(); sincronizar_minutos_categorias(bloco.plano, db)
    db.commit(); set_flash(request, "Bloco e exercícios duplicados.")
    return RedirectResponse(url=f"/treino/sessoes/{bloco.plano.sessao_id}", status_code=303)


@router.post("/blocos/{bloco_id}/apagar")
async def apagar_bloco(bloco_id: int, request: Request, db: Session = Depends(get_db), utilizador=Depends(exigir_autenticacao)):
    bloco = db.query(BlocoTreino).filter(BlocoTreino.id == bloco_id).first()
    if not bloco:
        return RedirectResponse(url="/equipas", status_code=303)
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, bloco.plano_id), db)
    if bloco.exercicios:
        set_flash(request, "Remove ou desloca os exercícios antes de apagar o bloco.", "error")
    else:
        plano_id, sessao_id = bloco.plano_id, bloco.plano.sessao_id
        db.delete(bloco); db.flush(); _reordenar_blocos(db, plano_id); db.commit(); set_flash(request, "Bloco removido.")
        return RedirectResponse(url=f"/treino/sessoes/{sessao_id}", status_code=303)
    return RedirectResponse(url=f"/treino/sessoes/{bloco.plano.sessao_id}", status_code=303)


# ─────────────────────────────────────────
# ADICIONAR EXERCÍCIO A UM BLOCO
# URL: POST /treino/planos/{plano_id}/exercicios
# ─────────────────────────────────────────
@router.post("/planos/{plano_id}/exercicios/reordenar")
async def reordenar_exercicios(
    plano_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    """Reordena os cartões e atualiza as horas sem recarregar o plano."""
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, plano_id), db)
    plano = db.query(PlanoTreino).filter(PlanoTreino.id == plano_id).first()
    if not plano:
        return JSONResponse({"sucesso": False, "erro": "Plano de treino não encontrado."}, status_code=404)

    try:
        dados = await request.json()
    except (TypeError, ValueError, json.JSONDecodeError):
        return JSONResponse({"sucesso": False, "erro": "A ordem enviada não é válida."}, status_code=400)

    ids_recebidos = dados.get("exercicio_ids") if isinstance(dados, dict) else None
    if not isinstance(ids_recebidos, list) or any(
        isinstance(valor, bool) or not isinstance(valor, int) for valor in ids_recebidos
    ):
        return JSONResponse({"sucesso": False, "erro": "A ordem enviada não é válida."}, status_code=422)

    exercicios = db.query(ExercicioPlano).filter(ExercicioPlano.plano_id == plano_id).all()
    ids_existentes = {exercicio.id for exercicio in exercicios}
    if len(ids_recebidos) != len(set(ids_recebidos)) or set(ids_recebidos) != ids_existentes:
        return JSONResponse(
            {"sucesso": False, "erro": "A lista deve incluir todos os exercícios do plano uma única vez."},
            status_code=422,
        )

    por_id = {exercicio.id: exercicio for exercicio in exercicios}
    exercicios_ordenados = [por_id[exercicio_id] for exercicio_id in ids_recebidos]
    proxima_hora = _aplicar_ordem_e_horas_exercicios(plano, exercicios_ordenados)
    _marcar_sessao_como_alterada_manual(plano.sessao)
    db.flush()
    sincronizar_minutos_categorias(plano, db)
    db.commit()

    return JSONResponse({
        "sucesso": True,
        "mensagem": "Ordem e horários guardados.",
        "proxima_hora": proxima_hora,
        "exercicios": [
            {"id": exercicio.id, "ordem": exercicio.ordem, "hora": exercicio.hora}
            for exercicio in exercicios_ordenados
        ],
    })


@router.post("/planos/{plano_id}/exercicios")
async def adicionar_exercicio(
    plano_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    bloco: str = Form("A"),
    bloco_id: str = Form(""),
    nome: str = Form(""),
    categoria: str = Form(""),
    hora: str = Form(""),
    minutos: str = Form(""),
    rpe: str = Form(""),
    organizacao: str = Form(""),
    coaching_points: str = Form(""),
    biblioteca_id: str = Form(""),
    origem_biblioteca: str = Form("novo"),
):
    resposta_json = "application/json" in request.headers.get("accept", "").lower()

    def responder_erro(mensagem: str, estado: int = 422):
        if resposta_json:
            return JSONResponse({"sucesso": False, "erro": mensagem}, status_code=estado)
        set_flash(request, mensagem, "error")
        return RedirectResponse(url=f"/treino/sessoes/{plano.sessao_id}", status_code=303)

    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, plano_id), db)
    plano = db.query(PlanoTreino).filter(PlanoTreino.id == plano_id).first()
    if not plano:
        if resposta_json:
            return JSONResponse({"sucesso": False, "erro": "Plano de treino não encontrado."}, status_code=404)
        return RedirectResponse(url="/equipas", status_code=303)

    try:
        rpe_exercicio = _normalizar_rpe(rpe)
        minutos_exercicio = _normalizar_minutos(minutos)
        bloco_dinamico_id = int(bloco_id) if bloco_id else None
        bloco = _normalizar_bloco(bloco) if not bloco_dinamico_id else None
    except ValueError as erro:
        return responder_erro(str(erro))

    total_no_bloco = db.query(ExercicioPlano).filter(
        ExercicioPlano.plano_id == plano_id,
        ExercicioPlano.bloco_id == bloco_dinamico_id if bloco_dinamico_id else ExercicioPlano.bloco == bloco
    ).count()

    biblioteca = None
    biblioteca_solicitada = bool((biblioteca_id or "").strip())
    copia_da_biblioteca = (origem_biblioteca or "").strip().lower() == "biblioteca"
    if biblioteca_solicitada:
        try:
            biblioteca = db.query(BibliotecoExercicio).filter(
                BibliotecoExercicio.id == int(biblioteca_id),
                BibliotecoExercicio.clube_id == plano.clube_id,
            ).first()
        except (TypeError, ValueError):
            biblioteca = None
        if not biblioteca:
            return responder_erro("O exercício selecionado já não está disponível na biblioteca.")
    elif copia_da_biblioteca:
        # Nunca guardar automaticamente um exercício se o formulário foi
        # marcado como cópia mas perdeu a referência à origem.
        return responder_erro("Seleciona novamente o exercício da biblioteca antes de o adicionar.")

    if biblioteca:
        # O formulário recebe uma cópia completa e pode adaptá-la, incluindo
        # limpar campos. Apenas o nome tem fallback para manter o registo válido.
        nome = (nome or "").strip() or biblioteca.nome

    if not (hora or "").strip():
        hora = _hora_sugerida_exercicio(plano.sessao, list(plano.exercicios)) or ""

    exercicio = ExercicioPlano(
        plano_id=plano_id,
        bloco=bloco,
        bloco_id=bloco_dinamico_id,
        ordem=total_no_bloco + 1,
        nome=nome or None,
        categoria=categoria or None,
        hora=hora or None,
        minutos=minutos_exercicio,
        rpe=rpe_exercicio,
        organizacao=organizacao or None,
        coaching_points=coaching_points or None
    )
    if biblioteca and biblioteca.desenho:
        exercicio.desenho_1 = biblioteca.desenho
    if biblioteca and biblioteca.desenho_campo_completo:
        exercicio.desenho_2 = biblioteca.desenho_campo_completo

    _marcar_sessao_como_alterada_manual(plano.sessao if plano else None)
    db.add(exercicio)

    nome_norm = nome.strip() if nome else None
    guardado_na_biblioteca = False
    nova_variante_da_biblioteca = bool(
        biblioteca
        and nome_norm
        and nome_norm.casefold() != (biblioteca.nome or "").strip().casefold()
    )
    # Um exercício criado de raiz entra uma vez na biblioteca. Uma cópia mantém
    # o original intacto; se receber outro título, passa a ser uma nova variante.
    if nome_norm and not biblioteca and not copia_da_biblioteca:
        existente = db.query(BibliotecoExercicio).filter(
            BibliotecoExercicio.clube_id == plano.clube_id,
            BibliotecoExercicio.nome.ilike(nome_norm),
        ).first()
        if not existente:
            db.add(BibliotecoExercicio(
                clube_id=plano.clube_id,
                nome=nome_norm,
                categoria=categoria or None,
                organizacao=organizacao or None,
                coaching_points=coaching_points or None,
            ))
            guardado_na_biblioteca = True
    elif nova_variante_da_biblioteca:
        db.add(BibliotecoExercicio(
            clube_id=plano.clube_id,
            nome=nome_norm,
            categoria=categoria or None,
            organizacao=organizacao or None,
            coaching_points=coaching_points or None,
            desenho=biblioteca.desenho,
            desenho_campo_completo=biblioteca.desenho_campo_completo,
        ))
        guardado_na_biblioteca = True

    db.flush()
    sincronizar_minutos_categorias(plano, db)
    db.commit()

    if nova_variante_da_biblioteca:
        mensagem = "Exercício adicionado ao plano e guardado como novo exercício na biblioteca."
    elif biblioteca_solicitada:
        mensagem = "Cópia adicionada ao plano. O exercício da biblioteca ficou inalterado."
    elif guardado_na_biblioteca:
        mensagem = "Exercício adicionado ao plano e guardado automaticamente na biblioteca."
    else:
        mensagem = "Exercício adicionado ao plano."

    if resposta_json:
        db.refresh(exercicio)
        exercicios_atualizados = db.query(ExercicioPlano).filter(
            ExercicioPlano.plano_id == plano.id
        ).all()
        return JSONResponse({
            "sucesso": True,
            "mensagem": mensagem,
            "exercicio_id": exercicio.id,
            "pagina_url": f"/treino/sessoes/{plano.sessao_id}",
            "proxima_hora": _hora_sugerida_exercicio(plano.sessao, exercicios_atualizados) or "",
        })

    set_flash(request, mensagem, "success")

    return RedirectResponse(url=f"/treino/sessoes/{plano.sessao_id}", status_code=303)


@router.post("/planos/{plano_id}/biblioteca/{biblioteca_id}")
async def adicionar_exercicio_da_biblioteca(
    plano_id: int,
    biblioteca_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    bloco: str = Form("A"),
    minutos: str = Form(""),
    hora: str = Form(""),
    rpe: str = Form(""),
):
    """Cria uma cópia editável de um exercício da biblioteca no plano."""
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, plano_id), db)
    plano = db.query(PlanoTreino).filter(PlanoTreino.id == plano_id).first()
    if not plano:
        return RedirectResponse(url="/equipas", status_code=303)
    biblioteca = db.query(BibliotecoExercicio).filter(
        BibliotecoExercicio.id == biblioteca_id,
        BibliotecoExercicio.clube_id == plano.clube_id,
    ).first()
    if not biblioteca:
        return RedirectResponse(url="/equipas", status_code=303)
    try:
        rpe_exercicio = _normalizar_rpe(rpe)
        minutos_exercicio = _normalizar_minutos(minutos)
        bloco = _normalizar_bloco(bloco)
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url=f"/treino/sessoes/{plano.sessao_id}", status_code=303)
    total_no_bloco = db.query(ExercicioPlano).filter(
        ExercicioPlano.plano_id == plano_id,
        ExercicioPlano.bloco == bloco,
    ).count()
    exercicio = ExercicioPlano(
        plano_id=plano_id,
        bloco=bloco,
        ordem=total_no_bloco + 1,
        hora=hora or None,
        minutos=minutos_exercicio,
        rpe=rpe_exercicio,
        nome=biblioteca.nome,
        categoria=biblioteca.categoria,
        desenho_1=biblioteca.desenho,
        desenho_2=biblioteca.desenho_campo_completo,
        organizacao=biblioteca.organizacao,
        coaching_points=biblioteca.coaching_points,
    )
    _marcar_sessao_como_alterada_manual(plano.sessao)
    db.add(exercicio)
    db.flush()
    sincronizar_minutos_categorias(plano, db)
    db.commit()
    set_flash(request, f"Exercício '{biblioteca.nome}' reutilizado no plano.")
    return RedirectResponse(url=f"/treino/sessoes/{plano.sessao_id}", status_code=303)


# ─────────────────────────────────────────
# APAGAR EXERCÍCIO
# URL: POST /treino/exercicios/{exercicio_id}/apagar
# ─────────────────────────────────────────
@router.post("/exercicios/{exercicio_id}/apagar")
async def apagar_exercicio(exercicio_id: int, request: Request, db: Session = Depends(get_db),
                           utilizador=Depends(exigir_autenticacao)):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_exercicio(db, exercicio_id), db)

    exercicio = db.query(ExercicioPlano).filter(ExercicioPlano.id == exercicio_id).first()

    if exercicio:
        sessao_id = exercicio.plano.sessao_id
        plano_id = exercicio.plano_id
        bloco = exercicio.bloco or "A"
        _marcar_sessao_como_alterada_manual(exercicio.plano.sessao)
        db.delete(exercicio)
        db.flush()
        sincronizar_minutos_categorias(exercicio.plano, db)
        _reordenar_exercicios_bloco(db, plano_id, bloco)
        db.commit()
        return RedirectResponse(url=f"/treino/sessoes/{sessao_id}", status_code=303)

    return RedirectResponse(url="/equipas")


@router.post("/exercicios/{exercicio_id}/duplicar")
async def duplicar_exercicio(exercicio_id: int, request: Request, db: Session = Depends(get_db),
                             utilizador=Depends(exigir_autenticacao)):
    """Duplica um exercício no mesmo bloco para acelerar a construção da sessão."""
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_exercicio(db, exercicio_id), db)
    exercicio = db.query(ExercicioPlano).filter(ExercicioPlano.id == exercicio_id).first()
    if not exercicio:
        return RedirectResponse(url="/equipas", status_code=303)

    bloco = exercicio.bloco or "A"
    total_no_bloco = db.query(ExercicioPlano).filter(
        ExercicioPlano.plano_id == exercicio.plano_id,
        ExercicioPlano.bloco == bloco,
    ).count()
    copia = ExercicioPlano(
        plano_id=exercicio.plano_id,
        bloco=bloco,
        ordem=total_no_bloco + 1,
        hora=exercicio.hora,
        minutos=exercicio.minutos,
        rpe=exercicio.rpe,
        nome=exercicio.nome,
        categoria=exercicio.categoria,
        desenho_1=exercicio.desenho_1,
        desenho_2=exercicio.desenho_2,
        desenho_3=exercicio.desenho_3,
        desenho_4=exercicio.desenho_4,
        desenhos_campos=exercicio.desenhos_campos,
        campos_ativos=exercicio.campos_ativos,
        organizacao=exercicio.organizacao,
        coaching_points=exercicio.coaching_points,
    )
    _marcar_sessao_como_alterada_manual(exercicio.plano.sessao)
    db.add(copia)
    db.flush()
    sincronizar_minutos_categorias(exercicio.plano, db)
    db.commit()
    set_flash(request, "Exercício duplicado no mesmo bloco.")
    return RedirectResponse(url=f"/treino/sessoes/{exercicio.plano.sessao_id}#bloco-{bloco}", status_code=303)


@router.post("/exercicios/{exercicio_id}/atualizar")
async def atualizar_exercicio(
    exercicio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    bloco: str = Form("A"),
    bloco_id: str = Form(""),
    nome: str = Form(""),
    categoria: str = Form(""),
    hora: str = Form(""),
    minutos: str = Form(""),
    rpe: str = Form(""),
    organizacao: str = Form(""),
    coaching_points: str = Form(""),
):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_exercicio(db, exercicio_id), db)

    exercicio = db.query(ExercicioPlano).filter(ExercicioPlano.id == exercicio_id).first()
    if not exercicio:
        return RedirectResponse(url="/equipas", status_code=303)

    bloco_anterior = exercicio.bloco or "A"
    bloco_novo = bloco or bloco_anterior
    bloco_dinamico_id = int(bloco_id) if bloco_id else exercicio.bloco_id

    try:
        exercicio.rpe = _normalizar_rpe(rpe)
        exercicio.minutos = _normalizar_minutos(minutos)
        bloco_novo = _normalizar_bloco(bloco) if not bloco_dinamico_id else bloco_anterior
    except ValueError as erro:
        set_flash(request, str(erro), "error")
        return RedirectResponse(url=f"/treino/sessoes/{exercicio.plano.sessao_id}", status_code=303)

    exercicio.nome = nome or None
    exercicio.categoria = categoria or None
    exercicio.hora = hora or None
    exercicio.organizacao = organizacao or None
    exercicio.coaching_points = coaching_points or None

    if bloco_dinamico_id != exercicio.bloco_id:
        exercicio.bloco_id = bloco_dinamico_id
        exercicio.bloco = None
        exercicio.ordem = db.query(ExercicioPlano).filter(ExercicioPlano.plano_id == exercicio.plano_id, ExercicioPlano.bloco_id == bloco_dinamico_id, ExercicioPlano.id != exercicio.id).count() + 1
    elif bloco_novo != bloco_anterior:
        exercicio.bloco = bloco_novo
        exercicio.ordem = (
            db.query(ExercicioPlano)
            .filter(
                ExercicioPlano.plano_id == exercicio.plano_id,
                ExercicioPlano.bloco == bloco_novo,
                ExercicioPlano.id != exercicio.id,
            )
            .count()
            + 1
        )

    _marcar_sessao_como_alterada_manual(exercicio.plano.sessao)
    db.flush()
    sincronizar_minutos_categorias(exercicio.plano, db)
    db.commit()

    if bloco_novo != bloco_anterior:
        _reordenar_exercicios_bloco(db, exercicio.plano_id, bloco_anterior)
        _reordenar_exercicios_bloco(db, exercicio.plano_id, bloco_novo)
        db.commit()

    return RedirectResponse(url=f"/treino/sessoes/{exercicio.plano.sessao_id}", status_code=303)


@router.post("/exercicios/{exercicio_id}/notas")
async def atualizar_notas_exercicio(
    exercicio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    organizacao: str = Form(""),
    coaching_points: str = Form(""),
):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_exercicio(db, exercicio_id), db)
    exercicio = db.query(ExercicioPlano).filter(ExercicioPlano.id == exercicio_id).first()
    if not exercicio:
        return JSONResponse({"sucesso": False, "erro": "Exercício não encontrado"}, status_code=404)

    exercicio.organizacao = organizacao.strip() or None
    exercicio.coaching_points = coaching_points.strip() or None
    _marcar_sessao_como_alterada_manual(exercicio.plano.sessao)
    db.commit()
    return JSONResponse({
        "sucesso": True,
        "organizacao": exercicio.organizacao or "",
        "coaching_points": exercicio.coaching_points or "",
    })


# ─────────────────────────────────────────
# GUARDAR REFLEXÃO DO PLANO
# URL: POST /treino/planos/{plano_id}/reflexao
# ─────────────────────────────────────────
@router.post("/planos/{plano_id}/reflexao")
async def guardar_reflexao(
    plano_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    reflexao: str = Form("")
):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_plano(db, plano_id), db)

    plano = db.query(PlanoTreino).filter(PlanoTreino.id == plano_id).first()
    if plano:
        _marcar_sessao_como_alterada_manual(plano.sessao)
        plano.reflexao = reflexao or None
        if reflexao.strip() and normalizar_estado_sessao(plano.sessao.estado) == "executada":
            plano.sessao.estado = "registada"
        db.commit()

    return RedirectResponse(url=f"/treino/sessoes/{plano.sessao_id}", status_code=303)


# ─────────────────────────────────────────
# GUARDAR DESENHO DE UM EXERCÍCIO
# URL: POST /treino/exercicios/{exercicio_id}/desenho
# ─────────────────────────────────────────
@router.post("/exercicios/{exercicio_id}/desenho")
async def guardar_desenho(exercicio_id: int, request: Request, db: Session = Depends(get_db),
                          utilizador=Depends(exigir_autenticacao)):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_exercicio(db, exercicio_id), db)

    dados = await request.json()
    try:
        numero = int(dados.get("numero"))
    except (TypeError, ValueError):
        numero = 0
    desenho_guardado = empacotar_desenho_editavel(dados.get("dados"), dados.get("estado"))

    exercicio = db.query(ExercicioPlano).filter(ExercicioPlano.id == exercicio_id).first()

    if not exercicio:
        return JSONResponse({"sucesso": False, "erro": "Exercício não encontrado"})

    if numero <= 0:
        return JSONResponse({"sucesso": False, "erro": "Campo inválido"}, status_code=422)

    if not desenho_guardado:
        return JSONResponse({"sucesso": False, "erro": "O desenho enviado não é válido."}, status_code=400)

    _definir_desenho_campo(exercicio, numero, desenho_guardado)
    slots = _slots_ativos(exercicio)
    if numero not in slots:
        slots.append(numero)
        _definir_slots_ativos(exercicio, slots)

    _marcar_sessao_como_alterada_manual(exercicio.plano.sessao)
    db.commit()
    return JSONResponse({"sucesso": True})


@router.post("/exercicios/{exercicio_id}/campos")
async def adicionar_campo_exercicio(
    exercicio_id: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
    tipo: str = Form(...),
):
    resposta_json = "application/json" in request.headers.get("accept", "").lower()
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_exercicio(db, exercicio_id), db)
    exercicio = db.query(ExercicioPlano).filter(ExercicioPlano.id == exercicio_id).first()
    if not exercicio:
        if resposta_json:
            return JSONResponse({"sucesso": False, "erro": "Exercício não encontrado."}, status_code=404)
        return RedirectResponse(url="/equipas", status_code=303)
    if tipo not in IMAGENS_CAMPO:
        if resposta_json:
            return JSONResponse({"sucesso": False, "erro": "Tipo de campo inválido."}, status_code=422)
        set_flash(request, "Tipo de campo inválido.", "error")
        return RedirectResponse(url=f"/treino/sessoes/{exercicio.plano.sessao_id}#exercicio-{exercicio.id}", status_code=303)
    slots = _slots_ativos(exercicio)
    disponivel = _proximo_numero_campo(tipo, slots)
    slots.append(disponivel)
    _definir_slots_ativos(exercicio, slots)
    _marcar_sessao_como_alterada_manual(exercicio.plano.sessao)
    db.commit()
    if resposta_json:
        tipo_campo, label, imagem = _configuracao_campo(disponivel)
        return JSONResponse({
            "sucesso": True,
            "campo": {
                "numero": disponivel,
                "tipo": tipo_campo,
                "label": label,
                "imagem": imagem,
            },
        })
    set_flash(request, "Campo acrescentado ao exercício.")
    return RedirectResponse(url=f"/treino/sessoes/{exercicio.plano.sessao_id}#exercicio-{exercicio.id}", status_code=303)


@router.post("/exercicios/{exercicio_id}/campos/{numero}/apagar")
async def apagar_campo_exercicio(
    exercicio_id: int,
    numero: int,
    request: Request,
    db: Session = Depends(get_db),
    utilizador=Depends(exigir_autenticacao),
):
    resposta_json = "application/json" in request.headers.get("accept", "").lower()
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_exercicio(db, exercicio_id), db)
    exercicio = db.query(ExercicioPlano).filter(ExercicioPlano.id == exercicio_id).first()
    if not exercicio or numero <= 0:
        if resposta_json:
            return JSONResponse({"sucesso": False, "erro": "Campo ou exercício inválido."}, status_code=404)
        return RedirectResponse(url="/equipas", status_code=303)
    if numero not in _slots_ativos(exercicio):
        if resposta_json:
            return JSONResponse({"sucesso": False, "erro": "O campo já não existe."}, status_code=404)
        set_flash(request, "O campo já não existe.", "error")
        return RedirectResponse(url=f"/treino/sessoes/{exercicio.plano.sessao_id}#exercicio-{exercicio.id}", status_code=303)
    _definir_slots_ativos(exercicio, [slot for slot in _slots_ativos(exercicio) if slot != numero])
    _definir_desenho_campo(exercicio, numero, None)
    _marcar_sessao_como_alterada_manual(exercicio.plano.sessao)
    db.commit()
    if resposta_json:
        return JSONResponse({"sucesso": True, "numero": numero})
    set_flash(request, "Campo removido sem afetar os restantes.")
    return RedirectResponse(url=f"/treino/sessoes/{exercicio.plano.sessao_id}#exercicio-{exercicio.id}", status_code=303)


# ─────────────────────────────────────────
# VERSÃO DE IMPRESSÃO DO PLANO DE TREINO
# URL: GET /treino/sessoes/{sessao_id}/print
# ─────────────────────────────────────────
@router.get("/sessoes/{sessao_id}/print", response_class=HTMLResponse)
def imprimir_plano_treino(sessao_id: int, request: Request, db: Session = Depends(get_db),
                          utilizador=Depends(exigir_autenticacao)):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_sessao(db, sessao_id), db)

    sessao = db.query(SessaoTreino).filter(SessaoTreino.id == sessao_id).first()
    if not sessao:
        return RedirectResponse(url="/equipas")
    sessao = enriquecer_sessao_para_ui(sessao)

    equipa = sessao.microciclo.mesociclo.macrociclo.equipa
    plano = db.query(PlanoTreino).filter(PlanoTreino.sessao_id == sessao_id).first()

    return templates.TemplateResponse(
        request,
        "treino/plano_print.html",
        _contexto_impressao_plano(request, sessao, equipa, plano, utilizador, db),
    )


# ─────────────────────────────────────────
# EXPORTAR PDF DO PLANO DE TREINO
# URL: GET /treino/sessoes/{sessao_id}/pdf
# ─────────────────────────────────────────
@router.get("/sessoes/{sessao_id}/pdf")
def exportar_pdf_plano(sessao_id: int, request: Request, db: Session = Depends(get_db),
                       utilizador=Depends(exigir_autenticacao)):
    _verificar_acesso_treino(utilizador, _obter_equipa_id_por_sessao(db, sessao_id), db)

    sessao = db.query(SessaoTreino).filter(SessaoTreino.id == sessao_id).first()
    if not sessao:
        return RedirectResponse(url="/equipas")
    sessao = enriquecer_sessao_para_ui(sessao)

    equipa = sessao.microciclo.mesociclo.macrociclo.equipa
    plano = db.query(PlanoTreino).filter(PlanoTreino.sessao_id == sessao_id).first()

    contexto_pdf = _contexto_impressao_plano(request, sessao, equipa, plano, utilizador, db)
    contexto_pdf["modo_pdf"] = True
    pdf = renderizar_pdf(request, "treino/plano_print.html", contexto_pdf)

    tipo_treino = "Treino físico" if (getattr(sessao, "tipo_treino", None) or "normal") == "fisico" else "Treino"
    nome = f"{tipo_treino} {sessao.numero_treino}" if sessao.numero_treino is not None else tipo_treino
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition_pdf(nome)}
    )
