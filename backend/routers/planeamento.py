# ─────────────────────────────────────────────────────────────
# ROUTER DE PLANEAMENTO
# Este ficheiro gere todas as rotas relacionadas com o
# planeamento desportivo: macrociclos, mesociclos e microciclos
# ─────────────────────────────────────────────────────────────

# APIRouter permite criar um conjunto de rotas separado do main.py
# Isto chama-se "separação de responsabilidades" — cada ficheiro
# trata de um tema específico
from fastapi import APIRouter, Request, Depends, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

# Importamos a função get_db que abre e fecha sessões com a BD
from database import get_db

# Importamos os modelos que vamos precisar
from models.planeamento import Macrociclo, Mesociclo, Microciclo
from models.equipa import Equipa

# prefix="/planeamento" significa que todas as rotas deste router
# começam com /planeamento — ex: /planeamento/macrociclos
router = APIRouter(prefix="/planeamento")

# Jinja2Templates aponta para a pasta onde estão os ficheiros HTML
templates = Jinja2Templates(directory="../frontend/templates")


# ─────────────────────────────────────────
# FUNÇÃO AUXILIAR — obter utilizador actual
# Esta função é repetida em todos os routers.
# Mais à frente podemos centralizá-la, mas por
# agora mantemos simples e legível.
# ─────────────────────────────────────────
def obter_utilizador_atual(request: Request, db: Session):
    # verificar_token é importado aqui dentro para evitar
    # importações circulares entre ficheiros
    from auth import verificar_token
    from models.utilizador import Utilizador

    # request.session é um dicionário gerido pelo SessionMiddleware
    # Guardámos o token aqui quando o utilizador fez login
    token = request.session.get("token")
    if not token:
        return None  # Sem token = não autenticado

    # jwt.decode verifica a assinatura e a validade do token
    payload = verificar_token(token)
    if not payload:
        return None  # Token inválido ou expirado

    # Procura o utilizador na BD pelo username que está dentro do token
    # .first() devolve o primeiro resultado ou None se não encontrar
    return db.query(Utilizador).filter(
        Utilizador.username == payload.get("sub")
    ).first()


# ─────────────────────────────────────────
# LISTA DE MACROCICLOS DE UMA EQUIPA
# URL: GET /planeamento/equipas/{equipa_id}/macrociclos
# ─────────────────────────────────────────
@router.get("/equipas/{equipa_id}/macrociclos", response_class=HTMLResponse)
def listar_macrociclos(equipa_id: int, request: Request, db: Session = Depends(get_db)):
    # Depends(get_db) é injecção de dependências do FastAPI
    # O FastAPI cria automaticamente uma sessão BD e passa-a como argumento
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        # Se não estiver autenticado, redireciona para o login
        return RedirectResponse(url="/login")

    # Procura a equipa pelo ID que vem na URL
    # filter() filtra os resultados — equivale a WHERE em SQL
    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas")

    # Procura todos os macrociclos desta equipa
    # order_by ordena pelo número do macro (1, 2, 3...)
    macrociclos = db.query(Macrociclo).filter(
        Macrociclo.equipa_id == equipa_id
    ).order_by(Macrociclo.numero).all()

    # Renderiza o template HTML passando os dados como variáveis
    return templates.TemplateResponse(request, "planeamento/macrociclos/lista.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "macrociclos": macrociclos
    })


# ─────────────────────────────────────────
# FORMULÁRIO DE CRIAR MACROCICLO
# URL: GET /planeamento/equipas/{equipa_id}/macrociclos/novo
# ─────────────────────────────────────────
@router.get("/equipas/{equipa_id}/macrociclos/novo", response_class=HTMLResponse)
def form_novo_macrociclo(equipa_id: int, request: Request, db: Session = Depends(get_db)):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    equipa = db.query(Equipa).filter(Equipa.id == equipa_id).first()
    if not equipa:
        return RedirectResponse(url="/equipas")

    # Conta quantos macrociclos já existem para esta equipa
    # .count() devolve um número inteiro em vez de uma lista
    total_macros = db.query(Macrociclo).filter(
        Macrociclo.equipa_id == equipa_id
    ).count()

    # O número do novo macro é o total actual + 1
    # Ex: se já existem 2 macros, o novo é o número 3
    proximo_numero = total_macros + 1

    return templates.TemplateResponse(request, "planeamento/macrociclos/form.html", {
        "utilizador": utilizador,
        "equipa": equipa,
        "proximo_numero": proximo_numero
    })


# ─────────────────────────────────────────
# CRIAR MACROCICLO
# URL: POST /planeamento/equipas/{equipa_id}/macrociclos/novo
# ─────────────────────────────────────────
@router.post("/equipas/{equipa_id}/macrociclos/novo")
async def criar_macrociclo(
    equipa_id: int,
    request: Request,
    db: Session = Depends(get_db),
    # Form(...) indica que este valor vem de um formulário HTML
    # O ... significa que o campo é obrigatório
    data_inicio: str = Form(...),
    data_fim: str = Form(...),
    obj_tecnica_individual_ofensiva: str = Form(""),
    obj_tecnica_individual_defensiva: str = Form(""),
    obj_tatica_individual_ofensiva: str = Form(""),
    obj_tatica_individual_defensiva: str = Form(""),
    obj_tatica_coletiva_ofensiva: str = Form(""),
    obj_tatica_coletiva_defensiva: str = Form(""),
    obj_fisicos: str = Form(""),
    obj_psicologicos: str = Form("")
):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    # Calcula o número do novo macro automaticamente
    total_macros = db.query(Macrociclo).filter(
        Macrociclo.equipa_id == equipa_id
    ).count()

    # date.fromisoformat converte uma string "2024-09-01" para um objecto date do Python
    from datetime import date
    macrociclo = Macrociclo(
        numero=total_macros + 1,
        data_inicio=date.fromisoformat(data_inicio),
        data_fim=date.fromisoformat(data_fim),
        # if campo else None — se o campo estiver vazio, guarda None em vez de string vazia
        obj_tecnica_individual_ofensiva=obj_tecnica_individual_ofensiva or None,
        obj_tecnica_individual_defensiva=obj_tecnica_individual_defensiva or None,
        obj_tatica_individual_ofensiva=obj_tatica_individual_ofensiva or None,
        obj_tatica_individual_defensiva=obj_tatica_individual_defensiva or None,
        obj_tatica_coletiva_ofensiva=obj_tatica_coletiva_ofensiva or None,
        obj_tatica_coletiva_defensiva=obj_tatica_coletiva_defensiva or None,
        obj_fisicos=obj_fisicos or None,
        obj_psicologicos=obj_psicologicos or None,
        equipa_id=equipa_id
    )

    # db.add() prepara o objecto para ser inserido na BD
    db.add(macrociclo)
    # db.commit() confirma a transacção — só aqui os dados são realmente guardados
    db.commit()

    # Redireciona para a lista de macrociclos da equipa
    # status_code=303 é o código HTTP correcto após um POST bem sucedido
    return RedirectResponse(
        url=f"/planeamento/equipas/{equipa_id}/macrociclos",
        status_code=303
    )


# ─────────────────────────────────────────
# DETALHE DE UM MACROCICLO
# URL: GET /planeamento/macrociclos/{macro_id}
# ─────────────────────────────────────────
@router.get("/macrociclos/{macro_id}", response_class=HTMLResponse)
def detalhe_macrociclo(macro_id: int, request: Request, db: Session = Depends(get_db)):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    macrociclo = db.query(Macrociclo).filter(Macrociclo.id == macro_id).first()
    if not macrociclo:
        return RedirectResponse(url="/equipas")

    # Procura os mesociclos deste macrociclo ordenados pelo número
    mesociclos = db.query(Mesociclo).filter(
        Mesociclo.macrociclo_id == macro_id
    ).order_by(Mesociclo.numero).all()

    # Calcula o próximo número de mesociclo
    proximo_numero_meso = len(mesociclos) + 1

    return templates.TemplateResponse(request, "planeamento/macrociclos/detalhe.html", {
        "utilizador": utilizador,
        "macrociclo": macrociclo,
        "mesociclos": mesociclos,
        "proximo_numero_meso": proximo_numero_meso
    })


# ─────────────────────────────────────────
# CRIAR MESOCICLO
# URL: POST /planeamento/macrociclos/{macro_id}/mesociclos/novo
# ─────────────────────────────────────────
@router.post("/macrociclos/{macro_id}/mesociclos/novo")
async def criar_mesociclo(
    macro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    data_inicio: str = Form(...),
    data_fim: str = Form(...),
    obj_tecnica_individual_ofensiva: str = Form(""),
    obj_tecnica_individual_defensiva: str = Form(""),
    obj_tatica_individual_ofensiva: str = Form(""),
    obj_tatica_individual_defensiva: str = Form(""),
    obj_tatica_coletiva_ofensiva: str = Form(""),
    obj_tatica_coletiva_defensiva: str = Form(""),
    obj_fisicos: str = Form(""),
    obj_psicologicos: str = Form("")
):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    # Conta os mesociclos existentes neste macrociclo
    total_mesos = db.query(Mesociclo).filter(
        Mesociclo.macrociclo_id == macro_id
    ).count()

    from datetime import date
    mesociclo = Mesociclo(
        numero=total_mesos + 1,
        data_inicio=date.fromisoformat(data_inicio),
        data_fim=date.fromisoformat(data_fim),
        obj_tecnica_individual_ofensiva=obj_tecnica_individual_ofensiva or None,
        obj_tecnica_individual_defensiva=obj_tecnica_individual_defensiva or None,
        obj_tatica_individual_ofensiva=obj_tatica_individual_ofensiva or None,
        obj_tatica_individual_defensiva=obj_tatica_individual_defensiva or None,
        obj_tatica_coletiva_ofensiva=obj_tatica_coletiva_ofensiva or None,
        obj_tatica_coletiva_defensiva=obj_tatica_coletiva_defensiva or None,
        obj_fisicos=obj_fisicos or None,
        obj_psicologicos=obj_psicologicos or None,
        macrociclo_id=macro_id
    )

    db.add(mesociclo)
    db.commit()

    return RedirectResponse(
        url=f"/planeamento/macrociclos/{macro_id}",
        status_code=303
    )


# ─────────────────────────────────────────
# DETALHE DE UM MESOCICLO
# URL: GET /planeamento/mesociclos/{meso_id}
# ─────────────────────────────────────────
@router.get("/mesociclos/{meso_id}", response_class=HTMLResponse)
def detalhe_mesociclo(meso_id: int, request: Request, db: Session = Depends(get_db)):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    mesociclo = db.query(Mesociclo).filter(Mesociclo.id == meso_id).first()
    if not mesociclo:
        return RedirectResponse(url="/equipas")

    # Procura os microciclos deste mesociclo
    microciclos = db.query(Microciclo).filter(
        Microciclo.mesociclo_id == meso_id
    ).order_by(Microciclo.numero).all()

    proximo_numero_micro = len(microciclos) + 1

    return templates.TemplateResponse(request, "planeamento/mesociclos/detalhe.html", {
        "utilizador": utilizador,
        "mesociclo": mesociclo,
        "microciclos": microciclos,
        "proximo_numero_micro": proximo_numero_micro
    })


# ─────────────────────────────────────────
# CRIAR MICROCICLO
# URL: POST /planeamento/mesociclos/{meso_id}/microciclos/novo
# ─────────────────────────────────────────
@router.post("/mesociclos/{meso_id}/microciclos/novo")
async def criar_microciclo(
    meso_id: int,
    request: Request,
    db: Session = Depends(get_db),
    data_inicio: str = Form(...),
    data_fim: str = Form(...),
    tipo: str = Form(""),
    obj_tecnica_individual_ofensiva: str = Form(""),
    obj_tecnica_individual_defensiva: str = Form(""),
    obj_tatica_individual_ofensiva: str = Form(""),
    obj_tatica_individual_defensiva: str = Form(""),
    obj_tatica_coletiva_ofensiva: str = Form(""),
    obj_tatica_coletiva_defensiva: str = Form(""),
    obj_fisicos: str = Form(""),
    obj_psicologicos: str = Form("")
):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    total_micros = db.query(Microciclo).filter(
        Microciclo.mesociclo_id == meso_id
    ).count()

    from datetime import date
    microciclo = Microciclo(
        numero=total_micros + 1,
        data_inicio=date.fromisoformat(data_inicio),
        data_fim=date.fromisoformat(data_fim),
        tipo=tipo or None,
        obj_tecnica_individual_ofensiva=obj_tecnica_individual_ofensiva or None,
        obj_tecnica_individual_defensiva=obj_tecnica_individual_defensiva or None,
        obj_tatica_individual_ofensiva=obj_tatica_individual_ofensiva or None,
        obj_tatica_individual_defensiva=obj_tatica_individual_defensiva or None,
        obj_tatica_coletiva_ofensiva=obj_tatica_coletiva_ofensiva or None,
        obj_tatica_coletiva_defensiva=obj_tatica_coletiva_defensiva or None,
        obj_fisicos=obj_fisicos or None,
        obj_psicologicos=obj_psicologicos or None,
        mesociclo_id=meso_id
    )

    db.add(microciclo)
    db.commit()

    return RedirectResponse(
        url=f"/planeamento/mesociclos/{meso_id}",
        status_code=303
    )


# ─────────────────────────────────────────
# DETALHE DE UM MICROCICLO
# URL: GET /planeamento/microciclos/{micro_id}
# ─────────────────────────────────────────
@router.get("/microciclos/{micro_id}", response_class=HTMLResponse)
def detalhe_microciclo(micro_id: int, request: Request, db: Session = Depends(get_db)):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    microciclo = db.query(Microciclo).filter(Microciclo.id == micro_id).first()
    if not microciclo:
        return RedirectResponse(url="/equipas")

    from models.planeamento import SessaoTreino
    sessoes = db.query(SessaoTreino).filter(
        SessaoTreino.microciclo_id == micro_id
    ).order_by(SessaoTreino.data).all()

    # ─────────────────────────────────────────
    # CÁLCULO DO QUADRO DE BALANÇO
    # Todos os valores são calculados automaticamente
    # a partir das sessões inseridas
    # ─────────────────────────────────────────

    # Separa treinos de jogos usando list comprehension
    # [x for x in lista if condição] — filtra uma lista em Python
    treinos = [s for s in sessoes if not s.e_jogo]
    jogos = [s for s in sessoes if s.e_jogo]

    # Calcula o volume total somando os minutos de todos os treinos
    # sum() soma uma lista de valores
    # s.volume_minutos or 0 — se for None usa 0
    volume_total = sum(s.volume_minutos or 0 for s in treinos)

    # Calcula a média de RPE dos treinos
    # Filtra só os treinos que têm RPE definido
    rpes_validos = [s.intensidade_rpe for s in treinos if s.intensidade_rpe]
    media_rpe = round(sum(rpes_validos) / len(rpes_validos), 1) if rpes_validos else 0

    # Calcula o tempo total por componente somando todas as sessões
    # Usamos um dicionário para organizar os dados
    componentes = {
        "TIO": sum(s.min_tecnica_individual_ofensiva or 0 for s in treinos),
        "TID": sum(s.min_tecnica_individual_defensiva or 0 for s in treinos),
        "TaIO": sum(s.min_tatica_individual_ofensiva or 0 for s in treinos),
        "TaID": sum(s.min_tatica_individual_defensiva or 0 for s in treinos),
        "TCO": sum(s.min_tatica_coletiva_ofensiva or 0 for s in treinos),
        "TCD": sum(s.min_tatica_coletiva_defensiva or 0 for s in treinos),
        "FÍS": sum(s.min_fisicos or 0 for s in treinos),
    }

    # Agrupa todos os dados do balanço num dicionário
    balanço = {
        "treinos_previstos": len(treinos),
        "treinos_realizados": len(treinos),
        "jogos_previstos": len(jogos),
        "jogos_realizados": len(jogos),
        "volume_total": volume_total,
        "media_rpe": media_rpe,
        "componentes": componentes
    }

    # Dados para os gráficos — convertidos para JSON
    dados_graficos = {
        "labels": [s.data.isoformat() if s.data else "" for s in sessoes],
        "volumes": [s.volume_minutos if s.volume_minutos else 0 for s in sessoes],
        "rpes": [float(s.intensidade_rpe) if s.intensidade_rpe else 0 for s in sessoes]
    }

    return templates.TemplateResponse(request, "planeamento/microciclos/detalhe.html", {
        "utilizador": utilizador,
        "microciclo": microciclo,
        "sessoes": sessoes,
        "dados_graficos": dados_graficos,
        # Passamos o balanço para o template
        "balanco": balanço
    })
# ─────────────────────────────────────────
# CRIAR SESSÃO DE TREINO
# URL: POST /planeamento/microciclos/{micro_id}/sessoes/nova
# ─────────────────────────────────────────
@router.post("/microciclos/{micro_id}/sessoes/nova")
async def criar_sessao(
    micro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    data: str = Form(...),
    local: str = Form(""),
    volume_minutos: str = Form(""),
    intensidade_rpe: str = Form(""),
    # O checkbox envia "true" se marcado, nada se não marcado
    # Por isso usamos Form("") e verificamos se tem valor
    e_jogo: str = Form("")
):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    # Importamos SessaoTreino aqui para evitar importações desnecessárias no topo
    from models.planeamento import SessaoTreino

    # Conta o número de treinos já existentes neste microciclo
    # (não conta jogos — só treinos)
    total_treinos = db.query(SessaoTreino).filter(
        SessaoTreino.microciclo_id == micro_id,
        # == False verifica se o campo é False na BD
        SessaoTreino.e_jogo == False
    ).count()

    from datetime import date
    sessao = SessaoTreino(
        data=date.fromisoformat(data),
        local=local or None,
        # int(x) if x else None — converte para inteiro só se não estiver vazio
        volume_minutos=int(volume_minutos) if volume_minutos else None,
        # float(x) permite decimais — RPE pode ser 6.5, por exemplo
        intensidade_rpe=float(intensidade_rpe) if intensidade_rpe else None,
        # Se o checkbox foi marcado, e_jogo é "true", caso contrário é ""
        e_jogo=e_jogo == "true",
        # O número do treino só incrementa para treinos, não para jogos
        numero_treino=None if e_jogo == "true" else total_treinos + 1,
        microciclo_id=micro_id
    )

    db.add(sessao)
    db.commit()

    return RedirectResponse(
        url=f"/planeamento/microciclos/{micro_id}",
        status_code=303
    )

# ─────────────────────────────────────────
# GUARDAR REFLEXÃO DO MICROCICLO
# URL: POST /planeamento/microciclos/{micro_id}/reflexao
# ─────────────────────────────────────────
@router.post("/microciclos/{micro_id}/reflexao")
async def guardar_reflexao_microciclo(
    micro_id: int,
    request: Request,
    db: Session = Depends(get_db),
    reflexao: str = Form("")
):
    utilizador = obter_utilizador_atual(request, db)
    if not utilizador:
        return RedirectResponse(url="/login")

    # Procura o microciclo na base de dados
    microciclo = db.query(Microciclo).filter(Microciclo.id == micro_id).first()
    if not microciclo:
        return RedirectResponse(url="/equipas")

    # Actualiza apenas o campo reflexao
    # Não precisamos de criar um novo objecto — modificamos o existente
    microciclo.reflexao = reflexao or None

    # db.commit() guarda as alterações na base de dados
    db.commit()

    return RedirectResponse(
        url=f"/planeamento/microciclos/{micro_id}",
        status_code=303
    )