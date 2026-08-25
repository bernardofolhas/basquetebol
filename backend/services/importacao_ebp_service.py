import io
import math
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from services.imagem_playbook_service import preparar_imagem_passo


MAX_FICHEIRO_EBP_BYTES = 10 * 1024 * 1024
MAX_CONTEUDO_EBP_BYTES = 6 * 1024 * 1024
MAX_SEQUENCIAS = 100
MAX_GRAFICOS_POR_SEQUENCIA = 500
LARGURA_COORDENADAS = 7000
ALTURA_COORDENADAS = 6000
TAMANHO_IMAGEM = (1400, 1200)


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
    largura, altura = TAMANHO_IMAGEM
    return (
        round(max(0, min(LARGURA_COORDENADAS, x)) * largura / LARGURA_COORDENADAS),
        round(max(0, min(ALTURA_COORDENADAS, y)) * altura / ALTURA_COORDENADAS),
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
    tamanho = 25
    desenho.line((
        fim,
        (fim[0] - tamanho * math.cos(angulo - .48), fim[1] - tamanho * math.sin(angulo - .48)),
    ), fill=cor, width=largura)
    desenho.line((
        fim,
        (fim[0] - tamanho * math.cos(angulo + .48), fim[1] - tamanho * math.sin(angulo + .48)),
    ), fill=cor, width=largura)


def _seta(
    desenho: ImageDraw.ImageDraw,
    inicio: tuple[int, int],
    fim: tuple[int, int],
    cor,
    largura: int = 6,
) -> None:
    desenho.line((inicio, fim), fill=cor, width=largura)
    _cabeca_seta(desenho, inicio, fim, cor, largura)


def _linha_tracejada(desenho: ImageDraw.ImageDraw, inicio: tuple[int, int], fim: tuple[int, int], cor) -> None:
    distancia = max(1, math.dist(inicio, fim))
    passos = max(1, int(distancia / 22))
    for indice in range(0, passos, 2):
        a = indice / passos
        b = min(1, (indice + 1) / passos)
        p1 = (inicio[0] + (fim[0] - inicio[0]) * a, inicio[1] + (fim[1] - inicio[1]) * a)
        p2 = (inicio[0] + (fim[0] - inicio[0]) * b, inicio[1] + (fim[1] - inicio[1]) * b)
        desenho.line((p1, p2), fill=cor, width=6)
    _cabeca_seta(desenho, (
        round(inicio[0] + (fim[0] - inicio[0]) * .86),
        round(inicio[1] + (fim[1] - inicio[1]) * .86),
    ), fim, cor, 5)


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
) -> list[list[tuple[int, int]]]:
    percursos: list[list[tuple[int, int]]] = []
    atual: list[tuple[int, int]] = []
    for grafico in graficos:
        if grafico.tipo not in tipos:
            continue
        inicio, fim = _ponto(grafico.x1, grafico.y1), _ponto(grafico.x2, grafico.y2)
        if atual and math.dist(atual[-1], inicio) <= 3:
            atual.append(fim)
        else:
            if atual:
                percursos.append(atual)
            atual = [inicio, fim]
    if atual:
        percursos.append(atual)
    return percursos


def _desenhar_percurso(
    desenho: ImageDraw.ImageDraw,
    pontos: list[tuple[int, int]],
    cor,
    largura: int = 6,
) -> None:
    percurso = _suavizar_percurso(pontos)
    desenho.line(percurso, fill=cor, width=largura, joint="curve")
    _cabeca_seta(desenho, percurso[-2], percurso[-1], cor, largura)


def _desenhar_drible(
    desenho: ImageDraw.ImageDraw,
    pontos: list[tuple[int, int]],
    cor,
) -> None:
    percurso = _suavizar_percurso(pontos)
    ziguezague: list[tuple[float, float]] = [percurso[0]]
    lado = 1
    for inicio, fim in zip(percurso, percurso[1:]):
        distancia = max(1, math.dist(inicio, fim))
        segmentos = max(1, int(distancia / 24))
        dx, dy = fim[0] - inicio[0], fim[1] - inicio[1]
        comprimento = max(1, math.hypot(dx, dy))
        normal = (-dy / comprimento * 7, dx / comprimento * 7)
        for indice in range(1, segmentos + 1):
            t = indice / segmentos
            deslocamento = 0 if indice == segmentos else lado
            ziguezague.append((
                inicio[0] + dx * t + normal[0] * deslocamento,
                inicio[1] + dy * t + normal[1] * deslocamento,
            ))
            lado *= -1
    desenho.line(ziguezague, fill=cor, width=5, joint="curve")
    _cabeca_seta(desenho, ziguezague[-2], ziguezague[-1], cor, 5)


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
        ), fill=cor, width=3)
    _cabeca_seta(desenho, inicio, fim, cor, 5)


def _imagem_campo() -> Image.Image:
    largura, altura = TAMANHO_IMAGEM
    imagem = Image.new("RGBA", TAMANHO_IMAGEM, (252, 251, 247, 255))
    desenho = ImageDraw.Draw(imagem)
    cor = (71, 78, 89, 255)
    espessura = 5
    margem = 14

    desenho.rectangle((margem, margem, largura - margem, altura - margem), outline=cor, width=espessura)
    centro_x = largura // 2
    aro_y = round(altura * .095)
    desenho.line((round(largura * .45), round(altura * .045), round(largura * .55), round(altura * .045)), fill=cor, width=7)
    desenho.ellipse((centro_x - 25, aro_y - 25, centro_x + 25, aro_y + 25), outline=cor, width=5)

    garrafao_esquerda = round(largura * .36)
    garrafao_direita = round(largura * .64)
    lance_livre_y = round(altura * .38)
    desenho.rectangle((garrafao_esquerda, margem, garrafao_direita, lance_livre_y), outline=cor, width=espessura)
    raio_lance = round(largura * .115)
    desenho.ellipse((centro_x - raio_lance, lance_livre_y - raio_lance,
                     centro_x + raio_lance, lance_livre_y + raio_lance), outline=cor, width=espessura)

    raio_restritiva = round(largura * .08)
    desenho.arc((centro_x - raio_restritiva, aro_y - raio_restritiva,
                 centro_x + raio_restritiva, aro_y + raio_restritiva), 0, 180, fill=cor, width=espessura)

    canto = round(largura * .075)
    fim_canto_y = round(altura * .27)
    desenho.line((canto, margem, canto, fim_canto_y), fill=cor, width=espessura)
    desenho.line((largura - canto, margem, largura - canto, fim_canto_y), fill=cor, width=espessura)
    raio_triplo = round(largura * .425)
    desenho.arc((centro_x - raio_triplo, aro_y - raio_triplo,
                 centro_x + raio_triplo, aro_y + raio_triplo), 18, 162, fill=cor, width=espessura)

    meio_campo_y = altura - margem
    raio_central = round(largura * .105)
    desenho.ellipse((centro_x - raio_central, meio_campo_y - raio_central,
                     centro_x + raio_central, meio_campo_y + raio_central), outline=cor, width=espessura)
    desenho.ellipse((centro_x - 25, meio_campo_y - 25,
                     centro_x + 25, meio_campo_y + 25), outline=cor, width=4)
    for lado in (margem, largura - margem):
        desenho.line((lado - 1, round(altura * .61), lado + (24 if lado == margem else -24), round(altura * .61)), fill=cor, width=5)
    return imagem


def renderizar_sequencia_ebp(sequencia: SequenciaEbp) -> str:
    imagem = _imagem_campo()
    desenho = ImageDraw.Draw(imagem)
    cor_linha = (31, 41, 55, 255)
    fonte = ImageFont.load_default(size=28)

    linhas = [grafico for grafico in sequencia.graficos if grafico.tipo not in {"court", "circle", "ball"}]
    simbolos = [grafico for grafico in sequencia.graficos if grafico.tipo in {"circle", "ball"}]

    for grafico in linhas:
        inicio, fim = _ponto(grafico.x1, grafico.y1), _ponto(grafico.x2, grafico.y2)
        largura = max(4, min(10, grafico.espessura * 5))
        if grafico.tipo == "ppass":
            _linha_tracejada(desenho, inicio, fim, cor_linha)
        elif grafico.tipo == "pshot":
            _desenhar_lancamento(desenho, inicio, fim, cor_linha)
        elif grafico.tipo == "pscreen":
            desenho.line((inicio, fim), fill=cor_linha, width=largura)
            angulo = math.atan2(fim[1] - inicio[1], fim[0] - inicio[0]) + math.pi / 2
            deslocamento = (math.cos(angulo) * 18, math.sin(angulo) * 18)
            desenho.line((fim[0] - deslocamento[0], fim[1] - deslocamento[1],
                          fim[0] + deslocamento[0], fim[1] + deslocamento[1]), fill=cor_linha, width=largura)
        elif grafico.tipo not in {"loop", "ploop", "dribbel", "pdribbel"}:
            _seta(desenho, inicio, fim, cor_linha, largura)

    for percurso in _agrupar_percursos(linhas, {"loop", "ploop"}):
        _desenhar_percurso(desenho, percurso, cor_linha)
    for percurso in _agrupar_percursos(linhas, {"dribbel", "pdribbel"}):
        _desenhar_drible(desenho, percurso, cor_linha)

    for grafico in simbolos:
        centro = _ponto(grafico.x1, grafico.y1)
        if grafico.tipo == "ball":
            raio = 17
            caixa = (centro[0] - raio, centro[1] - raio, centro[0] + raio, centro[1] + raio)
            desenho.ellipse(caixa, fill=(238, 118, 35, 255), outline=(55, 39, 28, 255), width=3)
            desenho.arc(caixa, 30, 210, fill=(55, 39, 28, 255), width=2)
            desenho.line((centro[0], centro[1] - raio, centro[0], centro[1] + raio), fill=(55, 39, 28, 255), width=2)
            continue
        raio = 30
        preenchimento = (*_cor_bgr(grafico.cor), 255)
        caixa = (centro[0] - raio, centro[1] - raio, centro[0] + raio, centro[1] + raio)
        desenho.ellipse(caixa, fill=preenchimento, outline=(17, 24, 39, 255), width=4)
        etiqueta = str(grafico.numero) if grafico.numero else grafico.texto
        if etiqueta:
            caixa_texto = desenho.textbbox((0, 0), etiqueta, font=fonte)
            desenho.text((centro[0] - (caixa_texto[2] - caixa_texto[0]) / 2,
                          centro[1] - (caixa_texto[3] - caixa_texto[1]) / 2 - 2),
                         etiqueta, fill=(255, 255, 255, 255), font=fonte)

    saida = io.BytesIO()
    imagem.save(saida, format="PNG", optimize=True)
    return preparar_imagem_passo(saida.getvalue())
