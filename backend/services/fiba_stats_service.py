"""Normalização segura de ficheiros e respostas API FIBA/Genius Sports."""

from __future__ import annotations

import hashlib
import json
import re
import ssl
import unicodedata
from difflib import SequenceMatcher
from typing import Any
from urllib.parse import quote, urljoin, urlparse

import httpx
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

from config import config


MAX_FIBA_BYTES = 8 * 1024 * 1024
EXTENSOES_FIBA = {".json", ".xml"}
HOSTS_ESTATISTICA_PUBLICA = {"fpb.pt", "www.fpb.pt"}


class ErroImportacaoFiba(ValueError):
    pass


def _pick(registo: dict[str, Any], *nomes: str) -> Any:
    mapa = {str(chave).lower(): valor for chave, valor in registo.items()}
    for nome in nomes:
        valor = mapa.get(nome.lower())
        if valor not in (None, ""):
            return valor
    return None


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor not in (None, "") else ""


def _booleano(valor: Any, default: bool = True) -> bool:
    if valor is None:
        return default
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() not in {"0", "false", "no", "nao", "não", "missed", "failed"}


def _numero(valor: Any) -> float | None:
    try:
        numero = float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return numero if 0 <= numero <= 100 else None


def _inteiro_limitado(valor: Any, minimo: int, maximo: int, default: int) -> int:
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return default
    return max(minimo, min(numero, maximo))


def _segundos_relogio(valor: Any) -> int | None:
    if valor in (None, ""):
        return None
    texto = str(valor).strip()
    if texto.isdigit():
        return min(int(texto), 3600)
    partes = texto.split(":")
    try:
        if len(partes) >= 2:
            return min((int(partes[0]) * 60) + int(partes[1]), 3600)
    except ValueError:
        return None
    return None


def _normalizar_nome(valor: str) -> str:
    sem_acentos = "".join(
        letra for letra in unicodedata.normalize("NFKD", valor or "") if not unicodedata.combining(letra)
    )
    return re.sub(r"[^a-z0-9]+", " ", sem_acentos.lower()).strip()


def _lista_qualificadores(valor: Any) -> list[str]:
    if isinstance(valor, list):
        return [_texto(item) for item in valor if _texto(item)]
    if isinstance(valor, dict):
        return [_texto(chave) for chave, ativo in valor.items() if _booleano(ativo, False)]
    texto = _texto(valor)
    return [item.strip() for item in re.split(r"[,;|]", texto) if item.strip()]


def _tipo_evento(registo: dict[str, Any]) -> str | None:
    acao = _texto(_pick(registo, "actionType", "action_type", "eventType", "event_type", "statType", "tipo")).lower()
    subtipo = _texto(_pick(registo, "subType", "sub_type", "subtipo")).lower()
    qualificadores = " ".join(_lista_qualificadores(_pick(registo, "qualifiers", "qualifier", "qualificadores"))).lower()
    resultado = _pick(registo, "success", "successful", "made", "convertido", "shotResult", "result", "outcome")
    sucesso = _booleano(resultado, default=True)

    if "substitution" in acao or "substituicao" in acao or "substituição" in acao:
        detalhe = f"{subtipo} {qualificadores}".strip()
        if any(token in detalhe for token in ("player in", "sub in", "entrada", "enter", " in")) or detalhe == "in":
            return "entrada_campo"
        if any(token in detalhe for token in ("player out", "sub out", "saida", "saída", "leave", " out")) or detalhe == "out":
            return "saida_campo"
        return None

    if any(token in acao for token in ("freethrow", "free_throw", "free throw", "1pt", "lance_livre", "ll_")):
        return "ll_c" if sucesso and "miss" not in acao else "ll_f"
    if any(token in acao for token in ("3pt", "3points", "threepoint", "three_point", "triplo", "tres_")):
        return "tres_c" if sucesso and "miss" not in acao else "tres_f"
    if any(token in acao for token in ("2pt", "2points", "twopoint", "two_point", "dois_")):
        return "dois_c" if sucesso and "miss" not in acao else "dois_f"
    if "rebound" in acao or "ressalto" in acao:
        detalhe = f"{acao} {subtipo} {qualificadores}"
        return "ressalto_ofensivo" if any(token in detalhe for token in ("offensive", "offence", "ofensivo")) else "ressalto_defensivo"
    equivalencias = {
        "assist": "assistencia",
        "assistencia": "assistencia",
        "steal": "roubo",
        "roubo": "roubo",
        "turnover": "perda",
        "perda": "perda",
        "block": "desarme",
        "desarme": "desarme",
        "foulon": "falta_sofrida",
        "fouldrawn": "falta_sofrida",
        "falta_sofrida": "falta_sofrida",
        "foul": "falta",
        "falta": "falta",
    }
    compacto = re.sub(r"[^a-z_]", "", acao)
    for origem, destino in equivalencias.items():
        if origem in compacto:
            return destino
    return None


def _registo_xml(elemento) -> dict[str, Any]:
    registo: dict[str, Any] = dict(elemento.attrib)
    for filho in list(elemento):
        chave = filho.tag.split("}")[-1]
        if list(filho):
            registo[chave] = [_registo_xml(neto) for neto in list(filho)]
        elif filho.text and filho.text.strip():
            registo[chave] = filho.text.strip()
    return registo


def _extrair_json(payload: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    # FIBA LiveStats Webcast exposes the match in data.json. Shot coordinates
    # are stored separately and are joined to play-by-play by actionNumber.
    if isinstance(payload, dict) and isinstance(payload.get("pbp"), list) and isinstance(payload.get("tm"), dict):
        equipas: list[dict[str, Any]] = []
        lancamentos: dict[str, dict[str, Any]] = {}
        for numero_equipa, equipa_bruta in payload["tm"].items():
            if not isinstance(equipa_bruta, dict):
                continue
            equipa = dict(equipa_bruta)
            equipa["teamNumber"] = str(numero_equipa)
            plantel = equipa.get("pl")
            if isinstance(plantel, dict):
                equipa["players"] = [
                    {**jogador, "pno": str(numero_jogador)}
                    for numero_jogador, jogador in plantel.items()
                    if isinstance(jogador, dict)
                ]
            equipas.append(equipa)
            for lancamento in equipa.get("shot") or []:
                if isinstance(lancamento, dict) and lancamento.get("actionNumber") is not None:
                    lancamentos[str(lancamento["actionNumber"])] = lancamento

        acoes = []
        for acao_bruta in payload["pbp"]:
            if not isinstance(acao_bruta, dict):
                continue
            acao = dict(acao_bruta)
            lancamento = lancamentos.get(str(acao.get("actionNumber")))
            if lancamento:
                acao["x"] = lancamento.get("x")
                acao["y"] = lancamento.get("y")
            acoes.append(acao)
        return acoes, equipas

    acoes: list[dict[str, Any]] = []
    equipas: list[dict[str, Any]] = []

    def visitar(no: Any) -> None:
        if isinstance(no, list):
            for item in no:
                visitar(item)
            return
        if not isinstance(no, dict):
            return
        tipo = _texto(_pick(no, "type")).lower()
        if _pick(no, "actionType", "action_type", "eventType", "event_type", "statType") is not None or tipo == "action":
            acoes.append(no)
        for chave, valor in no.items():
            if str(chave).lower() in {"teams", "competitors"} and isinstance(valor, list):
                equipas.extend(item for item in valor if isinstance(item, dict))
            visitar(valor)

    visitar(payload)
    return acoes, equipas


def _extrair_xml(raiz) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    acoes: list[dict[str, Any]] = []
    equipas: list[dict[str, Any]] = []
    for elemento in raiz.iter():
        nome = elemento.tag.split("}")[-1].lower()
        if nome in {"action", "event", "matchaction", "play"}:
            acoes.append(_registo_xml(elemento))
        elif nome in {"team", "competitor"}:
            registo = _registo_xml(elemento)
            if _pick(registo, "teamNumber", "team_number", "number", "teamId", "id") is not None:
                equipas.append(registo)
    return acoes, equipas


def _jogadores_equipas(equipas_brutas: list[dict[str, Any]]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    equipas: list[dict[str, str]] = []
    jogadores: list[dict[str, str]] = []
    vistos_equipas: set[str] = set()
    vistos_jogadores: set[tuple[str, str]] = set()
    for indice, equipa in enumerate(equipas_brutas, 1):
        numero = _texto(_pick(equipa, "teamNumber", "team_number", "number")) or str(indice)
        nome = _texto(_pick(equipa, "teamName", "name", "nome", "teamNickname")) or f"Equipa {numero}"
        if numero not in vistos_equipas:
            equipas.append({"numero": numero, "nome": nome})
            vistos_equipas.add(numero)
        plantel = _pick(equipa, "players", "persons", "roster", "teamPlayers") or []
        if isinstance(plantel, dict):
            plantel = list(plantel.values())
        if not isinstance(plantel, list):
            continue
        for atleta in plantel:
            if not isinstance(atleta, dict):
                continue
            externo = _texto(_pick(atleta, "pno", "personId", "playerId", "externalId", "id", "shirtNumber"))
            if not externo:
                continue
            chave = (numero, externo)
            if chave in vistos_jogadores:
                continue
            primeiro = _texto(_pick(atleta, "firstName", "givenName"))
            ultimo = _texto(_pick(atleta, "familyName", "lastName", "surname"))
            nome_atleta = _texto(_pick(atleta, "name", "fullName", "displayName")) or " ".join(filter(None, (primeiro, ultimo)))
            jogadores.append({
                "equipa_numero": numero,
                "identificador": externo,
                "nome": nome_atleta or f"Atleta {externo}",
                "numero": _texto(_pick(atleta, "shirtNumber", "jerseyNumber", "number", "pno")),
            })
            vistos_jogadores.add(chave)
    return equipas, jogadores


def interpretar_fiba(conteudo: bytes, nome_ficheiro: str = "estatistica.json", content_type: str = "") -> dict[str, Any]:
    if not conteudo:
        raise ErroImportacaoFiba("O ficheiro está vazio.")
    if len(conteudo) > MAX_FIBA_BYTES:
        raise ErroImportacaoFiba("O ficheiro excede o limite de 8 MB.")
    texto = conteudo.decode("utf-8-sig", errors="replace").strip()
    e_xml = nome_ficheiro.lower().endswith(".xml") or "xml" in content_type.lower() or texto.startswith("<")
    try:
        if e_xml:
            raiz = ElementTree.fromstring(conteudo)
            acoes_brutas, equipas_brutas = _extrair_xml(raiz)
            formato = "xml"
        else:
            payload = json.loads(texto)
            acoes_brutas, equipas_brutas = _extrair_json(payload)
            formato = "json"
    except (ElementTree.ParseError, DefusedXmlException, json.JSONDecodeError, UnicodeError) as exc:
        raise ErroImportacaoFiba("O ficheiro não contém XML ou JSON FIBA válido.") from exc

    equipas, jogadores = _jogadores_equipas(equipas_brutas)
    nomes_jogadores = {(item["equipa_numero"], item["identificador"]): item for item in jogadores}
    eventos: list[dict[str, Any]] = []
    ignorados = 0
    for indice, acao in enumerate(acoes_brutas, 1):
        tipo = _tipo_evento(acao)
        if not tipo:
            ignorados += 1
            continue
        equipa_numero = _texto(_pick(acao, "teamNumber", "team_number", "team", "competitorNumber", "tno"))
        jogador_externo = _texto(_pick(acao, "pno", "personId", "playerId", "player", "person"))
        atleta = nomes_jogadores.get((equipa_numero, jogador_externo), {})
        qualificadores = _lista_qualificadores(_pick(acao, "qualifiers", "qualifier", "qualificadores"))
        externo = _texto(_pick(acao, "messageId", "actionId", "actionNumber", "eventId", "id"))
        if not externo:
            assinatura = json.dumps(acao, ensure_ascii=True, sort_keys=True, default=str)
            externo = hashlib.sha256(f"{indice}:{assinatura}".encode()).hexdigest()[:32]
        posicao_x = _numero(_pick(acao, "x", "posicao_x", "coordinateX"))
        posicao_y = _numero(_pick(acao, "y", "posicao_y", "coordinateY"))
        if posicao_x is None or posicao_y is None:
            posicao_x = posicao_y = None
        eventos.append({
            "identificador_externo": externo,
            "equipa_numero": equipa_numero,
            "jogador_externo": jogador_externo,
            "jogador_nome": atleta.get("nome", ""),
            "jogador_numero": atleta.get("numero", ""),
            "tipo": tipo,
            "periodo": _inteiro_limitado(_pick(acao, "period", "periodo", "quarter"), 1, 20, 1),
            "segundos_restantes": _segundos_relogio(_pick(acao, "clock", "time", "timeRemaining", "segundos_restantes")),
            "posicao_x": posicao_x,
            "posicao_y": posicao_y,
            "subtipo": _texto(_pick(acao, "subType", "sub_type", "subtipo"))[:60] or None,
            "qualificadores": qualificadores,
            "anulado": _booleano(_pick(acao, "deleted", "anulado"), default=False),
        })

    if not eventos:
        raise ErroImportacaoFiba("Não foram encontradas ações estatísticas FIBA compatíveis.")
    if not equipas:
        numeros = sorted({item["equipa_numero"] for item in eventos if item["equipa_numero"]})
        equipas = [{"numero": numero, "nome": f"Equipa {numero}"} for numero in numeros]
    if not jogadores:
        unicos = {}
        for evento in eventos:
            chave = (evento["equipa_numero"], evento["jogador_externo"])
            if evento["jogador_externo"] and chave not in unicos:
                unicos[chave] = {
                    "equipa_numero": evento["equipa_numero"],
                    "identificador": evento["jogador_externo"],
                    "nome": evento["jogador_nome"] or f"Atleta {evento['jogador_externo']}",
                    "numero": evento["jogador_numero"],
                }
        jogadores = list(unicos.values())
    return {
        "formato": formato,
        "equipas": equipas,
        "jogadores": jogadores,
        "eventos": eventos,
        "eventos_ignorados": ignorados,
    }


def sugerir_mapeamentos(jogadores_externos: list[dict[str, str]], jogadores_locais, existentes: dict[str, int] | None = None) -> list[dict[str, Any]]:
    existentes = existentes or {}
    resultado = []
    for externo in jogadores_externos:
        identificador = externo["identificador"]
        sugestao = existentes.get(identificador)
        motivo = "associação guardada" if sugestao else ""
        if not sugestao:
            nome_externo = _normalizar_nome(externo.get("nome", ""))
            candidatos_nome = [item for item in jogadores_locais if _normalizar_nome(item.nome) == nome_externo and nome_externo]
            if len(candidatos_nome) == 1:
                sugestao, motivo = candidatos_nome[0].id, "nome igual"
        if not sugestao and externo.get("numero"):
            candidatos_numero = [item for item in jogadores_locais if str(item.numero_camisola or "") == externo["numero"]]
            if len(candidatos_numero) == 1:
                sugestao, motivo = candidatos_numero[0].id, "número igual"
        if not sugestao and externo.get("nome"):
            candidato, pontuacao = None, 0.0
            for local in jogadores_locais:
                atual = SequenceMatcher(None, _normalizar_nome(externo["nome"]), _normalizar_nome(local.nome)).ratio()
                if atual > pontuacao:
                    candidato, pontuacao = local, atual
            if candidato and pontuacao >= 0.88:
                sugestao, motivo = candidato.id, "nome semelhante"
        resultado.append({**externo, "jogador_id_sugerido": sugestao, "motivo": motivo})
    return resultado


async def obter_estatistica_api(identificador_jogo: str) -> tuple[bytes, str, str]:
    if not config.fiba_stats_api_url_template or not config.fiba_stats_api_key:
        raise ErroImportacaoFiba("A API oficial ainda não está configurada neste ambiente.")
    if "{match_id}" not in config.fiba_stats_api_url_template:
        raise ErroImportacaoFiba("A configuração da API não contém o identificador do jogo.")
    url = config.fiba_stats_api_url_template.replace("{match_id}", quote(identificador_jogo.strip(), safe=""))
    if not url.startswith("https://"):
        raise ErroImportacaoFiba("A ligação à API oficial tem de utilizar HTTPS.")
    headers = {config.fiba_stats_api_key_header: config.fiba_stats_api_key, "Accept": "application/json, application/xml"}
    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=False) as cliente:
            resposta = await cliente.get(url, headers=headers)
            resposta.raise_for_status()
    except httpx.HTTPError as exc:
        raise ErroImportacaoFiba("Não foi possível obter a estatística na API oficial.") from exc
    if len(resposta.content) > MAX_FIBA_BYTES:
        raise ErroImportacaoFiba("A resposta da API excede o limite de 8 MB.")
    content_type = resposta.headers.get("content-type", "application/json")
    extensao = ".xml" if "xml" in content_type.lower() else ".json"
    return resposta.content, f"api-{identificador_jogo}{extensao}", content_type


def _validar_url_estatistica(url: str) -> str:
    valor = (url or "").strip()
    try:
        parsed = urlparse(valor)
        porta = parsed.port
    except ValueError as exc:
        raise ErroImportacaoFiba("O endereço da estatística não é válido.") from exc
    host = (parsed.hostname or "").lower().rstrip(".")
    host_genius = host.endswith(".shared.geniussports.com")
    if parsed.scheme != "https" or not host or parsed.username or parsed.password or porta not in (None, 443):
        raise ErroImportacaoFiba("Utiliza uma ligação HTTPS pública da FPB ou FIBA LiveStats.")
    if host not in HOSTS_ESTATISTICA_PUBLICA and not host_genius:
        raise ErroImportacaoFiba("Por segurança, só são aceites ligações públicas da FPB ou FIBA LiveStats.")
    return valor


def _contexto_ssl_sistema() -> ssl.SSLContext:
    contexto = ssl.create_default_context()
    enum_certificados = getattr(ssl, "enum_certificates", None)
    if not enum_certificados:
        return contexto
    for certificado, encoding, _ in enum_certificados("ROOT"):
        if encoding != "x509_asn":
            continue
        try:
            contexto.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(certificado))
        except ssl.SSLError:
            continue
    return contexto


async def _descarregar_url_estatistica(cliente: httpx.AsyncClient, url: str) -> httpx.Response:
    atual = _validar_url_estatistica(url)
    for _ in range(3):
        try:
            resposta = await cliente.get(
                atual,
                headers={
                    "Accept": "application/json, application/xml, text/html;q=0.8",
                    "User-Agent": "Mozilla/5.0 (compatible; BasketballClubStats/1.0)",
                },
            )
        except httpx.HTTPError as exc:
            raise ErroImportacaoFiba("Não foi possível abrir a ligação da estatística.") from exc
        if resposta.is_redirect:
            destino = resposta.headers.get("location")
            if not destino:
                break
            atual = _validar_url_estatistica(urljoin(atual, destino))
            continue
        try:
            resposta.raise_for_status()
        except httpx.HTTPError as exc:
            raise ErroImportacaoFiba("A ligação da estatística não está disponível publicamente.") from exc
        if len(resposta.content) > MAX_FIBA_BYTES:
            raise ErroImportacaoFiba("A resposta da estatística excede o limite de 8 MB.")
        return resposta
    raise ErroImportacaoFiba("A ligação da estatística redirecionou demasiadas vezes.")


def _url_dados_livestats(html: str, url_origem: str) -> str | None:
    # Webcast pages expose the public data folder in a hidden input.
    datapath = re.search(
        r"id\s*=\s*['\"]datapath['\"][^>]*value\s*=\s*['\"]([^'\"]+)['\"]",
        html,
        flags=re.IGNORECASE,
    )
    if datapath:
        return urljoin(url_origem, datapath.group(1).rstrip("/") + "/data.json")

    # FPB match pages keep the linked LiveStats match id in data-id.
    match_id = re.search(r"id\s*=\s*['\"]inputHiddenMatchId['\"][^>]*data-id\s*=\s*['\"](\d+)['\"]", html, re.I)
    if match_id:
        return f"https://fibalivestats.dcd.shared.geniussports.com/data/{match_id.group(1)}/data.json"

    webcast = re.search(
        r"https://[a-z0-9.-]+\.shared\.geniussports\.com/[^'\"\s<>]+/p\.html",
        html,
        flags=re.IGNORECASE,
    )
    return webcast.group(0) if webcast else None


async def obter_estatistica_link(url_estatistica: str) -> tuple[bytes, str, str]:
    """Resolve a public FPB/FIBA LiveStats page or a direct XML/JSON URL."""
    url = _validar_url_estatistica(url_estatistica)
    async with httpx.AsyncClient(timeout=25, follow_redirects=False, verify=_contexto_ssl_sistema()) as cliente:
        resposta = await _descarregar_url_estatistica(cliente, url)
        content_type = resposta.headers.get("content-type", "").lower()
        nome = urlparse(str(resposta.url)).path.rsplit("/", 1)[-1] or "estatistica.json"
        if any(tipo in content_type for tipo in ("json", "javascript", "xml")) or nome.lower().endswith((".json", ".xml")):
            return resposta.content, nome, content_type

        html = resposta.content.decode("utf-8", errors="replace")
        url_dados = _url_dados_livestats(html, str(resposta.url))
        if not url_dados:
            raise ErroImportacaoFiba(
                "Este jogo ainda não disponibiliza dados FIBA LiveStats públicos. Usa a exportação XML/JSON como alternativa."
            )
        if url_dados.endswith("/p.html"):
            pagina_livestats = await _descarregar_url_estatistica(cliente, url_dados)
            url_dados = _url_dados_livestats(
                pagina_livestats.content.decode("utf-8", errors="replace"),
                str(pagina_livestats.url),
            )
        if not url_dados or url_dados.endswith("/p.html"):
            raise ErroImportacaoFiba("Não foi possível localizar o JSON público deste jogo.")
        dados = await _descarregar_url_estatistica(cliente, url_dados)
        tipo_dados = dados.headers.get("content-type", "application/json")
        return dados.content, "fiba-livestats-data.json", tipo_dados
