from services.coletor_dados import executar_coleta_e_triagem
from services.avaliador import analisar_editais_ao_vivo, analisar_editais_periodico

def executar_motor_ao_vivo(user_id: str, sites: list[str], prompt_perfil: str) -> tuple[list, list]:
    todos_brutos = []
    todos_aprovados = []
    
    for site_url in sites:
        print(f"\n[MOTOR] [{user_id}] Iniciando ciclo isolado para o host: {site_url}")
        
        # 1. Extrai os links APENAS deste site específico
        brutos_do_site = executar_coleta_e_triagem(site_url)
        
        if brutos_do_site:
            todos_brutos.extend(brutos_do_site)
            print(f"[{user_id}] Acionando IA (AO VIVO) exclusivamente para os {len(brutos_do_site)} itens de {site_url}...")
            
            # 2. O Gemini avalia apenas este lote pequeno (Foco 100%, sem perda de dados)
            aprovados_do_site = analisar_editais_ao_vivo(brutos_do_site, perfil_usuario=prompt_perfil) or []
            todos_aprovados.extend(aprovados_do_site)
            
    return todos_brutos, todos_aprovados

def executar_motor_periodico(user_id: str, sites: list[str], prompt_perfil: str) -> tuple[list, list]:
    todos_brutos = []
    todos_aprovados = []
    
    for site_url in sites:
        print(f"\n[MOTOR] [{user_id}] Iniciando ciclo isolado para o host: {site_url}")
        
        # 1. Extrai os links APENAS deste site específico
        brutos_do_site = executar_coleta_e_triagem(site_url)
        
        if brutos_do_site:
            todos_brutos.extend(brutos_do_site)
            print(f"[{user_id}] Acionando IA (PERIÓDICO) exclusivamente para os {len(brutos_do_site)} itens de {site_url}...")
            
            # 2. O Gemini avalia apenas este lote pequeno (Foco 100%, sem perda de dados)
            aprovados_do_site = analisar_editais_periodico(brutos_do_site, perfil_usuario=prompt_perfil) or []
            todos_aprovados.extend(aprovados_do_site)
            
    return todos_brutos, todos_aprovados