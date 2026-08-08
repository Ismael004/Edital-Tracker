import os 
import json
import re
import requests
from bs4 import BeautifulSoup
from groq import Groq
from dotenv import load_dotenv
from urllib.parse import urljoin

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_DISPONIVEL = True
except ImportError:
    PLAYWRIGHT_DISPONIVEL = False

load_dotenv()

def gerar_mapa_otimizado_de_links(html_bruto: str, url_base: str) -> dict:
    soup = BeautifulSoup(html_bruto, 'html.parser')

    # CORREÇÃO 1: Limpeza cirúrgica. Mantemos nav, aside, header, footer e button vivos!
    # Apagamos apenas código que não contém texto legível
    for tag in soup(['script', 'style', 'iframe', 'svg', 'noscript', 'canvas']):
        tag.decompose()

    mapa_de_links = {}
    contador_id = 1
    
    padrao_lixo = re.compile(r'(login|logout|senha|carrinho|checkout|contato|tag|author|category|facebook|instagram|twitter|youtube|linkedin)', re.IGNORECASE)

    for tag_a in soup.find_all('a', href=True):
        texto_limpo = tag_a.get_text(strip=True)
        link_parcial = tag_a['href']

        # CORREÇÃO 2: Reduzido de 10 para 4 caracteres.
        # Agora siglas curtas como "PIBIC", "PRAE", "Ed.1" não serão mais ignoradas!
        if not texto_limpo or len(texto_limpo) < 4 or link_parcial.startswith(('javascript:', '#', 'mailto:', 'tel:')):
            continue
            
        if padrao_lixo.search(link_parcial):
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

def particionar_dicionario(dicionario: dict, tamanho_lote: int):
    itens = list(dicionario.items())
    for i in range(0, len(itens), tamanho_lote):
        yield dict(itens[i:i + tamanho_lote])

# CAMADA DE REDE (AQUISIÇÃO DE DADOS)

def requisitar_html_estatico(url: str) -> str:
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    try:
        resposta = requests.get(url, headers=headers, timeout=15)
        resposta.raise_for_status()
        return resposta.text
    except Exception as erro:
        print(f"[REDE] Falha na aquisição estática ({url}): {erro}")
        return ""

def renderizar_html_dinamico(url: str) -> str:
    if not PLAYWRIGHT_DISPONIVEL:
        print("[REDE] Fallback dinâmico indisponível. Instale o Playwright.")
        return ""
    
    print("[REDE] Detectado possível bloqueio ou site dinâmico. Injetando motor de renderização...")
    try:
        with sync_playwright() as motor:
            navegador = motor.chromium.launch(headless=True)
            pagina = navegador.new_page()
            pagina.goto(url, wait_until="networkidle", timeout=30000)
            codigo_fonte = pagina.content()
            navegador.close()
            return codigo_fonte
    except Exception as erro:
        print(f"[REDE] Falha catastrófica no motor de renderização: {erro}")
        return ""

# CONTROLADOR DA RASPAGEM E TRIAGEM

def executar_coleta_e_triagem(url_alvo: str) -> list:
    print(f"\n[COLETOR] Inicializando varredura no host: {url_alvo}")

    documento_html = requisitar_html_estatico(url_alvo)
    mapa_dados = {}
    
    if documento_html:
        mapa_dados = gerar_mapa_otimizado_de_links(documento_html, url_alvo)

    if len(mapa_dados) < 10:
        documento_html_dinamico = renderizar_html_dinamico(url_alvo)
        if documento_html_dinamico:
            mapa_dados = gerar_mapa_otimizado_de_links(documento_html_dinamico, url_alvo)
            print(f"[COLETOR] Fallback dinâmico bem-sucedido. Total indexado: {len(mapa_dados)} nós.")

    if not mapa_dados:
        print("[COLETOR] Nenhum nó de dado viável extraído. Abortando operação para esta URL.")
        return []

    chave_groq = os.getenv("GROQ_API_KEY")
    if not chave_groq:
        print("[SISTEMA] Credenciais da Groq ausentes no ambiente.")
        return []

    cliente_ia = Groq(api_key=chave_groq)
    resultados_finais = []
    
    lotes_processamento = list(particionar_dicionario(mapa_dados, 100))
    print(f"[COLETOR] {len(mapa_dados)} nós mapeados. Encaminhando para IA em {len(lotes_processamento)} lote(s)...")

    for indice, lote_atual in enumerate(lotes_processamento):
        texto_otimizado_para_ia = "\n".join([f"[{id_item}] {dados['titulo']}" for id_item, dados in lote_atual.items()])
        
        prompt_engenharia = f"""
        Você é um analisador sintático de dados da web.
        Abaixo há uma lista de textos extraídos de um portal, precedidos por um número de identificação [ID].
        Sua TAREFA ÚNICA: Identifique TODOS os itens que representam CONTEÚDO REAL do site (como manchetes, notícias, artigos, editais, publicações, comunicados, projetos ou atualizações em geral).
        Você deve rejeitar APENAS lixo estrutural e de navegação (ex: "Leia mais", "Página Anterior", "Esqueci a senha", "Políticas de Privacidade", "Acessibilidade").
        
        Lista de Dados:
        {texto_otimizado_para_ia}
        
        Devolva APENAS um JSON válido. A única chave deve ser "ids_aprovados", que contém uma lista com os números inteiros correspondentes aos conteúdos válidos.
        Exemplo de saída: {{"ids_aprovados": [1, 2, 5, 14, 22, 99]}}
        Se o lote inteiro for apenas lixo de navegação, devolva: {{"ids_aprovados": []}}
        """

        try:
            resposta_ia = cliente_ia.chat.completions.create(
                messages=[{"role": "user", "content": prompt_engenharia}],
                model="llama-3.3-70b-versatile",
                temperature=0, 
                response_format={"type": "json_object"}    
            )

            dados_decodificados = json.loads(resposta_ia.choices[0].message.content)
            ids_validados = dados_decodificados.get("ids_aprovados", [])
            
            for id_aprovado in ids_validados:
                if id_aprovado in lote_atual:
                    item_original = lote_atual[id_aprovado]
                    resultados_finais.append({
                        "titulo": item_original["titulo"],
                        "link": item_original["link"],
                        "fonte": url_alvo
                    })

        except Exception as erro:
            print(f"[IA] Falha no processamento cognitivo do Lote {indice + 1}: {erro}")

    return resultados_finais