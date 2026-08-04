import os
import json
import time
import re
import pprint
from google import genai
from google.genai import errors
from dotenv import load_dotenv

load_dotenv()

modelo_id = 'gemini-3.1-flash-lite'

def analisar_editais(lista_editais):
    if not lista_editais:
        print("Nenhum edital para analisar.")
        return []

    try:
        cliente = genai.Client()
    except Exception as erro:
        print(f"Erro ao inicializar o cliente: {erro}")
        return []

    textos_editais = ""

    for i, edital in enumerate(lista_editais):
        textos_editais += f"[{i}] Título: {edital['título']} | Link: {edital['link']}\n"

    prompt = f"""   
    Perfil do Estudante: Engenharia Elétrica, focado em tecnologia, programação, estágios, bolsas de pesquisa, inovação e transferência.
    
    Editais encontrados:
    {textos_editais}
    
    TAREFA:
    Avalie os editais acima e selecione os que têm alta chance de interesse para o perfil.
    Retorne APENAS um array JSON. Se nenhum for interessante, retorne [].
    
    Formato OBRIGATÓRIO:
    [
      {{
        "titulo": "titulo exato do edital",
        "link": "link exato",
        "justificativa": "1 frase curta explicando o interesse"
      }}
    ]
    """

    for tentativa in range(3):
        try:
            resposta = cliente.models.generate_content(model = modelo_id, contents = prompt)
            texto_resposta = resposta.text.strip()
            
            if texto_resposta.startswith("```json"):
                texto_resposta = texto_resposta[7:]
            if texto_resposta.endswith("```"):
                texto_resposta = texto_resposta[:-3]
            
            texto_resposta = texto_resposta.strip()
            
            editais_filtrados = json.loads(texto_resposta)
            return editais_filtrados

        except Exception as e:
            erro_str = str(e).lower()
            if "429" in erro_str or "quota" in erro_str or "exhausted" in erro_str:
                tempo_espera = 15 
               
                match = re.search(r'retry in (\d+(\.\d+)?)s', erro_str)
                if match:
                    tempo_espera = int(float(match.group(1))) + 2 
                time.sleep(tempo_espera)
            else:

                print(f"Erro crítico na IA (Não é limite): {e}")
                return []
                
    print("Falha na IA após todas as tentativas. Retornando vazio.")
    return None
            
