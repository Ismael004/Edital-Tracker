import smtplib
from email.message import EmailMessage
import os
from dotenv import load_dotenv

load_dotenv()

def enviar_relatorio_email(editais, modo_sem_ia = False):
    if not editais:
        print("Nenhum edital para enviar.")
        return False

    email_remetente = os.getenv("EMAIL_REMETENTE")
    senha_app = os.getenv("SENHA_APP")

    if not email_remetente or not senha_app:
        print("Email ou senha incorretos. Verifique as variáveis de ambiente.")
        return False

    msg = EmailMessage()
    if modo_sem_ia:
        msg['Subject'] = f"[SISTEMA] {len(editais)} novas notícias (Sem IA justificativa)"
    else:
        msg['Subject'] = f" Edital Tracker: {len(editais)} novas notícias"
    msg['From'] = email_remetente
    msg['To'] = "ismaelsilvaalmeida257@gmail.com"

    if not modo_sem_ia:
        html_content = """
        <html>
          <body style="font-family: Arial, sans-serif; color: #333;">
            <h2 style="color: #0b57d0;">Resumo de Oportunidades - UFC</h2>
            <p>A Inteligência Artificial filtrou os editais mais recentes e separou o que faz sentido para o seu perfil.</p>
            <hr style="border: 1px solid #eee;">
        """
        
        for edital in editais:
            titulo = edital.get('titulo', edital.get('título', 'Sem Título'))
            justificativa = edital.get('justificativa', 'Relevante para o perfil.')
            
            html_content += f"""
            <div style="margin-bottom: 20px;">
                <h3 style="margin-bottom: 5px;">
                    <a href="{edital.get('link', '#')}" style="color: #1a73e8; text-decoration: none;">{titulo}</a>
                </h3>
                <p style="margin-top: 0; padding: 10px; background-color: #f8f9fa; border-left: 4px solid #34a853;">
                    <strong> Por que ler?</strong> {justificativa}
                </p>
            </div>
            """
    
    else:
        html_content = """
        <html>
          <body style="font-family: Arial, sans-serif; color: #333;">
            <h2 style="color: #ea4335;">Alerta de Oportunidades - Modo Simples</h2>
            <p>Ocorreu um erro ao consultar o assistente de Inteligência Artificial hoje, mas aqui estão os novos editais publicados na UFC:</p>
            <hr style="border: 1px solid #eee;">
            <ul>
        """
        
        for edital in editais:
            titulo = edital.get('título', 'Edital Sem Título')
            link = edital.get('link', '#')
            
            html_content += f"""
                <li style="margin-bottom: 10px;">
                    <a href="{link}" style="color: #1a73e8; text-decoration: none;">{titulo}</a>
                </li>
            """
        html_content += "</ul>"
        
    html_content += """
        <hr style="border: 1px solid #eee;">
        <p style="font-size: 12px; color: #888;">Este é um e-mail automático gerado pelo seu Edital Tracker.</p>
      </body>
    </html>
    """
    
    texto_puro = "Resumo de Editais Relevantes:\n\n"
    for edital in editais:
        titulo = edital.get('titulo', edital.get('título', 'Sem Título'))
        texto_puro += f"- {titulo}\n"
        if not modo_sem_ia:
             texto_puro += f"  Motivo: {edital.get('justificativa', '')}\n"
        texto_puro += f"  Link: {edital.get('link', '#')}\n\n"
        
    msg.set_content(texto_puro)
    msg.add_alternative(html_content, subtype='html')
    
    try:
        print(f"Enviando relatório unificado (Modo IA: {not modo_sem_ia}) por e-mail...")
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(email_remetente, senha_app)
            smtp.send_message(msg)
            print("E-mail enviado com sucesso!")
            return True
    except Exception as erro:
        print(f"Falha ao enviar o e-mail: {erro}")
        return False