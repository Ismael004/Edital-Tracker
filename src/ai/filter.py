import os
from google import genai
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
    
    try:
        resposta = cliente.models.generate_content(
            model='gemini-flash-latest',
            contents=prompt
        )
        texto_resposta = resposta.text.strip()
        
        if texto_resposta.upper().startswith("SIM"):
            return {
                "relevante": True,
                "justificativa": texto_resposta[3:].strip() 
            }
        else:
            return {
                "relevante": False,
                "justificativa": "Edital ignorado pelo filtro de interesses."
            }
            
    except Exception as e:
        print(f"Erro ao consultar a IA: {e}")
        return {"relevante": False, "justificativa": "Erro na IA."}

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