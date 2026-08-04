import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scraper.ufc_sobral import buscar_ultimos_editais
from database.db import iniciar_banco, edital_ja_processado, salvar_edital
from ai.filter import analisar_editais
from notifications.email_notifier import enviar_relatorio_email

def executar_rastreador():
    print("Iniciando o Edital-Tracker...")
    print("-" * 50)
    
    iniciar_banco()
    
    print("Buscando editais no site da UFC Sobral...")
    editais = buscar_ultimos_editais()
    
    if not editais:
        print("Nenhum edital encontrado no site (ou falha no raspador).")
        return

    editais_ineditos = []
    for edital in editais:
        if edital_ja_processado(edital['link']):
            print(f"Ignorando (já visto): {edital.get('título', 'Sem Título')}")
        else:
            print(f"NOVO ENCONTRADO: {edital.get('título', 'Sem Título')}")
            editais_ineditos.append(edital)

    print("-" * 50)
    if not editais_ineditos:
        print("Nenhuma novidade no site da UFC hoje. Encerrando.")
        return
        
    print(f"Enviando {len(editais_ineditos)} edital(is) para a IA analisar em lote...")
    editais_aprovados_ia = analisar_editais(editais_ineditos)
    
    sucesso_email = False

    if editais_aprovados_ia is None:
        print("A IA falhou ou está indisponível. Ativando PLANO B (Modo Sobrevivência)...")
        sucesso_email = enviar_relatorio_email(editais_ineditos, modo_sem_ia=True)
        
    elif len(editais_aprovados_ia) > 0:
        print(f"A IA encontrou {len(editais_aprovados_ia)} edital(is) com o seu perfil!")
        sucesso_email = enviar_relatorio_email(editais_aprovados_ia, modo_sem_ia=False)
        
    else:
        print("A IA julgou que todos os editais novos SÃO IRRELEVANTES para você.")
        print("Nenhum e-mail será enviado para evitar spam na sua caixa de entrada.")
        sucesso_email = True 

    if sucesso_email:
        for edital in editais_ineditos:
            salvar_edital(edital['link'])
        print("Progresso salvo no banco de dados. Até amanhã!")
    else:
        print("Houve falha no envio do email. Não salvaremos no banco para podermos tentar de novo na próxima execução.")

if __name__ == "__main__":
    executar_rastreador()