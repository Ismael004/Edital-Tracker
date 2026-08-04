import smtplib
from email.message import EmailMessage
import os
from dotenv import load_dotenv

load_dotenv()

def enviar_email(titulo_edital, link_edital, destinatario):
    email_remetente = os.getenv("EMAIL_REMETENTE")
    senha_app = os.getenv("SENHA_APP")

    if not email_remetente or not senha_app:
        print("Email ou senha incorretos. Verifique as variáveis de ambiente.")
        return False

    msg = EmailMessage()
    msg['Subject'] = f'Novo edital publicado: {titulo_edital}'
    msg['From'] = email_remetente
    msg['To'] = destinatario

    corpo_email = f"""
    Olá!
    
    O Edital-Tracker passou pelo site da UFC e encontrou algo que tem alta probabilidade de te interessar:
    
    📌 Título: {titulo_edital}
    🔗 Acessar documento completo: {link_edital}
    
    Este é um email automático enviado pelo seu bot.
    """

    msg.set_content(corpo_email)
    try:
        print(f"Enviando email para {destinatario}...")
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(email_remetente, senha_app)
            print("Email enviado com sucesso")
            return True
    except Exception as erro:
        print(f"Erro ao enviar email: {erro}")
        return False