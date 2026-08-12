from fastapi import APIRouter, HTTPException
from models.schemas import ConfiguracaoUsuario, RespostaDaBusca
from services.controlador_principal import executar_motor_ao_vivo
from database.db import atualizar_configuracao_bd

router = APIRouter(prefix="/editais", tags=["Motor de Busca"])


@router.post("/configurar")
async def salvar_configuracoes(dados: ConfiguracaoUsuario):
    try:
        sucesso = atualizar_configuracao_bd(dados.user_id, dados.dict())
        if sucesso:
            return {"status": "sucesso", "mensagem": "Radar configurado. O robô já sabe o que procurar."}
        raise HTTPException(status_code=500, detail="Falha ao persistir dados no banco.")

    except HTTPException:
        raise
    except Exception as erro:
        print(f"[API] Falha no endpoint /configurar: {erro}")
        raise HTTPException(status_code=500, detail="Erro interno no servidor de banco de dados.")


@router.post("/varredura-ao-vivo", response_model=RespostaDaBusca)
async def iniciar_varredura_manual(dados: ConfiguracaoUsuario):
    """
    Endpoint acionado pelo botão "Buscar Agora" no dashboard.
    Não salva no banco — apenas roda os motores e devolve para a tela.
    """
    if not dados.target_sites:
        raise HTTPException(status_code=400, detail="A lista de sites monitorados está vazia.")

    print(f"\n[API] Requisição de Varredura Ao Vivo recebida para o usuário: {dados.user_id}")

    try:
        brutos, aprovados = executar_motor_ao_vivo(
            user_id=dados.user_id,
            sites=dados.target_sites,
            prompt_perfil=dados.prompt_perfil
        )

        return {
            "status": "sucesso",
            "estatisticas": {
                "total_extraido_dos_sites": len(brutos),
                "total_aprovados_pela_ia": len(aprovados)
            },
            "resultados_aprovados": aprovados,
            "logs_brutos": brutos
        }

    except Exception as erro:
        print(f"[API] Falha crítica durante a execução do motor ao vivo: {erro}")
        raise HTTPException(status_code=500, detail=str(erro))