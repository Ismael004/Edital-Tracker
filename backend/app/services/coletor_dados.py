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
from urllib.parse import urljoin
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

@com_retry(tentativas=3, espera_base=1.5)
def requisitar_html_estatico(url: str) -> str:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    resposta = requests.get(url, headers=headers, timeout=15)
    resposta.raise_for_status()
    return resposta.text


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


def renderizar_html_dinamico(url: str, scroll: bool = True) -> str:
    if not PLAYWRIGHT_DISPONIVEL:
        print("[REDE] Playwright indisponível. Instale com: pip install playwright && playwright install chromium")
        return ""

    print("[REDE] Acionando motor de renderização dinâmica...")
    try:
        with sync_playwright() as motor:
            navegador = motor.chromium.launch(headless=True)
            contexto = navegador.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                           '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            pagina = contexto.new_page()
            pagina.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Espera por rede ociosa, mas não trava se o site nunca ficar 100% quieto
            try:
                pagina.wait_for_load_state("networkidle", timeout=8000)
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


@com_retry(tentativas=2, espera_base=2.0)
def _chamar_ia(cliente_ia: Groq, prompt: str) -> dict:
    resposta = cliente_ia.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
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
