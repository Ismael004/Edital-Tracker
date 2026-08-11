import sys
import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from api.rotas import router as rotas_editais

app = FastAPI(
    title="Edital Tracker",
    description="Motor multi-agentes estruturado em Service Layer.",
    version="3.1.0",
)

# CORS: sem allow_credentials, já que a comunicação é via JSON puro (sem cookies/sessão).
# Restrinja allow_origins aos domínios reais assim que o frontend tiver endereço fixo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# A MÁGICA ACONTECE AQUI: Adicionamos o prefixo "/api" para alinhar com a Vercel
app.include_router(rotas_editais, prefix="/api")


# Ajustamos a rota principal para também ficar dentro do guarda-chuva do /api
@app.get("/api", tags=["Health"])
def health_check():
    return {"status": "ok", "mensagem": "API operando perfeitamente com arquitetura modular!"}

if __name__ == "__main__":
    print("Ligando a ignição do FastAPI...")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)


# NÃO chame uvicorn.run(..., reload=True) aqui para produção.
# Em produção, suba via linha de comando:
#   uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
# --workers 1 evita múltiplas instâncias concorrentes desnecessárias para este volume
# de uso; aumente só se o tráfego do dashboard justificar.