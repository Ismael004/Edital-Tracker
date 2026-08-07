import os 
from supabase import create_client, Client
from dotenv import load_dotenv
from typing import List, Dict, Optional

load_dotenv()

# Tratamento para evitar NullPointer (None) na hora de puxar as chaves
url: str = os.getenv("SUPABASE_URL", "")
key: str = os.getenv("SUPABASE_KEY", "")

# Instanciação condicional segura do cliente de banco
supabase: Optional[Client] = None
if url and key:
    supabase = create_client(url, key)
else:
    print("[DB] AVISO CRÍTICO: Chaves do Supabase não encontradas. O banco operará em modo offline/falha.")

def obter_todas_configuracoes_ativas() -> List[Dict]:
    # Busca apenas os usuários que optaram por receber os alertas diários do robô
    if not supabase: 
        return []
        
    try:
        resposta = supabase.table("user_configs").select("*").eq("email_notifications", True).execute()
        return resposta.data
    except Exception as e:
        print(f"[DB] Falha de leitura ao puxar configurações ativas: {e}")
        return []

def atualizar_configuracao_bd(user_id: str, dados: dict) -> bool:
    # Função VITAL para a Rota 1 da API: Salva/Atualiza o perfil do usuário enviado pelo site
    if not supabase: 
        return False
        
    try:
        # Mapeia as chaves que chegam da API (Pydantic) para as colunas reais da tabela no Supabase
        payload = {
            "user_id": user_id,
            "email": dados.get("email_notificacao", dados.get("email")),
            "target_sites": dados.get("sites_monitorados", dados.get("target_sites", [])),
            "prompt_perfil": dados.get("prompt_perfil", ""),
            "email_notifications": True # Reativa notificações por padrão ao atualizar
        }
        
        # Upsert: Insere se não existir, atualiza se o user_id já estiver cadastrado
        supabase.table("user_configs").upsert(payload).execute()
        return True
    except Exception as e:
        print(f"[DB] Erro ao gravar novas configurações para o usuário {user_id}: {e}")
        return False

def salvar_oportunidade(user_id: str, oportunidade: Dict) -> bool:
    # Salva o checkpoint diário para impedir gastos de tokens lendo itens repetidos no dia seguinte
    if not supabase: 
        return False
        
    try: 
        dados_para_salvar = {
            "user_id": user_id,
            "title": oportunidade.get("titulo", oportunidade.get("título", "Sem título")),
            "url": oportunidade.get("link", ""),
            "source_site": oportunidade.get("fonte", "Desconhecido"),
            "ai_summary": oportunidade.get("justificativa", ""),
            "status": "new"
        }
        
        # A API Python do Supabase trata conflitos automaticamente se a tabela tiver restrição UNIQUE (Ex: user_id + url)
        supabase.table("discovered_opportunities").upsert(dados_para_salvar).execute()
        return True
        
    except Exception as e:
        erro_str = str(e).lower()
        # Se for um erro de chave duplicada, é o fluxo natural. Só alertamos se for um erro estrutural diferente.
        if "duplicate key value" not in erro_str and "conflict" not in erro_str:
            print(f"[DB] Falha estrutural ao salvar oportunidade para {user_id}: {e}")
        return False

def edital_ja_processado_para_usuario(user_id: str, url_alvo: str) -> bool:
    # Barreira de economia extrema: Lê o histórico para impedir que a IA processe a mesma URL duas vezes
    if not supabase: 
        return False
        
    try:
        resposta = supabase.table("discovered_opportunities") \
            .select("id") \
            .eq("user_id", user_id) \
            .eq("url", url_alvo) \
            .execute()
        
        return len(resposta.data) > 0
    except Exception as e:
        print(f"[DB] Falha ao verificar barreira de duplicidade: {e}")
        return False

if __name__ == "__main__":
    print("[DB] Executando diagnóstico de conexão com o banco de dados...")
    if supabase:
        configs = obter_todas_configuracoes_ativas()
        print(f"[DB] Conexão perfeita! {len(configs)} radares ativos encontrados na nuvem.")
    else:
        print("[DB] Diagnóstico falhou: Cliente Supabase não pôde ser instanciado.")