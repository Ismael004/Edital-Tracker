# Importações atualizadas: removemos o extrair_brutos e puxamos direto o coletor
from services.coletor_dados import executar_coleta_e_triagem
from services.avaliador import analisar_editais_periodico
from services.disparador_email import enviar_relatorio_email
from database.db import obter_todas_configuracoes_ativas, salvar_oportunidade, edital_ja_processado_para_usuario

def rotina_diaria_de_buscas():
    print("\n[CRON] Acordando agendador. Iniciando varredura em lote...")
    usuarios_ativos = obter_todas_configuracoes_ativas()

    if not usuarios_ativos:
        print("[CRON] Operação cancelada: Nenhum usuário ativo encontrado no banco.")
        return

    for config in usuarios_ativos:
        try:
            # Desempacotamento de dados essenciais
            user_id = config.get('user_id')
            email_usuario = config.get('email')
            sites = config.get('target_sites', [])
            prompt_banco = config.get('prompt_perfil', 'Oportunidades e editais relevantes') 
            
            if not email_usuario:
                print(f"[CRON] [{user_id}] Alerta: Usuário ignorado por ausência de e-mail cadastrado.")
                continue

            print(f"\n[CRON] --- Alocando thread para usuário: {user_id} ---")
            
            aprovados_globais = []
            todos_ineditos_do_dia = []

            # NOVO FLUXO: Processamento Isolado por Site (Evita IA ignorando dados)
            for site_url in sites:
                print(f"[CRON] [{user_id}] Verificando radar: {site_url}")
                
                # FASE 1: Extração Bruta Isolada
                brutos_do_site = executar_coleta_e_triagem(site_url)

                if not brutos_do_site:
                    continue

                # FASE 2: Barreira de Deduplicação Local (Apenas para este site)
                ineditos_do_site = []
                for edital in brutos_do_site:
                    link = edital.get('link', '')
                    if link and not edital_ja_processado_para_usuario(user_id, link):
                        ineditos_do_site.append(edital)
                        todos_ineditos_do_dia.append(edital) # Guarda para o checkpoint final
                
                if not ineditos_do_site:
                    continue

                # FASE 3: Processamento Cognitivo Focado
                print(f"[CRON] [{user_id}] {len(ineditos_do_site)} inéditos em {site_url}. Acionando Gemini...")
                
                # CORRIGIDO: perfil_usuario no lugar de criterio_usuario
                aprovados_do_site = analisar_editais_periodico(ineditos_do_site, perfil_usuario=prompt_banco) or []
                aprovados_globais.extend(aprovados_do_site)

            # FASE 4: Notificação Unificada e Persistência de Estado
            if aprovados_globais:
                print(f"[CRON] [{user_id}] IA chancelou um total de {len(aprovados_globais)} itens. Injetando no SMTP...")
                sucesso = enviar_relatorio_email(email_usuario, aprovados_globais, modo_sem_ia=False)

                if sucesso:
                    for edital in todos_ineditos_do_dia:
                        salvar_oportunidade(user_id, edital)
                    print(f"[CRON] [{user_id}] Checkpoint global salvo com sucesso.")
            else:
                if todos_ineditos_do_dia:
                    print(f"[CRON] [{user_id}] IA bloqueou todas as novidades de todos os sites hoje.")
                    for edital in todos_ineditos_do_dia:
                        salvar_oportunidade(user_id, edital)
                else:
                    print(f"[CRON] [{user_id}] Sem nenhuma publicação inédita hoje (Base de dados perfeitamente sincronizada).")

        except Exception as e:
            print(f"[CRON] Falha estrutural ao processar usuário {user_id}: {e}")
            continue