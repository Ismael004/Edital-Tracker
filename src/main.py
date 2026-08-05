import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scraper.smart_scraper import buscar_editais_em_qualquer_site
from database.db import iniciar_banco, edital_ja_processado, salvar_edital
from ai.filter import analisar_editais
from notifications.email_notifier import enviar_relatorio_email

FONTES_MONITORADAS = [
    {"nome": "UFC Sobral - Editais", "url": "https://sobral.ufc.br/"},
    {"nome": "UFC PRAE (Bolsas)", "url": "https://prae.ufc.br/pt/"}
]

def executar_rastreador():
    print("Iniciando o Edital-Tracker Multi-Fontes...")
    print("-" * 50)
    
    iniciar_banco()
    
    editais_ineditos = []
    
    for fonte in FONTES_MONITORADAS:
        print(f"\nVerificando: {fonte['nome']}...")
        editais_encontrados = buscar_editais_em_qualquer_site(fonte['url'])
        
        if not editais_encontrados:
            print(f"Nada encontrado ou erro em {fonte['nome']}.")
            continue
            
        print(f"{len(editais_encontrados)} possíveis notícias extraídas de {fonte['nome']}.")
        
        for edital in editais_encontrados:
            titulo = edital.get('título', edital.get('titulo', ''))
            link = edital.get('link', '')
            
            if not titulo or not link:
                continue
                
            if edital_ja_processado(link):
                print(f"⏸Ignorando (já visto): {titulo}")
            else:
                print(f"NOVO ENCONTRADO: {titulo}")
                edital['fonte'] = fonte['nome']
                editais_ineditos.append(edital)

    print("\n" + "-" * 50)
    if not editais_ineditos:
        print("Nenhuma novidade inédita nos sites hoje. Encerrando.")
        return
        
    print(f"Enviando {len(editais_ineditos)} edital(is) para o Gemini analisar o perfil...")
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