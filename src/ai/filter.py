import os
import time
from google import genai
from google.genai import errors
from dotenv import load_dotenv

load_dotenv()

cliente = genai.Client()

def analisar_edital(titulo, link):
    """
    Envia o título do edital para a IA e pede para ela julgar se é interessante.
    """
    
    prompt = f"""
    Você é meu assistente pessoal acadêmico. 
    O meu perfil: Sou estudante de Engenharia Elétrica, me interesso por tecnologia, 
    programação, estágios, bolsas de pesquisa, inovação e transferência de curso.
    
    Acabei de encontrar este edital no site da universidade:
    Título: "{titulo}"
    
    Sua tarefa:
    1. Avalie se este edital tem alta chance de ser do meu interesse.
    2. Responda APENAS "SIM" se for do meu interesse, ou "NAO" se for irrelevante (como cardápios de RU, editais de humanas, etc).
    3. Se responder "SIM", pule uma linha e escreva um resumo de no máximo 2 frases explicando por que eu deveria ler isso.
    """
    
    for tentativa in range(5):
        try:
            resposta = cliente.models.generate_content(
                model='gemini-2.5-flash-lite',
                contents=prompt
            )
            texto_resposta = resposta.text.strip()
            
            if texto_resposta.upper().startswith("SIM"):
                return {
                    "relevante": True,
                    "justificativa": texto_resposta[3:].strip(),
                    "erro": False
                }
            else:
                return {
                    "relevante": False,
                    "justificativa": "Fora do interesse do usuário.",
                    "erro": False
                }
                
        except errors.APIError as e:
            erro_str = str(e)
            if e.code == 429 or "RESOURCE_EXHAUSTED" in erro_str:
                espera = 15
                
                import re
                match = re.search(r'retry in ([\d\.]+)s', erro_str)
                if match:
                    espera = int(float(match.group(1))) + 2
                    
                print(f"\n   ⏳ O Google pediu para esperar. Pausando por {espera} segundos... (Tentativa {tentativa+1}/5)")
                time.sleep(espera)
            else:
                print(f"   ❌ Erro na API do Google: {e}")
                return {"relevante": False, "justificativa": "Erro na IA.", "erro": True}
        except Exception as e:
             print(f"   ❌ Erro desconhecido: {e}")
             return {"relevante": False, "justificativa": "Erro na IA.", "erro": True}
                
    return {"relevante": False, "justificativa": "Muitos erros de limite. Desistindo deste edital.", "erro": True}

if __name__ == "__main__":
    print("Testando o Cérebro da IA...\n")
    
    edital_teste_1 = "Resultado Preliminar do Edital de Bolsas de Iniciação Científica em Robótica"
    edital_teste_2 = "Resultado da Prestação de Contas do Auxílio Moradia – 2º trimestre"
    
    print(f"Avaliando: {edital_teste_1}")
    resultado_1 = analisar_edital(edital_teste_1, "link-falso")
    print(f"Relevante? {resultado_1['relevante']}")
    print(f"Por quê? {resultado_1['justificativa']}\n")
    print("-" * 40)
    
    print(f"Avaliando: {edital_teste_2}")
    resultado_2 = analisar_edital(edital_teste_2, "link-falso")
    print(f"Relevante? {resultado_2['relevante']}")
    print(f"Por quê? {resultado_2['justificativa']}")