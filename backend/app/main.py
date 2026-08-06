import sys
import os
import uvicorn

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from apscheduler.schedulers.background import BackgroundScheduler

from dotenv import load_dotenv
from scraper.smart_scraper import buscar_editais_em_qualquer_site
from ai.filter import analisar_editais
from notifications.email_notifier import enviar_relatorio_email
from database.db import obter_todas_configuracoes_ativas, salvar_oportunidade, edital_ja_processado_para_usuario

load_dotenv()
meu_email = os.getenv("MEU_EMAIL")

def executar_motor_core(user_id: str, sites: list[str]) -> tuple[list, list]:

    editais_ineditos = []
    
    for site_url in sites:
        print(f"[{user_id}] Lendo: {site_url}")
        editais = buscar_editais_em_qualquer_site(site_url)
        if editais:
            for e in editais:
                titulo = e.get('título', e.get('titulo', ''))
                link = e.get('link', '')
                if titulo and link and not edital_ja_processado_para_usuario(user_id, link):
                    e['fonte'] = site_url
                    editais_ineditos.append(e)
                    
    editais_aprovados = []
    if editais_ineditos:
        print(f"[{user_id}] Analisando {len(editais_ineditos)} oportunidades na IA...")
        editais_aprovados = analisar_editais(editais_ineditos) or []
        
    return editais_ineditos, editais_aprovados

def rotina_diaria_de_buscas():
    print("Iniciando a varredura automática (APScheduler)...")
    
    usuarios_ativos = obter_todas_configuracoes_ativas()

    if not usuarios_ativos:
        print("Nenhum usuário ativo encontrado no banco.")
        return

    for config in usuarios_ativos:
        user_id = config.get('user_id')
        sites = config.get('target_sites', [])
        
        print(f"\n--- Iniciando ciclo para: {user_id} ---")
        
        ineditos, aprovados = executar_motor_core(user_id, sites)

        if not ineditos:
            print(f"[{user_id}] Tudo silencioso. Nenhum edital novo.")
            continue

        if aprovados:
            print(f"[{user_id}] IA aprovou {len(aprovados)}. Preparando e-mail...")
            sucesso = enviar_relatorio_email(aprovados, modo_sem_ia=False)

            if sucesso:
                for edital in ineditos:
                    salvar_oportunidade(user_id, edital)
                print(f"[{user_id}] E-mail enviado. Progresso salvo.")
        else:
             print(f"[{user_id}] IA rejeitou todos os {len(ineditos)} novos editais.")
             # Salva no banco para não processar de novo amanhã
             for edital in ineditos:
                  salvar_oportunidade(user_id, edital)

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Iniciando o relógio do piloto automático. Liga e desliga...")
    scheduler = BackgroundScheduler()
    scheduler.add_job(rotina_diaria_de_buscas,'cron', hour=8, minute = 0)
    scheduler.start()

    yield

    print("Desligando o relógio do piloto automático...")
    scheduler.shutdown()

app = FastAPI(
    title="Edital Tracker",
    description="Motor multi-agentes para rastreio e análise de oportunidades.",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Configuracao_Usuario(BaseModel):
    usuario_id: str
    prompt_perfil: str
    sites_monitorados: List[str]
    email_notificaticao: str

@app.get("/", tags=["Health"])
def health_check():
    return {"status": "ok", "mensagem": "Motor do Edital Tracker rodando a todo vapor!"}

@app.post("/api/configuracoes", tags=["Configuração"])
def salvar_configuracoes(config: Configuracao_Usuario):
    print(f"Configuração recebida para o usuário {config.usuario_id}")
    return {"status": "sucesso", "mensagem": "Configurações salvas (MOCK)"}

@app.post("/api/v1/buscar-agora", tags=["Core System"])
def forcar_busca_imediata(config: Configuracao_Usuario):
    print(f"\n--- Iniciando varredura ON-DEMAND para {config.usuario_id} ---")
    
    ineditos, aprovados = executar_motor_core(config.usuario_id, config.sites_monitorados)

    if not ineditos:
        return {"status": "alerta", "mensagem": "Nenhum edital inédito encontrado nesses sites hoje.", "editais": []}
    
    for edital in ineditos:
        salvar_oportunidade(config.usuario_id, edital)
    
    return {
        "status": "sucesso",
        "quantidade_bruta": len(ineditos),
        "quantidade_aprovada": len(aprovados),
        "editais": aprovados
    }

if __name__ == "__main__":
    print("Ligando a ignição do FastAPI...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


