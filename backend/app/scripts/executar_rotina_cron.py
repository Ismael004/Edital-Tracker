"""
executar_rotina_cron.py — Ponto de entrada único para o CRON externo.
NÃO depende do servidor FastAPI estar no ar — roda como processo standalone.
Chame isso via crontab, nunca via BackgroundScheduler dentro do main.py.
"""

import sys
import os
import logging

# Sobe um nível (de scripts/ para a raiz do projeto) para achar os módulos
# tasks/, api/, services/, etc.
RAIZ_PROJETO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(RAIZ_PROJETO)

os.makedirs(os.path.join(RAIZ_PROJETO, "logs"), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(RAIZ_PROJETO, "logs", "execucao_cron.log"), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ]
)

from tasks.rotinas import rotina_diaria_de_buscas

if __name__ == "__main__":
    logging.info("=== Início da execução via CRON ===")
    try:
        rotina_diaria_de_buscas()
    except Exception as erro:
        logging.error(f"FALHA NÃO TRATADA na rotina diária: {erro}", exc_info=True)
    logging.info("=== Fim da execução via CRON ===\n")