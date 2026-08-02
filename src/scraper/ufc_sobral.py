import requests 
from bs4 import BeautifulSoup

def buscar_ultimos_editais():
    url = "https://sobral.ufc.br/"
    headers = {'User-Agent': 'Mozilla/5.0'}

    print("Acessando a página de editais da UFC...")
    resposta = requests.get(url, headers=headers)
    site = BeautifulSoup(resposta.content, 'html.parser')

    artigos = site.find_all('article')

    resultados = []

    for item in artigos[:10]:
        link_tag = item.find('a')
        
        if link_tag:
            texto = link_tag.get_text(strip=True)
            link = link_tag.get('href')

            if len(texto) > 10:     
                resultados.append({"título": texto, "link": link})

    return resultados 

if __name__ == "__main__":
    editais = buscar_ultimos_editais()
    print("Últimos editais encontrados: ")
    for edital in editais:
        print(f"Título: {edital['título']}, Link: {edital['link']}")