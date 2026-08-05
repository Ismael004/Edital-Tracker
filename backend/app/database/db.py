import sqlite3
import os 

CAMINHO_DB = os.path.join(os.path.dirname(__file__), '..', '..', 'tracker.db')

def conectar():
    return sqlite3.connect(CAMINHO_DB)

def iniciar_banco():
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS editais_processados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            link TEXT UNIQUE NOT NULL,
            data_processamento TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    conexao.commit()
    conexao.close()

def edital_ja_processado(link):
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("SELECT id FROM editais_processados WHERE link = ?", (link,))
    resultado = cursor.fetchone()

    conexao.close()
    return resultado is not None

def salvar_edital(link):
    conexao = conectar()
    cursor = conexao.cursor()

    try:
        cursor.execute("INSERT INTO editais_processados (link) VALUES (?)", (link,))
        conexao.commit()
    except sqlite3.IntegrityError:
        pass
    finally:
        conexao.close()

if __name__ == "__main__":
    print("Iniciando o banco de dados...")
    iniciar_banco()
    print("✅ Banco de dados 'tracker.db' criado/verificado com sucesso na raiz do projeto!")
    
    
    link_falso = "https://sobral.ufc.br/edital-fake-999"
    
    print(f"\n1. O link falso já foi processado? -> {edital_ja_processado(link_falso)}")
    
    print("2. Salvando o link falso na memória...")
    salvar_edital(link_falso)
    
    print(f"3. E agora, o link falso já foi processado? -> {edital_ja_processado(link_falso)}")