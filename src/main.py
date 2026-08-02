import sys 
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scraper.ufc_sobral import buscar_ultimos_editais
from database.db import iniciar_banco, edital_ja_processado, salvar_edital

def executar_rastreador():
    print("1. Iniciar o Edital Tracker")
    iniciar_banco()

    editais = buscar_ultimos_editais()
    novos_editais = 0

    for edital in editais:
        titulo = edital['título']
        link = edital['link']

        if edital_ja_processado(link):
            print(f"2. ❌ O edital '{titulo}' já foi processado anteriormente.")

        else:
            print(f"2. ✅ Novo edital encontrado: '{titulo}'")

            salvar_edital(link)
            novos_editais += 1

    print(f"\n3. Rastreamento concluído! Total de novos editais encontrados: {novos_editais}")


if __name__ == "__main__":
    executar_rastreador()