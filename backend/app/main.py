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
from database.db import iniciar_banco, edital_ja_processado, salvar_edital
from ai.filter import analisar_editais
from notifications.email_notifier import enviar_relatorio_email

load_dotenv()
meu_email = os.getenv("MEU_EMAIL")

def rotina_diaria_de_buscas():
    print("Iniciando a varredura automática nos bastidores...")

    usuario_exemplo = {
        "email": meu_email,
        "prompt": "Engenharia Elétrica, bolsas, estágios, inovação e tecnologia.",
        "sites": ["https://sobral.ufc.br/", "https://prae.ufc.br/pt/"]
    }

    iniciar_banco()
    editais_ineditos = []

    for site in usuario_exemplo["sites"]:
        print(f"Acessando: {site}...")
        editais = buscar_editais_em_qualquer_site(site)

        for e in editais:
            titulo = e.get('título', e.get('titulo', ''))
            link = e.get('link', '')

            if titulo and link and not edital_ja_processado(link):
                e['fonte'] = site
                editais_ineditos.append(e)

    if not editais_ineditos:
        print("Nenhum edital inédito encontrado hoje.")
        return

    print(f"Encontrados {len(editais_ineditos)} editais inéditos. Analisando com a IA...")
    editais_aprovados = analisar_editais(editais_ineditos)

    if editais_aprovados:
        print(f"A IA selecionou {len(editais_aprovados)} editais relevantes. Enviando e-mail...")
        sucesso = enviar_relatorio_email(editais_aprovados, modo_sem_ia=False)

        if sucesso:
            for edital in editais_ineditos:
                salvar_edital(edital['link'])

    print("E-mail enviado com sucesso e progresso salvo no banco de dados.")

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
    print(f"Configuração recebidas para o usuário {config.usuario_id}")
    return {"status": "sucesso", "mensagem": "Configurações salvas (MOCK)"}

@app.post("/api/v1/buscar-agora", tags=["Core System"])
def forcar_busca_imediata(config: Configuracao_Usuario):
    print(f"Iniciando varredura ON-DEMAND para {config.usuario_id}...")
    iniciar_banco()
    editais_encontrados = []

    for site_url in config.sites_monitorados:
        print(f"Lendo: {site_url}")
        editais = buscar_editais_em_qualquer_site(site_url)
        if editais:
            for e in editais:
                e['fonte'] = site_url

            editais_encontrados.extends(editais)

    if not editais_encontrados:
        return {"status": "alerta", "mensagem": "Nenhum edital encontrado nesses sites hoje."}

    print(f"Analisando {len(editais_encontrados)} oportunidades no Gemini...")
    editais_aprovados = analisar_editais(editais_encontrados)
    
    return {
        "status": "sucesso",
        "quantidade_bruta": len(editais_encontrados),
        "quantidade_aprovada": len(editais_aprovados) if editais_aprovados else 0,
        "editais": editais_aprovados or []
    }

if __name__ == "__main__":
    print("Ligação a ignição do FastaAPI...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)