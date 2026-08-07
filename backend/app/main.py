import sys
import os
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.background import BackgroundScheduler

# Garante que o Python encontre a pasta raiz independentemente de onde o script for rodado
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Importa a rotina em background (Cron)
from tasks.rotinas import rotina_diaria_de_buscas
# Importa o roteador que criamos no arquivo api/rotas.py
from api.rotas import router as rotas_editais

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[SISTEMA] Iniciando o relógio do piloto automático (Cron)...")
    scheduler = BackgroundScheduler()
    # Configura a rotina matinal para varredura autônoma às 08:00
    scheduler.add_job(rotina_diaria_de_buscas, 'cron', hour=8, minute=0)
    scheduler.start()
    
    yield # O servidor fica rodando aqui
    
    print("[SISTEMA] Desligando o relógio do piloto automático...")
    scheduler.shutdown()

app = FastAPI(
    title="Edital Tracker",
    description="Motor multi-agentes estruturado em Service Layer.",
    version="3.0.0",
    lifespan=lifespan
)

# Configuração de Segurança (CORS) para permitir a conexão com o Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Acopla as rotas modularizadas. Toda a lógica da API agora vive no api/rotas.py
app.include_router(rotas_editais)

# Rota básica de Health Check
@app.get("/", tags=["Health"])
def health_check():
    return {"status": "ok", "mensagem": "API operando perfeitamente com arquitetura modular!"}

if __name__ == "__main__":
    print("Ligando a ignição do FastAPI...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)