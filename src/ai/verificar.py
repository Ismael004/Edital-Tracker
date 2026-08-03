import os
from google import genai
from dotenv import load_dotenv

# Carrega a variável de ambiente GEMINI_API_KEY
load_dotenv()

def listar_modelos_disponiveis():
    print("Iniciando verificação de modelos disponíveis...\n")
    print("-" * 50)
    
    try:
        # Instancia o cliente da nova biblioteca
        cliente = genai.Client()
        
        # Pede para a API listar todos os modelos que você tem acesso
        modelos = cliente.models.list()
        
        contador = 0
        for modelo in modelos:
            # Vamos imprimir o nome e a descrição para facilitar
            print(f"Nome do Modelo: {modelo.name}")
            print(f"Descrição: {modelo.description}")
            print(f"Versão: {modelo.version}")
            print("-" * 50)
            contador += 1
            
        print(f"\n✅ Total de {contador} modelos encontrados.")
        print("\nPara a nossa IA, procure por algo como 'gemini-1.5-flash', 'gemini-1.5-pro' ou 'gemini-2.0-flash'.")
        
    except Exception as erro:
        print(f"❌ Ocorreu um erro ao listar os modelos: {erro}")
        print("\nDica: Verifique se sua chave da API está correta no arquivo .env.")

if __name__ == "__main__":
    listar_modelos_disponiveis()