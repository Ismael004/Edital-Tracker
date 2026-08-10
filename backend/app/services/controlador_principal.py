from services.coletor_dados import executar_coleta_multiplas_urls
from services.avaliador import analisar_editais_ao_vivo


def executar_motor_ao_vivo(user_id: str, sites: list[str], prompt_perfil: str) -> tuple[list, list]:
    """
    Fluxo do botão "Testar agora" no dashboard. Modo rígido (analisar_editais_ao_vivo),
    sem dedup — a pessoa está testando ajuste de prompt/sites e quer ver tudo, mesmo
    itens já vistos antes. Se isso não for mais o comportamento desejado, adicionar
    obter_urls_ja_processadas() aqui, no mesmo padrão usado em tasks/rotinas.py.
    """
    print(f"\n[MOTOR] [{user_id}] Iniciando varredura ao vivo em {len(sites)} site(s)...")

    # Coleta paralela entre sites, em vez de sequencial — mesmo ganho de velocidade
    # já aplicado no fluxo periódico.
    brutos = executar_coleta_multiplas_urls(sites)

    if not brutos:
        print(f"[MOTOR] [{user_id}] Nenhum item coletado.")
        return [], []

    print(f"[MOTOR] [{user_id}] {len(brutos)} item(ns) coletado(s). Acionando IA (modo ao vivo)...")
    aprovados = analisar_editais_ao_vivo(brutos, perfil_usuario=prompt_perfil) or []

    return brutos, aprovados


# NOTA: executar_motor_periodico() foi removido deste arquivo — era código morto,
# nunca chamado por nenhuma rota. O fluxo periódico real vive em tasks/rotinas.py
# (rotina_diaria_de_buscas), que é o que o CRON de fato executa. Manter as duas
# implementações em paralelo é o tipo de duplicação que causa bug de "eu corrigi
# aqui mas o sistema continua usando a versão velha" — ponto único de verdade agora.