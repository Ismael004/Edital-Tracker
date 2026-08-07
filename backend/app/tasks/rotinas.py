from services.controlador_principal import extrair_brutos
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
            email_usuario = config.get('email') # Crucial: O e-mail deve vir do banco
            sites = config.get('target_sites', [])
            prompt_banco = config.get('prompt_perfil', 'Oportunidades e editais relevantes') 
            
            if not email_usuario:
                print(f"[CRON] [{user_id}] Alerta: Usuário ignorado por ausência de e-mail cadastrado.")
                continue

            print(f"\n[CRON] --- Alocando thread para usuário: {user_id} ---")
            
            # FASE 1: Extração Bruta (Apenas puxa do site, sem gastar com IA)
            brutos_totais = extrair_brutos(user_id, sites)

            if not brutos_totais:
                print(f"[CRON] [{user_id}] Sites monitorados não retornaram dados legíveis.")
                continue

            # FASE 2: Barreira de Deduplicação Local (ECONOMIA EXTREMA DE TOKENS)
            # Nós só enviamos para a IA aquilo que o usuário NUNCA viu.
            ineditos_reais = []
            for edital in brutos_totais:
                link = edital.get('link', '')
                if link and not edital_ja_processado_para_usuario(user_id, link):
                    ineditos_reais.append(edital)
            
            if not ineditos_reais:
                print(f"[CRON] [{user_id}] Sem publicações inéditas hoje (Base de dados perfeitamente sincronizada).")
                continue

            # FASE 3: Processamento Cognitivo (IA)
            print(f"[CRON] [{user_id}] {len(ineditos_reais)} novos links encontrados. Acionando a Curadoria do Gemini...")
            aprovados_reais = analisar_editais_periodico(ineditos_reais, criterio_usuario=prompt_banco)

            # FASE 4: Notificação e Persistência de Estado (Checkpoint)
            if aprovados_reais:
                print(f"[CRON] [{user_id}] IA chancelou {len(aprovados_reais)} itens. Injetando no túnel SMTP...")
                sucesso = enviar_relatorio_email(email_usuario, aprovados_reais, modo_sem_ia=False)

                if sucesso:
                    # Salva TUDO no banco (tanto o que a IA aprovou quanto o que rejeitou)
                    # Se não salvar os rejeitados, amanhã a IA vai gastar token analisando o mesmo lixo de novo
                    for edital in ineditos_reais:
                        salvar_oportunidade(user_id, edital)
                    print(f"[CRON] [{user_id}] Checkpoint global salvo com sucesso.")
            else:
                print(f"[CRON] [{user_id}] IA bloqueou todas as {len(ineditos_reais)} novidades por incompatibilidade de perfil.")
                for edital in ineditos_reais:
                    salvar_oportunidade(user_id, edital)
                print(f"[CRON] [{user_id}] Checkpoint salvo (Apenas rejeições).")

        except Exception as e:
            # Isolamento Térmico: Se o loop de um usuário quebrar, o except segura o erro 
            # e o "continue" pula para garantir que o próximo usuário da lista receba o e-mail.
            print(f"[CRON] Falha estrutural ao processar usuário {user_id}: {e}")
            continue