import io
import math
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from services.imagem_playbook_service import preparar_imagem_passo


MAX_FICHEIRO_EBP_BYTES = 10 * 1024 * 1024
MAX_CONTEUDO_EBP_BYTES = 6 * 1024 * 1024
MAX_SEQUENCIAS = 100
MAX_GRAFICOS_POR_SEQUENCIA = 500
# O Basketball Playbook guarda os elementos numa prancha maior do que o campo
# visivel. Estes limites correspondem exatamente a essa area util.
COORDENADA_X_MIN = 500
COORDENADA_X_MAX = 6850
COORDENADA_Y_MIN = 1650
COORDENADA_Y_MAX = 7150
TAMANHO_IMAGEM = (1400, 1225)
MARGEM_CAMPO = (28, 36, 1372, 1189)


@dataclass(frozen=True)
class GraficoEbp:
    tipo: str
    numero: int
    x1: int
    y1: int
    x2: int
    y2: int
    espessura: int
    rotacao: int
    seta: int
    cor: int
    cor_secundaria: int
    etiqueta: int
    nivel: int
    texto: str = ""


@dataclass(frozen=True)
class SequenciaEbp:
    texto: str
    graficos: tuple[GraficoEbp, ...]


@dataclass(frozen=True)
class JogadaEbp:
    nome: str
    categoria_origem: str
    descricao: str
    sequencias: tuple[SequenciaEbp, ...]


def _inteiro(valor: str | None, predefinido: int = 0) -> int:
    try:
        return int((valor or "").strip())
    except (TypeError, ValueError):
        return predefinido


def _campos(bloco: str) -> dict[str, str]:
    resultado: dict[str, str] = {}
    for linha in bloco.splitlines():
        if "=" not in linha:
            continue
        chave, valor = linha.split("=", 1)
        resultado[chave.strip().lower()] = valor.strip()
    return resultado


def _extrair_texto(conteudo: bytes) -> str:
    if not conteudo:
        raise ValueError("O ficheiro EBP está vazio.")
    if len(conteudo) > MAX_FICHEIRO_EBP_BYTES:
        raise ValueError("O ficheiro EBP não pode ultrapassar 10 MB.")

    if conteudo.startswith(b"Version"):
        dados = conteudo
    else:
        # Basketball Playbook troca os três primeiros bytes do cabeçalho ZIP por EBP.
        if not conteudo.startswith(b"EBP\x04"):
            raise ValueError("O ficheiro não tem um formato EBP reconhecido.")
        arquivo = b"PK\x03" + conteudo[3:]
        try:
            with zipfile.ZipFile(io.BytesIO(arquivo)) as zip_ebp:
                membros = [item for item in zip_ebp.infolist() if Path(item.filename).name.lower() == "playbook.ebp"]
                if len(membros) != 1:
                    raise ValueError("O ficheiro EBP não contém um playbook válido.")
                membro = membros[0]
                if membro.file_size > MAX_CONTEUDO_EBP_BYTES:
                    raise ValueError("O conteúdo do ficheiro EBP é demasiado grande.")
                if membro.compress_size and membro.file_size / membro.compress_size > 200:
                    raise ValueError("O ficheiro EBP tem uma compressão inválida.")
                dados = zip_ebp.read(membro)
        except (zipfile.BadZipFile, RuntimeError, OSError) as erro:
            raise ValueError("Não foi possível abrir o ficheiro EBP.") from erro

    for codificacao in ("utf-8-sig", "cp1252"):
        try:
            return dados.decode(codificacao)
        except UnicodeDecodeError:
            continue
    raise ValueError("O texto interno do ficheiro EBP não é válido.")


def interpretar_ebp(conteudo: bytes) -> JogadaEbp:
    texto = _extrair_texto(conteudo)
    if "Basketball Playbook" not in texto[:160]:
        raise ValueError("Esta versão do ficheiro EBP ainda não é suportada.")

    marcadores = list(re.finditer(r"(?mi)^Nr_parts\s*=\s*(\d+)\s*$", texto))
    if not marcadores:
        raise ValueError("O ficheiro EBP não contém passos importáveis.")
    if len(marcadores) > MAX_SEQUENCIAS:
        raise ValueError("O ficheiro EBP contém demasiados passos.")

    cabecalho = _campos(texto[:marcadores[0].start()])
    nome = (cabecalho.get("playname") or "Jogada importada").strip()[:180]
    categoria_origem = (cabecalho.get("category") or "").strip()[:120]
    introducao = (cabecalho.get("intro") or "").strip()
    descricao = introducao or (f"Categoria de origem: {categoria_origem}" if categoria_origem else "")

    sequencias: list[SequenciaEbp] = []
    for indice, marcador in enumerate(marcadores):
        quantidade = _inteiro(marcador.group(1))
        if quantidade < 1 or quantidade > MAX_GRAFICOS_POR_SEQUENCIA:
            raise ValueError("Um dos passos do ficheiro EBP tem uma estrutura inválida.")
        fim = marcadores[indice + 1].start() if indice + 1 < len(marcadores) else len(texto)
        bloco = texto[marcador.end():fim]
        blocos_graficos = re.split(r"(?mi)(?=^Graphicnr\s*=)", bloco)
        graficos: list[GraficoEbp] = []
        for bloco_grafico in blocos_graficos:
            dados = _campos(bloco_grafico)
            if "graphicnr" not in dados or "type" not in dados:
                continue
            graficos.append(GraficoEbp(
                tipo=dados["type"].strip().lower(),
                numero=_inteiro(dados.get("graphicnr")),
                x1=_inteiro(dados.get("x1")),
                y1=_inteiro(dados.get("y1")),
                x2=_inteiro(dados.get("x2")),
                y2=_inteiro(dados.get("y2")),
                espessura=_inteiro(dados.get("thickness"), 1),
                rotacao=_inteiro(dados.get("rotation")),
                seta=_inteiro(dados.get("arrow")),
                cor=_inteiro(dados.get("color")),
                cor_secundaria=_inteiro(dados.get("color2")),
                etiqueta=_inteiro(dados.get("tagnr")),
                nivel=_inteiro(dados.get("level")),
                texto=(dados.get("playtext") or "").strip()[:200],
            ))
            if len(graficos) == quantidade:
                break
        if not graficos:
            raise ValueError("Um dos passos do ficheiro EBP não contém elementos gráficos.")

        prefixo_inicio = marcadores[indice - 1].end() if indice else 0
        prefixo = texto[prefixo_inicio:marcador.start()]
        textos = re.findall(r"(?mi)^Text\s*=\s*(.*)$", prefixo)
        sequencias.append(SequenciaEbp(
            texto=(textos[-1].strip() if textos else "")[:2000],
            graficos=tuple(graficos),
        ))

    return JogadaEbp(
        nome=nome,
        categoria_origem=categoria_origem,
        descricao=descricao[:2000],
        sequencias=tuple(sequencias),
    )


def _ponto(x: int, y: int) -> tuple[int, int]:
    esquerda, topo, direita, fundo = MARGEM_CAMPO
    x_limitado = max(COORDENADA_X_MIN, min(COORDENADA_X_MAX, x))
    y_limitado = max(COORDENADA_Y_MIN, min(COORDENADA_Y_MAX, y))
    return (
        round(esquerda + (x_limitado - COORDENADA_X_MIN) * (direita - esquerda)
              / (COORDENADA_X_MAX - COORDENADA_X_MIN)),
        round(topo + (y_limitado - COORDENADA_Y_MIN) * (fundo - topo)
              / (COORDENADA_Y_MAX - COORDENADA_Y_MIN)),
    )


def _cor_bgr(valor: int) -> tuple[int, int, int]:
    if valor < 0:
        return 255, 255, 255
    return valor & 255, (valor >> 8) & 255, (valor >> 16) & 255


def _cabeca_seta(
    desenho: ImageDraw.ImageDraw,
    inicio: tuple[float, float],
    fim: tuple[float, float],
    cor,
    largura: int = 6,
) -> None:
    angulo = math.atan2(fim[1] - inicio[1], fim[0] - inicio[0])
    tamanho = 23
    meia_largura = 10
    base_x = fim[0] - tamanho * math.cos(angulo)
    base_y = fim[1] - tamanho * math.sin(angulo)
    normal_x = -math.sin(angulo) * meia_largura
    normal_y = math.cos(angulo) * meia_largura
    desenho.polygon((
        fim,
        (base_x + normal_x, base_y + normal_y),
        (base_x - normal_x, base_y - normal_y),
    ), fill=cor)


def _seta(
    desenho: ImageDraw.ImageDraw,
    inicio: tuple[int, int],
    fim: tuple[int, int],
    cor,
    largura: int = 6,
) -> None:
    desenho.line((inicio, fim), fill=cor, width=largura)
    _cabeca_seta(desenho, inicio, fim, cor, largura)


def _linha_tracejada(
    desenho: ImageDraw.ImageDraw,
    inicio: tuple[int, int],
    fim: tuple[int, int],
    cor,
    com_seta: bool = True,
) -> None:
    distancia = max(1, math.dist(inicio, fim))
    passos = max(1, int(distancia / 22))
    for indice in range(0, passos, 2):
        a = indice / passos
        b = min(1, (indice + 1) / passos)
        p1 = (inicio[0] + (fim[0] - inicio[0]) * a, inicio[1] + (fim[1] - inicio[1]) * a)
        p2 = (inicio[0] + (fim[0] - inicio[0]) * b, inicio[1] + (fim[1] - inicio[1]) * b)
        desenho.line((p1, p2), fill=cor, width=4)
    if com_seta:
        _cabeca_seta(desenho, (
            round(inicio[0] + (fim[0] - inicio[0]) * .86),
            round(inicio[1] + (fim[1] - inicio[1]) * .86),
        ), fim, cor, 4)


def _suavizar_percurso(pontos: list[tuple[int, int]]) -> list[tuple[float, float]]:
    if len(pontos) < 3:
        return list(pontos)
    resultado: list[tuple[float, float]] = list(pontos)
    for _ in range(3):
        novos = [resultado[0]]
        for inicio, fim in zip(resultado, resultado[1:]):
            novos.append((inicio[0] * .75 + fim[0] * .25, inicio[1] * .75 + fim[1] * .25))
            novos.append((inicio[0] * .25 + fim[0] * .75, inicio[1] * .25 + fim[1] * .75))
        novos.append(resultado[-1])
        resultado = novos
    return resultado


def _agrupar_percursos(
    graficos: list[GraficoEbp],
    tipos: set[str],
) -> list[list[GraficoEbp]]:
    percursos: list[list[GraficoEbp]] = []
    atual: list[GraficoEbp] = []
    for grafico in graficos:
        if grafico.tipo not in tipos:
            continue
        inicio = _ponto(grafico.x1, grafico.y1)
        fim_anterior = _ponto(atual[-1].x2, atual[-1].y2) if atual else None
        if atual and fim_anterior and math.dist(fim_anterior, inicio) <= 3:
            atual.append(grafico)
        else:
            if atual:
                percursos.append(atual)
            atual = [grafico]
    if atual:
        percursos.append(atual)
    return percursos


def _pontos_percurso(graficos: list[GraficoEbp]) -> list[tuple[int, int]]:
    if not graficos:
        return []
    return [
        _ponto(graficos[0].x1, graficos[0].y1),
        *[_ponto(grafico.x2, grafico.y2) for grafico in graficos],
    ]


def _desenhar_percurso(
    desenho: ImageDraw.ImageDraw,
    pontos: list[tuple[int, int]],
    cor,
    largura: int = 4,
    com_seta: bool = True,
) -> None:
    percurso = _suavizar_percurso(pontos)
    desenho.line(percurso, fill=cor, width=largura, joint="curve")
    if com_seta:
        _cabeca_seta(desenho, percurso[-2], percurso[-1], cor, largura)


def _desenhar_drible(
    desenho: ImageDraw.ImageDraw,
    pontos: list[tuple[int, int]],
    cor,
    com_seta: bool = True,
) -> None:
    percurso = _suavizar_percurso(pontos)
    ziguezague: list[tuple[float, float]] = [percurso[0]]
    lado = 1
    for inicio, fim in zip(percurso, percurso[1:]):
        distancia = max(1, math.dist(inicio, fim))
        segmentos = max(1, int(distancia / 24))
        dx, dy = fim[0] - inicio[0], fim[1] - inicio[1]
        comprimento = max(1, math.hypot(dx, dy))
        normal = (-dy / comprimento * 6, dx / comprimento * 6)
        for indice in range(1, segmentos + 1):
            t = indice / segmentos
            deslocamento = 0 if indice == segmentos else lado
            ziguezague.append((
                inicio[0] + dx * t + normal[0] * deslocamento,
                inicio[1] + dy * t + normal[1] * deslocamento,
            ))
            lado *= -1
    desenho.line(ziguezague, fill=cor, width=4, joint="curve")
    if com_seta:
        _cabeca_seta(desenho, ziguezague[-2], ziguezague[-1], cor, 4)


def _desenhar_lancamento(
    desenho: ImageDraw.ImageDraw,
    inicio: tuple[int, int],
    fim: tuple[int, int],
    cor,
) -> None:
    dx, dy = fim[0] - inicio[0], fim[1] - inicio[1]
    comprimento = max(1, math.hypot(dx, dy))
    normal = (-dy / comprimento * 4, dx / comprimento * 4)
    for lado in (-1, 1):
        desenho.line((
            (inicio[0] + normal[0] * lado, inicio[1] + normal[1] * lado),
            (fim[0] + normal[0] * lado, fim[1] + normal[1] * lado),
        ), fill=cor, width=2)
    _cabeca_seta(desenho, inicio, fim, cor, 4)


def _misturar_cor(cor: tuple[int, int, int], destino: tuple[int, int, int], peso: float) -> tuple[int, int, int]:
    return tuple(round(origem * (1 - peso) + alvo * peso) for origem, alvo in zip(cor, destino))


def _fundo_campo(campo: GraficoEbp | None) -> Image.Image:
    if campo:
        cantos = (
            _cor_bgr(campo.espessura),
            _cor_bgr(campo.rotacao),
            _cor_bgr(campo.cor),
            _cor_bgr(campo.seta),
        )
        cantos = tuple(_misturar_cor(cor, (255, 255, 255), .28) for cor in cantos)
    else:
        cantos = ((249, 249, 249), (224, 224, 224), (244, 244, 244), (232, 232, 232))
    base = Image.new("RGB", (2, 2))
    base.putdata(cantos)
    return base.resize(TAMANHO_IMAGEM, Image.Resampling.BILINEAR).convert("RGBA")


def _imagem_campo(campo: GraficoEbp | None = None) -> Image.Image:
    largura, altura = TAMANHO_IMAGEM
    imagem = _fundo_campo(campo)
    desenho = ImageDraw.Draw(imagem)
    cor = (20, 20, 20, 255)
    espessura = 4
    esquerda, topo, direita, fundo = MARGEM_CAMPO

    desenho.rectangle((esquerda, topo, direita, fundo), outline=cor, width=espessura)
    centro_x = largura // 2
    aro_y = round(altura * .137)
    desenho.line((round(largura * .438), round(altura * .111),
                  round(largura * .562), round(altura * .111)), fill=cor, width=5)
    desenho.ellipse((centro_x - 21, aro_y - 21, centro_x + 21, aro_y + 21), outline=cor, width=4)

    garrafao_esquerda = round(largura * .343)
    garrafao_direita = round(largura * .657)
    lance_livre_y = round(altura * .422)
    desenho.rectangle((garrafao_esquerda, topo, garrafao_direita, lance_livre_y), outline=cor, width=espessura)
    raio_lance = round(largura * .081)
    desenho.ellipse((centro_x - raio_lance, lance_livre_y - raio_lance,
                     centro_x + raio_lance, lance_livre_y + raio_lance), outline=cor, width=espessura)

    raio_restritiva_x = round(largura * .087)
    raio_restritiva_y = round(altura * .083)
    desenho.arc((centro_x - raio_restritiva_x, aro_y - raio_restritiva_y,
                 centro_x + raio_restritiva_x, aro_y + raio_restritiva_y), 0, 180, fill=cor, width=espessura)

    canto = round(largura * .079)
    desenho.line((canto, topo, canto, aro_y), fill=cor, width=espessura)
    desenho.line((largura - canto, topo, largura - canto, aro_y), fill=cor, width=espessura)
    raio_triplo = centro_x - canto
    desenho.arc((centro_x - raio_triplo, aro_y - raio_triplo,
                 centro_x + raio_triplo, aro_y + raio_triplo), 0, 180, fill=cor, width=espessura)
    return imagem


def _fonte_jogador(tamanho: int = 52) -> ImageFont.ImageFont:
    for nome in ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"):
        try:
            return ImageFont.truetype(nome, tamanho)
        except OSError:
            continue
    return ImageFont.load_default(size=tamanho)


def _desenhar_simbolo_jogador(
    imagem: Image.Image,
    desenho: ImageDraw.ImageDraw,
    grafico: GraficoEbp,
    centro: tuple[int, int],
) -> None:
    raio = 53
    diametro = raio * 2
    base = _misturar_cor(_cor_bgr(grafico.cor), (255, 255, 255), .24)
    claro = _misturar_cor(base, (255, 255, 255), .48)
    gradiente = Image.radial_gradient("L").resize((diametro, diametro), Image.Resampling.BILINEAR)
    preenchimento = ImageOps.colorize(gradiente, black=claro, white=base).convert("RGBA")
    mascara = Image.new("L", (diametro, diametro), 0)
    mascara_desenho = ImageDraw.Draw(mascara)
    if grafico.tipo in {"triangle", "trianglef"}:
        pontos_locais = ((raio, 1), (diametro - 2, diametro - 2), (2, diametro - 2))
        mascara_desenho.polygon(pontos_locais, fill=255)
    else:
        mascara_desenho.ellipse((1, 1, diametro - 2, diametro - 2), fill=255)
    imagem.paste(preenchimento, (centro[0] - raio, centro[1] - raio), mascara)

    if grafico.tipo in {"triangle", "trianglef"}:
        pontos = ((centro[0], centro[1] - raio),
                  (centro[0] + raio - 2, centro[1] + raio - 2),
                  (centro[0] - raio + 2, centro[1] + raio - 2))
        desenho.line((*pontos, pontos[0]), fill=(12, 12, 12, 255), width=4, joint="curve")
        centro_texto = (centro[0], centro[1] + 13)
    else:
        caixa = (centro[0] - raio, centro[1] - raio, centro[0] + raio, centro[1] + raio)
        desenho.ellipse(caixa, outline=(12, 12, 12, 255), width=4)
        centro_texto = centro

    etiqueta = str(grafico.numero) if grafico.numero else grafico.texto
    if etiqueta:
        fonte = _fonte_jogador()
        caixa_texto = desenho.textbbox((0, 0), etiqueta, font=fonte, stroke_width=1)
        desenho.text((centro_texto[0] - (caixa_texto[2] - caixa_texto[0]) / 2,
                      centro_texto[1] - (caixa_texto[3] - caixa_texto[1]) / 2 - 5),
                     etiqueta, fill=(8, 8, 8, 255), font=fonte, stroke_width=1,
                     stroke_fill=(8, 8, 8, 255))


def _desenhar_bola(desenho: ImageDraw.ImageDraw, centro: tuple[int, int]) -> None:
    raio = 17
    caixa = (centro[0] - raio, centro[1] - raio, centro[0] + raio, centro[1] + raio)
    desenho.ellipse(caixa, fill=(250, 250, 250, 255), outline=(10, 10, 10, 255), width=4)


def renderizar_sequencia_ebp(sequencia: SequenciaEbp) -> str:
    campo = next((grafico for grafico in sequencia.graficos if grafico.tipo == "court"), None)
    imagem = _imagem_campo(campo)
    desenho = ImageDraw.Draw(imagem)
    tipos_simbolo = {"circle", "triangle", "trianglef", "ball", "ballf"}
    linhas = [grafico for grafico in sequencia.graficos if grafico.tipo != "court" and grafico.tipo not in tipos_simbolo]
    simbolos = [grafico for grafico in sequencia.graficos if grafico.tipo in tipos_simbolo]

    tipos_compostos = {
        "loop", "ploop", "dribbel", "pdribbel", "screen", "pscreen", "pass", "ppass", "shot", "pshot",
    }
    for grafico in linhas:
        if grafico.tipo in tipos_compostos:
            continue
        inicio, fim = _ponto(grafico.x1, grafico.y1), _ponto(grafico.x2, grafico.y2)
        cor_linha = (*_cor_bgr(grafico.cor), 255)
        largura = max(3, min(9, grafico.espessura * 4))
        _seta(desenho, inicio, fim, cor_linha, largura)

    for percurso in _agrupar_percursos(linhas, {"pass", "ppass"}):
        pontos = _pontos_percurso(percurso)
        cor_linha = (*_cor_bgr(percurso[-1].cor), 255)
        for indice, (inicio, fim) in enumerate(zip(pontos, pontos[1:])):
            _linha_tracejada(
                desenho,
                inicio,
                fim,
                cor_linha,
                com_seta=indice == len(pontos) - 2
                and (percurso[-1].tipo == "ppass" or bool(percurso[-1].seta)),
            )

    for percurso in _agrupar_percursos(linhas, {"shot", "pshot"}):
        pontos = _pontos_percurso(percurso)
        cor_linha = (*_cor_bgr(percurso[-1].cor), 255)
        for inicio, fim in zip(pontos, pontos[1:]):
            _desenhar_lancamento(desenho, inicio, fim, cor_linha)

    for percurso in _agrupar_percursos(linhas, {"screen", "pscreen"}):
        pontos = _pontos_percurso(percurso)
        cor_linha = (*_cor_bgr(percurso[-1].cor), 255)
        largura = max(3, min(9, percurso[-1].espessura * 4))
        desenho.line(pontos, fill=cor_linha, width=largura, joint="curve")
        if percurso[-1].tipo == "pscreen" and len(pontos) >= 2:
            inicio, fim = pontos[-2], pontos[-1]
            angulo = math.atan2(fim[1] - inicio[1], fim[0] - inicio[0]) + math.pi / 2
            deslocamento = (math.cos(angulo) * 20, math.sin(angulo) * 20)
            desenho.line((fim[0] - deslocamento[0], fim[1] - deslocamento[1],
                          fim[0] + deslocamento[0], fim[1] + deslocamento[1]), fill=cor_linha, width=largura)

    for percurso in _agrupar_percursos(linhas, {"loop", "ploop"}):
        cor_linha = (*_cor_bgr(percurso[-1].cor), 255)
        _desenhar_percurso(
            desenho,
            _pontos_percurso(percurso),
            cor_linha,
            com_seta=percurso[-1].tipo == "ploop" or bool(percurso[-1].seta),
        )
    for percurso in _agrupar_percursos(linhas, {"dribbel", "pdribbel"}):
        cor_linha = (*_cor_bgr(percurso[-1].cor), 255)
        _desenhar_drible(
            desenho,
            _pontos_percurso(percurso),
            cor_linha,
            com_seta=percurso[-1].tipo == "pdribbel" or bool(percurso[-1].seta),
        )

    for grafico in simbolos:
        centro = _ponto(grafico.x1, grafico.y1)
        if grafico.tipo in {"ball", "ballf"}:
            _desenhar_bola(desenho, centro)
            continue
        _desenhar_simbolo_jogador(imagem, desenho, grafico, centro)

    saida = io.BytesIO()
    imagem.save(saida, format="PNG", optimize=True)
    return preparar_imagem_passo(saida.getvalue())
