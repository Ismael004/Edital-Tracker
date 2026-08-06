import os 
from supabase import create_client, Client
from dotenv import load_dotenv
from typing import List, Dict, Optional

load_dotenv()

url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")

if not url or not key:
    print("Aviso: Chaves do Supabase não encontrados no arquivo")

supabase: Client = create_client(url, key)

def obter_todas_configuracoes_ativas() -> List[Dict]:
    try:
        resposta = supabase.table("user_configs").select("*").eq("email_notifications", True).execute()
        return resposta.data
    except Exception as e:
        print(f"Erro ao puxar configuração do Supabase: {e}")
        return []

def salvar_oportunidade(user_id: str, oportunidade: Dict) -> bool:
    try: 
        dados_para_salvar = {
            "user_id": user_id,
            "title": oportunidade.get("titulo", oportunidade.get("título", "Sem título")),
            "url": oportunidade.get("link", ""),
            "source_site": oportunidade.get("fonte", "Desconhecido"),
            "ai_summary": oportunidade.get("justificativa", ""),
            "status": "new"
        }
        supabase.table("discovered_opportunities").upsert(dados_para_salvar, ignore_duplicates=True).execute()
        return True
    
    except Exception as e:
        if "duplicate key value" not in str(e):
            print(f"Erro ao salvar oportunidade para {user_id}: {e}")
        return False

def edital_ja_processado_para_usuario(user_id: str, url: str) -> bool:
    try:
        resposta = supabase.table("discovered_opportunities") \
            .select("id") \
            .eq("user_id", user_id) \
            .eq("url", url) \
            .execute()
        
        return len(resposta.data) > 0
    except Exception as e:
        print(f"⚠️ Erro ao verificar duplicidade: {e}")
        return False

if __name__ == "__main__":
    print("Testando conexão com o Supabase...")
    # Tenta puxar as configurações
    configs = obter_todas_configuracoes_ativas()
    print(f"Conexão estabelecida! {len(configs)} configurações ativas encontradas na nuvem.")