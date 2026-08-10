from services.coletor_dados import executar_coleta_multiplas_urls
from services.avaliador import analisar_editais_periodico
from services.disparador_email import enviar_relatorio_email
from database.db import (
    obter_todas_configuracoes_ativas,
    salvar_oportunidade,
    obter_urls_ja_processadas,
)


def rotina_diaria_de_buscas():
    print("\n[CRON] Acordando agendador. Iniciando varredura em lote...")
    usuarios_ativos = obter_todas_configuracoes_ativas()

    if not usuarios_ativos:
        print("[CRON] Operação cancelada: Nenhum usuário ativo encontrado no banco.")
        return

    for config in usuarios_ativos:
        user_id = config.get('user_id')
        try:
            email_usuario = config.get('email')
            sites = config.get('target_sites', [])
            prompt_banco = config.get('prompt_perfil', 'Oportunidades e editais relevantes')

            if not email_usuario:
                print(f"[CRON] [{user_id}] Alerta: Usuário ignorado por ausência de e-mail cadastrado.")
                continue

            if not sites:
                print(f"[CRON] [{user_id}] Alerta: Nenhum site configurado. Pulando.")
                continue

            print(f"\n[CRON] --- Processando usuário: {user_id} ---")

            # FASE 1: Coleta paralela entre todos os sites do usuário
            brutos = executar_coleta_multiplas_urls(sites)

            if not brutos:
                print(f"[CRON] [{user_id}] Nenhum item coletado em nenhum dos sites.")
                continue

            # FASE 2: Dedup em lote — UMA busca ao banco, não uma por item
            urls_ja_vistas = obter_urls_ja_processadas(user_id)
            ineditos = [item for item in brutos if item.get('link') and item['link'] not in urls_ja_vistas]

            if not ineditos:
                print(f"[CRON] [{user_id}] Sem nenhuma publicação inédita hoje (base sincronizada).")
                continue

            print(f"[CRON] [{user_id}] {len(ineditos)} inédito(s) de {len(brutos)} coletado(s). Acionando curadoria...")

            # FASE 3: Curadoria já faz batching + paralelização internamente
            aprovados = analisar_editais_periodico(ineditos, perfil_usuario=prompt_banco) or []

            # FASE 4: Notificação + checkpoint
            if aprovados:
                print(f"[CRON] [{user_id}] IA aprovou {len(aprovados)} item(ns). Enviando e-mail...")
                sucesso = enviar_relatorio_email(email_usuario, aprovados, modo_sem_ia=False)

                if sucesso:
                    for edital in ineditos:
                        salvar_oportunidade(user_id, edital)
                    print(f"[CRON] [{user_id}] Checkpoint salvo para {len(ineditos)} item(ns).")
                else:
                    rejeitados = [item for item in ineditos if item not in aprovados]
                    for edital in rejeitados:
                        salvar_oportunidade(user_id, edital)
                    print(f"[CRON] [{user_id}] Falha no envio — aprovados serão retentados na próxima execução.")
            else:
                print(f"[CRON] [{user_id}] IA não aprovou nenhum item hoje. Salvando checkpoint mesmo assim.")
                for edital in ineditos:
                    salvar_oportunidade(user_id, edital)

        except Exception as e:
            print(f"[CRON] Falha estrutural ao processar usuário {user_id}: {e}")
            continue


if __name__ == "__main__":
    rotina_diaria_de_buscas()