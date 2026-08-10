import os
from supabase import create_client, Client
from dotenv import load_dotenv
from typing import List, Dict, Optional, Set

load_dotenv()

url: str = os.getenv("SUPABASE_URL", "")
key: str = os.getenv("SUPABASE_KEY", "")

supabase: Optional[Client] = None
if url and key:
    supabase = create_client(url, key)
else:
    print("[DB] AVISO CRÍTICO: Chaves do Supabase não encontradas. O banco operará em modo offline/falha.")


def obter_todas_configuracoes_ativas() -> List[Dict]:
    if not supabase:
        return []
    try:
        resposta = supabase.table("user_configs").select("*").eq("email_notifications", True).execute()
        return resposta.data
    except Exception as e:
        print(f"[DB] Falha de leitura ao puxar configurações ativas: {e}")
        return []


def atualizar_configuracao_bd(user_id: str, dados: dict) -> bool:
    if not supabase:
        return False
    try:
        payload = {
            "user_id": user_id,
            "email": dados.get("email"),
            "target_sites": dados.get("sites_monitorados", dados.get("target_sites", [])),
            "prompt_perfil": dados.get("prompt_perfil", ""),
            "email_notifications": True
        }
        supabase.table("user_configs").upsert(payload).execute()
        return True
    except Exception as e:
        print(f"[DB] Erro ao gravar novas configurações para o usuário {user_id}: {e}")
        return False


def salvar_oportunidade(user_id: str, oportunidade: Dict) -> bool:
    """
    IMPORTANTE: esta função só deduplica de verdade se a tabela
    'discovered_opportunities' tiver uma constraint UNIQUE(user_id, url)
    configurada no schema do Supabase. Verifique isso direto no painel
    antes de confiar neste dedup — sem a constraint, o upsert insere
    duplicatas silenciosamente.
    """
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
        supabase.table("discovered_opportunities").upsert(
            dados_para_salvar,
            on_conflict="user_id,url"  # explícito: não depender de constraint "adivinhada"
        ).execute()
        return True
    except Exception as e:
        erro_str = str(e).lower()
        if "duplicate key value" not in erro_str and "conflict" not in erro_str:
            print(f"[DB] Falha estrutural ao salvar oportunidade para {user_id}: {e}")
        return False


def obter_urls_ja_processadas(user_id: str) -> Set[str]:
    """
    Busca TODAS as URLs já processadas para o usuário em uma única chamada.
    Substitui edital_ja_processado_para_usuario() para checagem em lote —
    evita 1 round-trip por item coletado (N+1), que fica caro rápido
    quando o scraper traz 50-100+ itens por execução.
    """
    if not supabase:
        return set()
    try:
        resposta = supabase.table("discovered_opportunities") \
            .select("url") \
            .eq("user_id", user_id) \
            .execute()
        return {linha["url"] for linha in resposta.data}
    except Exception as e:
        print(f"[DB] Falha ao buscar URLs já processadas: {e}")
        return set()


def edital_ja_processado_para_usuario(user_id: str, url_alvo: str) -> bool:
    """
    Mantida para compatibilidade com chamadas pontuais (ex: dashboard
    "ao vivo" checando um único item). Para o pipeline em lote/CRON,
    use obter_urls_ja_processadas() + checagem em memória — muito mais barato.
    """
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