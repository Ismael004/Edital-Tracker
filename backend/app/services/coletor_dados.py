import os
import json
import re
import time
import hashlib
import sqlite3
import requests
from bs4 import BeautifulSoup
from groq import Groq
from dotenv import load_dotenv
from urllib.parse import urljoin, urlparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_DISPONIVEL = True
except ImportError:
    PLAYWRIGHT_DISPONIVEL = False

load_dotenv()

CAMINHO_CACHE = "cache_coleta.sqlite3"
TTL_CACHE_SEGUNDOS = 6 * 3600  # 6 horas — ajuste conforme a frequência de atualização do site alvo

# ============================================================
# IDENTIDADE DE REDE (compartilhada entre requests e Playwright)
# ============================================================

USER_AGENT_PADRAO = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
)

HEADERS_PADRAO = {
    'User-Agent': USER_AGENT_PADRAO,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7',
    'Referer': 'https://www.google.com/',
}

# Status HTTP que indicam bloqueio por WAF/anti-bot — tentar de novo com o
# mesmo fingerprint não resolve, então nesses casos pulamos direto pro
# fallback dinâmico em vez de gastar as tentativas do retry.
STATUS_BLOQUEIO = {401, 403, 429, 503}

# Muita WAF devolve HTTP 200 normal, mas o corpo da página é uma tela de
# desafio/captcha em vez do conteúdo real. Isso passa batido pelo status_code
# e só aparece se você olhar o texto — daí esse detector por palavra-chave.
SINAIS_DE_BLOQUEIO = [
    "captcha", "recaptcha", "hcaptcha", "cloudflare", "checking your browser",
    "just a moment", "ray id", "attention required", "access denied",
    "acesso negado", "acesso restrito", "verifique que você é humano",
    "não sou um robô", "unusual traffic", "bloqueado por segurança",
    "sua conexão será verificada",
]


def detectar_sinais_de_bloqueio(html: str) -> list:
    """Varre o HTML por termos que indicam página de challenge/captcha,
    mesmo quando o status HTTP veio 200 (bloqueio "disfarçado")."""
    if not html:
        return []
    html_lower = html.lower()
    return [sinal for sinal in SINAIS_DE_BLOQUEIO if sinal in html_lower]

# Sessão reaproveitada entre chamadas: mantém cookies de sessão que alguns
# portais de governo exigem desde a primeira requisição.
SESSAO_HTTP = requests.Session()
SESSAO_HTTP.headers.update(HEADERS_PADRAO)


# ============================================================
# CAMADA DE CACHE (evita reprocessar a mesma URL repetidamente)
# ============================================================

def inicializar_cache():
    conexao = sqlite3.connect(CAMINHO_CACHE)
    conexao.execute("""
        CREATE TABLE IF NOT EXISTS resultados (
            hash_url TEXT PRIMARY KEY,
            url TEXT,
            payload TEXT,
            criado_em REAL
        )
    """)
    conexao.commit()
    conexao.close()


def _hash_url(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def buscar_no_cache(url: str):
    conexao = sqlite3.connect(CAMINHO_CACHE)
    linha = conexao.execute(
        "SELECT payload, criado_em FROM resultados WHERE hash_url = ?",
        (_hash_url(url),)
    ).fetchone()
    conexao.close()

    if not linha:
        return None

    payload, criado_em = linha
    if time.time() - criado_em > TTL_CACHE_SEGUNDOS:
        return None  # expirado

    return json.loads(payload)


def salvar_no_cache(url: str, resultados: list):
    conexao = sqlite3.connect(CAMINHO_CACHE)
    conexao.execute(
        "INSERT OR REPLACE INTO resultados (hash_url, url, payload, criado_em) VALUES (?, ?, ?, ?)",
        (_hash_url(url), url, json.dumps(resultados, ensure_ascii=False), time.time())
    )
    conexao.commit()
    conexao.close()


# ============================================================
# UTILITÁRIO DE RETRY COM BACKOFF EXPONENCIAL
# ============================================================

def com_retry(tentativas: int = 3, espera_base: float = 1.5):
    def decorador(func):
        def wrapper(*args, **kwargs):
            ultimo_erro = None
            for tentativa in range(tentativas):
                try:
                    return func(*args, **kwargs)
                except Exception as erro:
                    ultimo_erro = erro
                    if tentativa < tentativas - 1:
                        espera = espera_base ** tentativa
                        print(f"[RETRY] Tentativa {tentativa + 1} falhou ({erro}). Nova tentativa em {espera:.1f}s...")
                        time.sleep(espera)
            print(f"[RETRY] Todas as {tentativas} tentativas falharam: {ultimo_erro}")
            return None
        return wrapper
    return decorador


# ============================================================
# EXTRAÇÃO E MAPEAMENTO DE LINKS
# ============================================================

PADRAO_LIXO = re.compile(
    r'(login|logout|senha|carrinho|checkout|contato|tag|author|category|'
    r'facebook|instagram|twitter|youtube|linkedin|whatsapp|acessibilidade|'
    r'privacidade|cookies?)',
    re.IGNORECASE
)


def gerar_mapa_otimizado_de_links(html_bruto: str, url_base: str) -> dict:
    soup = BeautifulSoup(html_bruto, 'html.parser')

    for tag in soup(['script', 'style', 'iframe', 'svg', 'noscript', 'canvas']):
        tag.decompose()

    mapa_de_links = {}
    contador_id = 1

    for tag_a in soup.find_all('a', href=True):
        texto_limpo = tag_a.get_text(strip=True)
        link_parcial = tag_a['href']

        if not texto_limpo or len(texto_limpo) < 4:
            continue
        if link_parcial.startswith(('javascript:', '#', 'mailto:', 'tel:')):
            continue

        # Aplica o filtro de lixo tanto no href quanto no texto visível do link
        if PADRAO_LIXO.search(link_parcial) or PADRAO_LIXO.search(texto_limpo):
            continue

        link_absoluto = urljoin(url_base, link_parcial)

        ja_existe = any(item['link'] == link_absoluto for item in mapa_de_links.values())

        if not ja_existe:
            mapa_de_links[contador_id] = {
                "titulo": texto_limpo,
                "link": link_absoluto
            }
            contador_id += 1

    return mapa_de_links


def mesclar_mapas(mapa_principal: dict, mapa_adicional: dict) -> dict:
    """
    Une dois mapas de links sem perder o que já foi coletado.
    Nunca substitui — sempre soma o que há de novo.
    """
    proximo_id = max(mapa_principal.keys(), default=0) + 1
    links_existentes = {item['link'] for item in mapa_principal.values()}

    for item in mapa_adicional.values():
        if item['link'] not in links_existentes:
            mapa_principal[proximo_id] = item
            links_existentes.add(item['link'])
            proximo_id += 1

    return mapa_principal


def particionar_dicionario(dicionario: dict, tamanho_lote: int):
    itens = list(dicionario.items())
    for i in range(0, len(itens), tamanho_lote):
        yield dict(itens[i:i + tamanho_lote])


# ============================================================
# CAMADA DE REDE (AQUISIÇÃO DE DADOS)
# ============================================================

def requisitar_html_estatico(url: str, tentativas: int = 3, espera_base: float = 1.5, info: dict = None) -> str:
    """
    Não usa mais o decorator @com_retry genérico porque precisamos distinguir
    dois tipos de falha:
      - erro transitório (timeout, conexão caiu) -> vale a pena tentar de novo
      - bloqueio de WAF/anti-bot (403/429/503)    -> retry não resolve nada,
        é melhor economizar tempo e já sinalizar pro chamador ir de Playwright

    Se um dict for passado em `info`, ele é preenchido com status_code, tempo
    gasto e eventual erro — usado pelo testar_url() pra diagnóstico. O resto
    do pipeline não passa esse argumento e continua funcionando igual.
    """
    for tentativa in range(tentativas):
        t_inicio = time.time()
        try:
            resposta = SESSAO_HTTP.get(url, timeout=15)
            tempo_ms = round((time.time() - t_inicio) * 1000)

            if info is not None:
                info["status_code"] = resposta.status_code
                info["tempo_ms"] = tempo_ms
                info["servidor"] = resposta.headers.get("Server", "")

            if resposta.status_code in STATUS_BLOQUEIO:
                print(f"[REDE] {url} respondeu HTTP {resposta.status_code} (bloqueio de WAF/anti-bot). "
                      f"Pulando retry e indo direto para o fallback dinâmico.")
                if info is not None:
                    info["bloqueado"] = True
                return ""

            resposta.raise_for_status()
            return resposta.text

        except requests.exceptions.RequestException as erro:
            if info is not None:
                info["erro"] = str(erro)
            if tentativa < tentativas - 1:
                espera = espera_base ** tentativa
                print(f"[RETRY] Tentativa {tentativa + 1} falhou ({erro}). Nova tentativa em {espera:.1f}s...")
                time.sleep(espera)
            else:
                print(f"[RETRY] Todas as {tentativas} tentativas falharam: {erro}")

    return ""


def html_parece_pobre(html: str, mapa_dados: dict) -> bool:
    """
    Critério de qualidade mais robusto que uma simples contagem de links.
    Combina: HTML vazio/curto, poucos links úteis, ou indícios de SPA sem conteúdo renderizado.
    """
    if not html or len(html) < 500:
        return True

    if len(mapa_dados) < 5:
        return True

    marcadores_spa = ['<div id="root"></div>', '<div id="app"></div>', 'ng-app', 'data-reactroot']
    if any(marcador in html for marcador in marcadores_spa) and len(mapa_dados) < 15:
        return True

    return False


# Mascara os sinais mais óbvios de automação que sites com bot-detection
# (comum em portais .gov.br) checam antes de decidir servir conteúdo completo.
SCRIPT_ANTI_DETECCAO = """
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
Object.defineProperty(navigator, 'languages', { get: () => ['pt-BR', 'pt', 'en-US', 'en'] });
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
window.chrome = window.chrome || { runtime: {} };
"""

# Seletores comuns de botão "aceitar" em banners de cookie/LGPD.
# Muito site gov.br/prefeitura trava o clique/scroll até isso ser fechado.
SELETORES_BANNER_COOKIE = [
    "#onetrust-accept-btn-handler",
    "[id*='cookie'] button",
    "[class*='cookie'] button",
    "button:has-text('Aceitar')",
    "button:has-text('aceito')",
    "button:has-text('Concordo')",
    "button:has-text('Entendi')",
    "button:has-text('OK')",
]


def _fechar_banner_cookies(pagina) -> bool:
    for seletor in SELETORES_BANNER_COOKIE:
        try:
            elemento = pagina.query_selector(seletor)
            if elemento and elemento.is_visible():
                elemento.click(timeout=2000)
                pagina.wait_for_timeout(500)
                print(f"[REDE] Banner de cookies fechado via seletor: {seletor}")
                return True
        except Exception:
            continue
    return False


def renderizar_html_dinamico(url: str, scroll: bool = True, caminho_screenshot: str = None, info: dict = None) -> str:
    if not PLAYWRIGHT_DISPONIVEL:
        print("[REDE] Playwright indisponível. Instale com: pip install playwright && playwright install chromium")
        return ""

    print("[REDE] Acionando motor de renderização dinâmica...")
    try:
        with sync_playwright() as motor:
            navegador = motor.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled'],
            )
            contexto = navegador.new_context(
                user_agent=USER_AGENT_PADRAO,
                locale='pt-BR',
                timezone_id='America/Sao_Paulo',
                viewport={'width': 1366, 'height': 768},
                extra_http_headers={'Accept-Language': 'pt-BR,pt;q=0.9'},
            )
            contexto.add_init_script(SCRIPT_ANTI_DETECCAO)

            pagina = contexto.new_page()
            # Timeout maior — portais de governo tendem a ser mais lentos que a média
            pagina.goto(url, wait_until="domcontentloaded", timeout=45000)

            banner_fechado = _fechar_banner_cookies(pagina)
            if info is not None:
                info["banner_cookie_fechado"] = banner_fechado

            # Critério de espera principal: algo concreto apareceu na página.
            # networkidle sozinho é frágil em sites cheios de tracker/anúncio (ex: G1),
            # onde a rede quase nunca fica realmente ociosa.
            try:
                pagina.wait_for_selector('a', timeout=15000)
            except Exception:
                print("[REDE] Nenhum link surgiu em 15s — seguindo mesmo assim.")

            # Ainda damos uma chance curta de rede ociosa, mas sem depender dela
            try:
                pagina.wait_for_load_state("networkidle", timeout=6000)
            except Exception:
                pass

            if scroll:
                altura_anterior = 0
                for _ in range(6):
                    pagina.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    pagina.wait_for_timeout(800)
                    altura_atual = pagina.evaluate("document.body.scrollHeight")
                    if altura_atual == altura_anterior:
                        break
                    altura_anterior = altura_atual

            if caminho_screenshot:
                try:
                    pagina.screenshot(path=caminho_screenshot, full_page=True)
                    print(f"[REDE] Screenshot salvo em: {caminho_screenshot}")
                except Exception as erro_screenshot:
                    print(f"[REDE] Não foi possível salvar screenshot: {erro_screenshot}")

            codigo_fonte = pagina.content()
            navegador.close()
            return codigo_fonte
    except Exception as erro:
        print(f"[REDE] Falha catastrófica no motor de renderização: {erro}")
        return ""


# ============================================================
# CAMADA DE TRIAGEM COM IA (PARALELIZADA)
# ============================================================

def _montar_prompt(lote_atual: dict) -> str:
    texto_otimizado = "\n".join([f"[{id_item}] {dados['titulo']}" for id_item, dados in lote_atual.items()])
    return f"""
Você é um analisador sintático de dados da web.
Abaixo há uma lista de textos extraídos de um portal, precedidos por um número de identificação [ID].
Sua TAREFA ÚNICA: Identifique TODOS os itens que representam CONTEÚDO REAL do site (como manchetes, notícias, artigos, editais, publicações, comunicados, projetos ou atualizações em geral).
Você deve rejeitar APENAS lixo estrutural e de navegação (ex: "Leia mais", "Página Anterior", "Esqueci a senha", "Políticas de Privacidade", "Acessibilidade").

Lista de Dados:
{texto_otimizado}

Devolva APENAS um JSON válido. A única chave deve ser "ids_aprovados", que contém uma lista com os números inteiros correspondentes aos conteúdos válidos.
Exemplo de saída: {{"ids_aprovados": [1, 2, 5, 14, 22, 99]}}
Se o lote inteiro for apenas lixo de navegação, devolva: {{"ids_aprovados": []}}
"""


# A Groq descontinuou o llama-3.3-70b-versatile em 17/06/2026 (deprecation policy:
# https://console.groq.com/docs/deprecations). Modelo recomendado pela própria Groq
# para a mesma categoria de uso (geral/raciocínio, inferência rápida): openai/gpt-oss-120b.
# Centralizado aqui pra não precisar caçar string dentro do código da próxima vez
# que algum modelo for aposentado — só trocar essa constante.
MODELO_GROQ_TRIAGEM = "openai/gpt-oss-120b"


@com_retry(tentativas=2, espera_base=2.0)
def _chamar_ia(cliente_ia: Groq, prompt: str) -> dict:
    resposta = cliente_ia.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=MODELO_GROQ_TRIAGEM,
        temperature=0,
        response_format={"type": "json_object"}
    )
    return json.loads(resposta.choices[0].message.content)


def _validar_ids_aprovados(dados_decodificados, lote_atual: dict) -> list:
    """Valida que a resposta da IA tem o formato esperado antes de usar."""
    if not isinstance(dados_decodificados, dict):
        return []
    ids = dados_decodificados.get("ids_aprovados", [])
    if not isinstance(ids, list):
        return []
    return [i for i in ids if isinstance(i, int) and i in lote_atual]


def processar_lote(cliente_ia: Groq, lote_atual: dict, indice: int, url_alvo: str) -> list:
    prompt = _montar_prompt(lote_atual)
    resultado = _chamar_ia(cliente_ia, prompt)

    if resultado is None:
        print(f"[IA] Lote {indice + 1} descartado após falhas de retry.")
        return []

    ids_validados = _validar_ids_aprovados(resultado, lote_atual)

    return [
        {
            "titulo": lote_atual[id_aprovado]["titulo"],
            "link": lote_atual[id_aprovado]["link"],
            "fonte": url_alvo
        }
        for id_aprovado in ids_validados
    ]


def triar_com_ia(mapa_dados: dict, url_alvo: str, tamanho_lote: int = 60, max_workers: int = 5) -> list:
    chave_groq = os.getenv("GROQ_API_KEY")
    if not chave_groq:
        print("[SISTEMA] Credenciais da Groq ausentes no ambiente.")
        return []

    cliente_ia = Groq(api_key=chave_groq)
    lotes = list(particionar_dicionario(mapa_dados, tamanho_lote))
    print(f"[COLETOR] {len(mapa_dados)} nós mapeados. Encaminhando para IA em {len(lotes)} lote(s) paralelos...")

    resultados_finais = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futuros = {
            executor.submit(processar_lote, cliente_ia, lote, i, url_alvo): i
            for i, lote in enumerate(lotes)
        }
        for futuro in as_completed(futuros):
            indice = futuros[futuro]
            try:
                resultados_finais.extend(futuro.result())
            except Exception as erro:
                print(f"[IA] Falha inesperada no lote {indice + 1}: {erro}")

    return resultados_finais


# ============================================================
# CONTROLADOR PRINCIPAL DA COLETA
# ============================================================

def executar_coleta_e_triagem(url_alvo: str, usar_cache: bool = True, forcar_scroll: bool = True) -> list:
    print(f"\n[COLETOR] Inicializando varredura no host: {url_alvo}")

    inicializar_cache()

    if usar_cache:
        cache_existente = buscar_no_cache(url_alvo)
        if cache_existente is not None:
            print(f"[CACHE] Resultado reaproveitado do cache ({len(cache_existente)} itens).")
            return cache_existente

    # --- Etapa 1: coleta estática ---
    documento_html = requisitar_html_estatico(url_alvo) or ""
    mapa_dados = gerar_mapa_otimizado_de_links(documento_html, url_alvo) if documento_html else {}

    # --- Etapa 2: fallback dinâmico, com MERGE em vez de substituição ---
    if html_parece_pobre(documento_html, mapa_dados):
        documento_html_dinamico = renderizar_html_dinamico(url_alvo, scroll=forcar_scroll)
        if documento_html_dinamico:
            mapa_dinamico = gerar_mapa_otimizado_de_links(documento_html_dinamico, url_alvo)
            antes = len(mapa_dados)
            mapa_dados = mesclar_mapas(mapa_dados, mapa_dinamico)
            print(f"[COLETOR] Fallback dinâmico mesclado: {antes} -> {len(mapa_dados)} nós únicos.")

    if not mapa_dados:
        print("[COLETOR] Nenhum nó de dado viável extraído. Abortando operação para esta URL.")
        return []

    # --- Etapa 3: triagem via IA, em paralelo ---
    resultados_finais = triar_com_ia(mapa_dados, url_alvo)

    if usar_cache and resultados_finais:
        salvar_no_cache(url_alvo, resultados_finais)

    print(f"[COLETOR] Coleta finalizada: {len(resultados_finais)} itens aprovados.")
    return resultados_finais


# ============================================================
# EXECUÇÃO PARA MÚLTIPLAS URLS (BÔNUS: paraleliza também os sites)
# ============================================================

def executar_coleta_multiplas_urls(urls: list, max_workers_sites: int = 3) -> list:
    """
    Roda a coleta para vários sites em paralelo (nível de site, não de lote).
    Cuidado com max_workers_sites: cada site já abre workers próprios para IA,
    então o total de threads simultâneas é max_workers_sites * max_workers (da triagem).
    """
    todos_resultados = []
    with ThreadPoolExecutor(max_workers=max_workers_sites) as executor:
        futuros = {executor.submit(executar_coleta_e_triagem, url): url for url in urls}
        for futuro in as_completed(futuros):
            url = futuros[futuro]
            try:
                todos_resultados.extend(futuro.result())
            except Exception as erro:
                print(f"[COLETOR] Falha total na URL {url}: {erro}")
    return todos_resultados


# ============================================================
# DIAGNÓSTICO — testar UMA URL isolada, com log de cada etapa
# ============================================================

PASTA_DEBUG = "debug_coleta"


def _slug_debug(url: str) -> str:
    dominio = urlparse(url).netloc.replace(".", "_") or "url_sem_dominio"
    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{dominio}_{carimbo}"


def testar_url(url: str, usar_ia: bool = True, salvar_debug: bool = True) -> dict:
    """
    Roda o pipeline de coleta para uma única URL, sem cache e sem paralelismo,
    imprimindo o que acontece em cada etapa. Feito pra você testar rapidamente
    se um site problemático (prefeitura, governo, G1...) foi corrigido, sem
    precisar rodar a rotina inteira com todos os sites em paralelo.

    Com salvar_debug=True (padrão), grava em disco, dentro de debug_coleta/:
      - estatico.html   -> HTML bruto que o requests recebeu
      - dinamico.html   -> HTML bruto que o Playwright recebeu (se acionado)
      - screenshot.png  -> print da página renderizada (se o Playwright rodou)
    Contagem de links não conta a história toda — às vezes o site devolve
    HTTP 200 mas o corpo é um captcha, ou os "72 links" são todos lixo de
    menu. Esses arquivos deixam você conferir com os próprios olhos.

    Uso:
        from services.coletor_dados import testar_url
        testar_url("https://www.exemplo.gov.br/noticias")

    Ou via terminal:
        python coletor_dados.py https://www.exemplo.gov.br/noticias
    """
    print("=" * 70)
    print(f"[TESTE] Iniciando diagnóstico para: {url}")
    print("=" * 70)

    diagnostico = {
        "url": url,
        "status_code_estatico": None,
        "html_estatico_bytes": 0,
        "links_estatico": 0,
        "sinais_bloqueio_estatico": [],
        "usou_fallback_dinamico": False,
        "motivo_fallback": None,
        "html_dinamico_bytes": 0,
        "links_dinamico": 0,
        "sinais_bloqueio_dinamico": [],
        "banner_cookie_fechado": False,
        "links_finais": 0,
        "itens_aprovados_ia": 0,
        "resultados": [],
        "pasta_debug": None,
        "tempo_total_s": 0,
    }

    pasta = None
    if salvar_debug:
        pasta = os.path.join(PASTA_DEBUG, _slug_debug(url))
        os.makedirs(pasta, exist_ok=True)
        diagnostico["pasta_debug"] = pasta

    t0 = time.time()

    # --- Etapa 1: estático ---
    info_estatico = {}
    html_estatico = requisitar_html_estatico(url, info=info_estatico) or ""
    diagnostico["status_code_estatico"] = info_estatico.get("status_code")
    diagnostico["html_estatico_bytes"] = len(html_estatico)

    print(f"[TESTE] Estático: HTTP {info_estatico.get('status_code', '?')}, "
          f"{len(html_estatico)} bytes, {info_estatico.get('tempo_ms', '?')}ms.")
    if info_estatico.get("erro"):
        print(f"[TESTE] Erro de rede na etapa estática: {info_estatico['erro']}")

    sinais_estatico = detectar_sinais_de_bloqueio(html_estatico)
    diagnostico["sinais_bloqueio_estatico"] = sinais_estatico
    if sinais_estatico:
        print(f"[TESTE] ⚠️  HTML estático parece ser página de challenge/captcha "
              f"(HTTP 200, mas encontrado: {sinais_estatico}).")

    if pasta and html_estatico:
        with open(os.path.join(pasta, "estatico.html"), "w", encoding="utf-8") as f:
            f.write(html_estatico)

    mapa = gerar_mapa_otimizado_de_links(html_estatico, url) if html_estatico else {}
    diagnostico["links_estatico"] = len(mapa)
    print(f"[TESTE] {len(mapa)} links úteis extraídos do estático.")
    if mapa:
        print("[TESTE] Amostra de títulos extraídos (confira se fazem sentido):")
        for _id, item in list(mapa.items())[:5]:
            print(f"    [{_id}] {item['titulo'][:80]}")

    # --- Etapa 2: decide se precisa do fallback dinâmico ---
    pobre = html_parece_pobre(html_estatico, mapa)
    if pobre:
        if len(html_estatico) < 500:
            motivo = "HTML vazio/curto (provável bloqueio ou erro de rede)"
        elif len(mapa) < 5:
            motivo = "poucos links úteis (<5)"
        else:
            motivo = "indício de SPA sem conteúdo renderizado"
        diagnostico["motivo_fallback"] = motivo
        print(f"[TESTE] HTML considerado pobre ({motivo}). Acionando Playwright...")

        caminho_screenshot = os.path.join(pasta, "screenshot.png") if pasta else None
        info_dinamico = {}
        html_dinamico = renderizar_html_dinamico(
            url, scroll=True, caminho_screenshot=caminho_screenshot, info=info_dinamico
        )
        diagnostico["usou_fallback_dinamico"] = True
        diagnostico["html_dinamico_bytes"] = len(html_dinamico)
        diagnostico["banner_cookie_fechado"] = info_dinamico.get("banner_cookie_fechado", False)
        print(f"[TESTE] Banner de cookies foi fechado? {'Sim' if diagnostico['banner_cookie_fechado'] else 'Não (ou não havia)'}.")

        sinais_dinamico = detectar_sinais_de_bloqueio(html_dinamico)
        diagnostico["sinais_bloqueio_dinamico"] = sinais_dinamico
        if sinais_dinamico:
            print(f"[TESTE] ⚠️  HTML dinâmico também parece página de challenge/captcha: {sinais_dinamico}. "
              f"Olhe o screenshot.png pra confirmar visualmente.")

        if pasta and html_dinamico:
            with open(os.path.join(pasta, "dinamico.html"), "w", encoding="utf-8") as f:
                f.write(html_dinamico)

        if html_dinamico:
            mapa_dinamico = gerar_mapa_otimizado_de_links(html_dinamico, url)
            diagnostico["links_dinamico"] = len(mapa_dinamico)
            antes = len(mapa)
            mapa = mesclar_mapas(mapa, mapa_dinamico)
            print(f"[TESTE] Dinâmico: {len(html_dinamico)} bytes, {len(mapa_dinamico)} links próprios "
                  f"(mesclado: {antes} -> {len(mapa)} únicos).")
        else:
            print("[TESTE] Fallback dinâmico não retornou HTML nenhum — Playwright falhou por completo.")
    else:
        print("[TESTE] HTML estático já é suficiente — fallback dinâmico não foi acionado.")

    diagnostico["links_finais"] = len(mapa)

    if not mapa:
        print("[TESTE] Nenhum link foi extraído por nenhuma das duas vias. Abortando aqui.")
        diagnostico["tempo_total_s"] = round(time.time() - t0, 1)
        if pasta:
            print(f"[TESTE] Arquivos de debug salvos em: {pasta}/")
        print(f"[TESTE] Concluído em {diagnostico['tempo_total_s']}s.")
        print("=" * 70)
        return diagnostico

    # --- Etapa 3: triagem por IA (opcional, pra isolar problema de coleta vs de IA) ---
    if usar_ia:
        resultados = triar_com_ia(mapa, url)
        diagnostico["itens_aprovados_ia"] = len(resultados)
        diagnostico["resultados"] = resultados
        print(f"[TESTE] IA aprovou {len(resultados)} de {len(mapa)} itens brutos.")
        for item in resultados[:10]:
            print(f"    - {item['titulo']} -> {item['link']}")
        if len(resultados) > 10:
            print(f"    ... e mais {len(resultados) - 10} itens.")
    else:
        print("[TESTE] Triagem por IA pulada (usar_ia=False). Amostra dos links brutos extraídos:")
        for _id, item in list(mapa.items())[:10]:
            print(f"    [{_id}] {item['titulo']} -> {item['link']}")

    diagnostico["tempo_total_s"] = round(time.time() - t0, 1)
    print("=" * 70)
    if pasta:
        print(f"[TESTE] Arquivos de debug salvos em: {pasta}/")
    print(f"[TESTE] Concluído em {diagnostico['tempo_total_s']}s.")
    print("=" * 70)
    return diagnostico


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Uso: python coletor_dados.py <url> [--sem-ia] [--sem-debug]")
        sys.exit(1)

    url_teste = sys.argv[1]
    usar_ia_flag = "--sem-ia" not in sys.argv
    salvar_debug_flag = "--sem-debug" not in sys.argv
    testar_url(url_teste, usar_ia=usar_ia_flag, salvar_debug=salvar_debug_flag)