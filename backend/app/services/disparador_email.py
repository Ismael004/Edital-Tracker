import smtplib
import os
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

def enviar_relatorio_email(destinatario: str, editais: list, modo_sem_ia: bool = False) -> bool:
    # Camada de Notificação: Constrói e despacha o payload via SMTP
    if not editais:
        print("[MENSAGEIRO] Operação abortada: Matriz de editais vazia.")
        return False
        
    email_remetente = os.getenv("EMAIL_REMETENTE")
    senha_app = os.getenv("SENHA_APP")
    
    if not email_remetente or not senha_app:
        print("[MENSAGEIRO] Falha crítica: Credenciais de SMTP ausentes no ambiente.")
        return False

    msg = EmailMessage()
    
    # Roteamento Dinâmico: O destinatário agora é injetado pelo Controlador Principal
    msg['From'] = email_remetente
    msg['To'] = destinatario
    
    if modo_sem_ia:
        msg['Subject'] = f"[SISTEMA] {len(editais)} Novos Editais (IA Indisponível)"
    else:
        msg['Subject'] = f"Edital Tracker: {len(editais)} Novas Oportunidades Encontradas"
        
    # Construção do Esqueleto HTML (Template Base)
    cor_tema = "#ea4335" if modo_sem_ia else "#0b57d0"
    titulo_email = "Alerta de Sistema (Modo Simples)" if modo_sem_ia else "Radar de Oportunidades"
    subtitulo = "Ocorreu um erro no motor de IA, mas aqui estão os links brutos:" if modo_sem_ia else "A nossa inteligência filtrou as publicações e separou o que tem impacto real para você:"
    
    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: {cor_tema}; border-bottom: 2px solid {cor_tema}; padding-bottom: 10px;">{titulo_email}</h2>
        <p style="font-size: 14px; color: #555;">{subtitulo}</p>
        <div style="margin-top: 20px;">
    """
    
    texto_puro = f"{titulo_email}\n{'-'*30}\n\n"
    
    # Injeção Dinâmica dos Blocos de Conteúdo
    for edital in editais:
        titulo = edital.get('titulo', edital.get('título', 'Sem Título'))
        link = edital.get('link', '#')
        
        if modo_sem_ia:
            # Layout minimalista de contingência (Apenas links)
            html_content += f'<p>🔹 <a href="{link}" style="color: #1a73e8; text-decoration: none;">{titulo}</a></p>'
            texto_puro += f"- {titulo}\n  Link: {link}\n\n"
        else:
            # Layout rico com análise cognitiva da IA
            justificativa = edital.get('justificativa', 'Relevante para o seu perfil.')
            fonte = edital.get('fonte', 'Host Desconhecido')
            
            html_content += f"""
            <div style="margin-bottom: 25px; padding-bottom: 15px; border-bottom: 1px solid #eee;">
                <h3 style="margin: 0 0 8px 0; font-size: 16px;">
                    <a href="{link}" style="color: #1a73e8; text-decoration: none;">{titulo}</a>
                </h3>
                <span style="display: inline-block; background: #e8f0fe; color: #1967d2; font-size: 11px; padding: 3px 8px; border-radius: 12px; margin-bottom: 10px;">
                    Fonte: {fonte}
                </span>
                <p style="margin: 0; padding: 10px; background-color: #f8f9fa; border-left: 4px solid #34a853; font-size: 13px; color: #444;">
                    <strong>💡 Inteligência:</strong> {justificativa}
                </p>
            </div>
            """
            texto_puro += f"- {titulo}\n  Fonte: {fonte}\n  Motivo: {justificativa}\n  Link: {link}\n\n"
            
    html_content += """
        </div>
        <p style="font-size: 11px; color: #999; text-align: center; margin-top: 30px;">
            Enviado automaticamente por Edital Tracker Engine
        </p>
      </body>
    </html>
    """
    
    # Anexando os pacotes na mensagem SMTP
    msg.set_content(texto_puro)
    msg.add_alternative(html_content, subtype='html')
    
    try:
        print(f"[MENSAGEIRO] Despachando pacote para {destinatario}...")
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(email_remetente, senha_app)
            smtp.send_message(msg)
        print("[MENSAGEIRO] Sucesso: Operação de entrega concluída.")
        return True
    except Exception as erro:
        print(f"[MENSAGEIRO] Falha catastrófica no túnel SMTP: {erro}")
        return False