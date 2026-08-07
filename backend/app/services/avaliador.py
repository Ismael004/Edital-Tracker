import json
import os
from google import genai
from google.genai import types

# Lista de prioridade de modelos para mitigação de Rate Limit (Fallback em Cascata)
MODELOS_DISPONIVEIS = [
    'gemini-3.1-flash-lite',
    'gemini-3.5-flash-lite',
    'gemini-3.6-flash',
    'gemini-2.5-flash-lite'
]

def analisar_editais_ao_vivo(editais: list, perfil_usuario: str) -> list:
    # Validação estrita em tempo real engatilhada manualmente pelo usuário no dashboard
    if not editais:
        return []

    prompt_sistema = f"""Você é um filtro de testes em tempo real.
    O usuário está testando a raspagem de dados AGORA com este critério: "{perfil_usuario}"
    
    SUA MISSÃO:
    Seja IMPLACÁVEL. Rejeite qualquer item que não seja exatamente o que o usuário pediu.
    Não faça deduções lógicas (ex: se pediu Unicamp, rejeite Fuvest e Enem sumariamente).
    """
    
    return _processar_via_gemini(editais, prompt_sistema)

def analisar_editais_periodico(editais: list, perfil_usuario: str) -> list:
    # Curadoria estratégica rodando em background para compilação de relatórios diários
    if not editais:
        return []

    prompt_sistema = f"""Você é um curador de oportunidades e editais.
    Seu objetivo é montar o boletim diário para um usuário com este perfil: "{perfil_usuario}"
    
    SUA MISSÃO:
    Selecione os itens de maior valor para a carreira/estudos do usuário. 
    Rejeite lixo corporativo ou notícias inúteis, mas aprove oportunidades que claramente beneficiem o perfil descrito, mesmo que indiretamente.
    """
    
    return _processar_via_gemini(editais, prompt_sistema)

def _processar_via_gemini(editais: list, instrucao_base: str) -> list:
    # Abstração do motor cognitivo: compila o payload, aplica o fallback e força o JSON nativo
    texto_para_analise = "FRAGMENTOS EXTRAÍDOS DO SITE:\n"
    for item in editais:
        titulo = item.get('título', item.get('titulo', 'Sem título'))
        texto_para_analise += f"- {titulo} | Link: {item.get('link', '')}\n"

    prompt_estrutural = """
    RETORNO OBRIGATÓRIO:
    Devolva APENAS uma matriz (lista) JSON contendo os itens aprovados. 
    Cada objeto da lista DEVE ter exatamente as chaves: "titulo", "link", "justificativa".
    Não use formatação markdown, não escreva explicações antes ou depois.
    Se nada atender ao critério, devolva uma lista vazia: []
    """

    chave_api = os.getenv("GEMINI_API_KEY")
    if not chave_api:
        print("[SISTEMA] GEMINI_API_KEY não encontrada no ambiente.")
        return []
        
    client = genai.Client(api_key=chave_api)
    
    # Trava de hardware lógico do provedor para impossibilitar alucinações de formatação
    config_geracao = types.GenerateContentConfig(
        temperature=0.1,
        response_mime_type="application/json"
    )

    # Loop de resiliência: intercala modelos dinamicamente em caso de falha de cota ou rede
    for modelo in MODELOS_DISPONIVEIS:
        try:
            resposta = client.models.generate_content(
                model=modelo,
                contents=[instrucao_base, prompt_estrutural, texto_para_analise],
                config=config_geracao
            )

            # Extração limpa e garantida pela restrição prévia de MIME type
            resultados = json.loads(resposta.text)
            
            # Reconciliação do payload original: resgata a URL matriz do nó processado
            if resultados and isinstance(resultados, list):
                for r in resultados:
                    if not r.get('fonte'):
                        fonte_original = editais[0].get('fonte', 'Desconhecida')
                        for edital_bruto in editais:
                            if edital_bruto.get('link') == r.get('link'):
                                fonte_original = edital_bruto.get('fonte', 'Desconhecida')
                                break
                        r['fonte'] = fonte_original
            
            return resultados

        except Exception as erro:
            erro_str = str(erro).lower()
            if "429" in erro_str or "quota" in erro_str or "exhausted" in erro_str or "rate" in erro_str:
                print(f"[IA] Rate Limit ou cota esgotada no modelo {modelo}. Engatando fallback...")
                continue 
            else:
                print(f"[IA] Anomalia na inferência do modelo {modelo}: {erro}. Alternando rotas...")
                continue 
                
    print("[IA] FALHA CRÍTICA: Esgotamento total do pool de modelos. Abortando operação.")
    return []