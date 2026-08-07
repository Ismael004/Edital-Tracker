from services.coletor_dados import executar_coleta_e_triagem
from services.avaliador import analisar_editais_ao_vivo, analisar_editais_periodico

def extrair_brutos(user_id: str, sites: list[str]) -> list:
    # Consolida a extração de múltiplos hosts em um único pacote de dados padronizado
    editais_ineditos = []
    
    for site_url in sites:
        print(f"[MOTOR] [{user_id}] Solicitando varredura no host: {site_url}")
        
        # O novo coletor já entrega os dados padronizados com titulo, link e fonte
        dados_coletados = executar_coleta_e_triagem(site_url)
        
        if dados_coletados:
            editais_ineditos.extend(dados_coletados)
            
    return editais_ineditos

def executar_motor_ao_vivo(user_id: str, sites: list[str], prompt_perfil: str) -> tuple[list, list]:
    # Orquestra a varredura síncrona e aciona o filtro estrito em tempo real do Dashboard
    print(f"[MOTOR] [{user_id}] Iniciando ciclo de processamento AO VIVO...")
    
    brutos = extrair_brutos(user_id, sites)
    aprovados = analisar_editais_ao_vivo(brutos, perfil_usuario=prompt_perfil) or []
    
    if brutos:
        print(f"[MOTOR] [{user_id}] Encaminhando {len(brutos)} itens para o avaliador em tempo real...")
        # Correção do argumento nomeado para criterio_usuario alinhado ao avaliador.py
        aprovados = analisar_editais_ao_vivo(brutos, criterio_usuario=prompt_perfil) or []
        
    return brutos, aprovados

def executar_motor_periodico(user_id: str, sites: list[str], prompt_perfil: str) -> tuple[list, list]:
    # Orquestra a varredura assíncrona agendada e aciona o filtro de curadoria diária
    print(f"[MOTOR] [{user_id}] Iniciando ciclo de processamento PERIÓDICO...")
    
    brutos = extrair_brutos(user_id, sites)
    aprovados = []
    
    if brutos:
        print(f"[MOTOR] [{user_id}] Encaminhando {len(brutos)} itens para a curadoria estratégica...")
        # Correção do argumento nomeado para criterio_usuario alinhado ao avaliador.py
        aprovados = analisar_editais_periodico(brutos, criterio_usuario=prompt_perfil) or []
        
    return brutos, aprovados