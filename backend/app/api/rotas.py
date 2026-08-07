from fastapi import APIRouter, HTTPException, BackgroundTasks
from models.schemas import Configuracao_usuario
from services.controlador_principal import executar_motor_ao_vivo
from database.db import atualizar_configuracao_bd

# Criação do roteador principal que será acoplado ao servidor FastAPI (main.py)
router = APIRouter(prefix="/api/editais", tags=["Motor de Busca"])

# ==========================================
# ROTA 1: CONFIGURAÇÃO DE PERFIL
# ==========================================
@router.post("/configurar")
async def salvar_configuracoes(dados: Configuracao_usuario):
    # Recebe os dados do formulário do painel e salva no banco de dados
    try:
        sucesso = atualizar_configuracao_bd(dados.user_id, dados.dict())
        if sucesso:
            return {"status": "sucesso", "mensagem": "Radar configurado. O robô já sabe o que procurar."}
        raise HTTPException(status_code=500, detail="Falha ao persistir dados no banco.")
    
    except Exception as erro:
        print(f"[API] Falha no endpoint /configurar: {erro}")
        raise HTTPException(status_code=500, detail="Erro interno no servidor de banco de dados.")

# ==========================================
# ROTA 2: VARREDURA EM TEMPO REAL (BOTÃO "TESTAR AGORA")
# ==========================================
@router.post("/varredura-ao-vivo")
async def iniciar_varredura_manual(dados: Configuracao_usuario):
    """
    Este é o endpoint acionado quando o usuário clica em "Buscar Agora" no Dashboard.
    Ele não salva no banco, apenas roda os motores e devolve para a tela.
    """
    if not dados.target_sites:
        raise HTTPException(status_code=400, detail="A lista de sites monitorados está vazia.")

    print(f"\n[API] Requisição de Varredura Ao Vivo recebida para o usuário: {dados.user_id}")

    try:
        # Engatamos o Motor Síncrono que construímos no controlador_principal.py
        # Ele vai rodar o Groq (Coletor) e depois o Gemini (Avaliador) em tempo real
        brutos, aprovados = executar_motor_ao_vivo(
            user_id=dados.user_id,
            sites=dados.target_sites,
            prompt_perfil=dados.prompt_perfil
        )

        # Retornamos o JSON perfeitamente estruturado para o frontend desenhar a tela
        return {
            "status": "sucesso",
            "estatisticas": {
                "total_extraido_dos_sites": len(brutos),
                "total_aprovados_pela_ia": len(aprovados)
            },
            "resultados_aprovados": aprovados,
            "logs_brutos": brutos # Opcional: útil se o frontend quiser mostrar uma aba "Tudo que foi achado"
        }

    except Exception as erro:
        print(f"[API] Falha crítica durante a execução do motor ao vivo: {erro}")
        raise HTTPException(status_code=500, detail=str(erro))