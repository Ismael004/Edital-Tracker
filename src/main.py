import sys 
import os
import time

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scraper.ufc_sobral import buscar_ultimos_editais
from database.db import iniciar_banco, edital_ja_processado, salvar_edital
from ai.filter import analisar_edital

def executar_rastreador():
    print("1. Iniciar o Edital Tracker")
    iniciar_banco()

    editais = buscar_ultimos_editais()
    novos_editais = 0
    editais_relevantes = 0

    for edital in editais:
        titulo = edital['título']
        link = edital['link']

        if edital_ja_processado(link):
            print(f"2. ❌ O edital '{titulo}' já foi processado anteriormente.")

        else:
            print(f"2. ✅ Novo edital encontrado: '{titulo}'")

            salvar_edital(link)
            novos_editais += 1

            resultado_ia = analisar_edital(titulo, link)

            time.sleep(6)

            if resultado_ia['relevante']:
                editais_relevantes += 1
                print(f"Edital relevante! Justificativa: {resultado_ia['justificativa']}")
            else:
                print("Fora do interesse do usuário.")

    print(f"\n3. Rastreamento concluído! Total de novos editais encontrados: {novos_editais}")


if __name__ == "__main__":
    executar_rastreador()