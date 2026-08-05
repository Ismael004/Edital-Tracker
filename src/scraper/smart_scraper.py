import os 
import json
import requests
from bs4 import BeautifulSoup
from groq import Groq
from dotenv import load_dotenv
from urllib.parse import urljoin

load_dotenv()

def limpar_html_para_ia(html, url_base):
    soup = BeautifulSoup(html, 'html.parser')

    for tag in soup(['script', 'style', 'header', 'footer', 'nav']):
        tag.decompose()

    links_uteis = []

    for a_tag in soup.find_all('a', href=True):
        texto = a_tag.get_text(strip=True)
        link = a_tag['href']


        if texto and len(texto) > 10:
            link_completo = urljoin(url_base, link)
            links_uteis.append(f"Texto: {texto} | Link: {link_completo}")

    return "\n".join(links_uteis[:150])

def buscar_editais_em_qualquer_site(url):
    print(f"Acessando a página: {url}")

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    try:
        resposta = requests.get(url, headers=headers, timeout=10)
        resposta.raise_for_status()
    except Exception as e:
        print(f"Erro ao acessar a página: {e}")
        return []

    print("Limpando o HTML para enviar à IA...")
    conteudo_limpo = limpar_html_para_ia(resposta.text, url)

    if not conteudo_limpo:
        print("Nenhum link encontrado na página.")
        return []

    chave_groq = os.getenv("GROQ_API_KEY")
    if not chave_groq:
        print("Chave da API Groq não encontrada. Verifique o arquivo .env.")
        return []

    print("Acessando a página com o Groq para extrair links relevantes...")

    client_groq = Groq(api_key=chave_groq)

    pprompt = f"""
    Você é um extrator de dados altamente preciso. Eu vou te dar uma lista de textos e links extraídos de um site educacional, institucional ou de notícias.
    Sua TAREFA ÚNICA é identificar quais desses itens são MANCHETES, NOTÍCIAS, EDITAIS, RESULTADOS ou AVISOS IMPORTANTES e extraí-los.
    Ignore veementemente links de menu de navegação (ex: "Sobre nós", "Contato", "Login", "Esqueceu a senha", "Página Inicial", "Facebook").
    
    Lista de Links extraídos:
    {conteudo_limpo}
    
    Retorne APENAS um objeto JSON válido contendo uma única chave chamada "editais", que deve ser uma lista de objetos com as chaves "título" e "link".
    Formato obrigatório do JSON:
    {{
      "editais": [
        {{"título": "Título exato da notícia ou edital encontrado", "link": "https://link-completo.com"}}
      ]
    }}
    """

    try:
        chat_completion = client_groq.chat.completions.create(
            messages = [{"role": "user", "content": pprompt}],
            model = "llama-3.1-8b-instant",
            temperature = 0, 
            response_format = {"type": "json_object"}    
        )

        resposta_ia = chat_completion.choices[0].message.content

        try:
            dados_json = json.loads(resposta_ia)
            editais = dados_json.get("editais", [])
            return editais

        except json.JSONDecodeError:
            print("Erro ao decodificar a resposta da IA. A resposta recebida não é um JSON válido.")
            return []

    except Exception as e:
        print(f"Erro na API da Groq: {e}")
        return []


