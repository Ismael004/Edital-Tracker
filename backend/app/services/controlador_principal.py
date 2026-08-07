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
    brutos = extrair_brutos(user_id, sites)
    aprovados = []
    if brutos:
        print(f"[{user_id}] Acionando filtro AO VIVO para {len(brutos)} itens...")
        # Alinhado para 'perfil_usuario' conforme definido no avaliador.py
        aprovados = analisar_editais_ao_vivo(brutos, perfil_usuario=prompt_perfil) or []
    return brutos, aprovados

def executar_motor_periodico(user_id: str, sites: list[str], prompt_perfil: str) -> tuple[list, list]:
    brutos = extrair_brutos(user_id, sites)
    aprovados = []
    if brutos:
        print(f"[{user_id}] Acionando filtro PERIODICO para {len(brutos)} itens...")
        # Alinhado para 'perfil_usuario' conforme definido no avaliador.py
        aprovados = analisar_editais_periodico(brutos, perfil_usuario=prompt_perfil) or []
    return brutos, aprovados