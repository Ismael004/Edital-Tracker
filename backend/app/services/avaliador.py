import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from google import genai
from google.genai import types

# Lista de prioridade de modelos para mitigação de Rate Limit (Fallback em Cascata)
# ATENÇÃO: valide estes nomes na documentação oficial do Gemini antes de subir para
# produção — nomes de modelo inexistentes queimam tentativas e tempo no loop de fallback.
MODELOS_DISPONIVEIS = [
    'gemini-3.1-flash-lite',
    'gemini-3.5-flash-lite',
    'gemini-3.6-flash',
    'gemini-2.5-flash-lite'
]

TAMANHO_LOTE_PADRAO = 50   # itens por chamada — evita truncamento de JSON e perda de precisão
MAX_WORKERS_PADRAO = 5     # lotes processados em paralelo
TIMEOUT_REQUISICAO_SEGUNDOS = 30


# ============================================================
# FUNÇÕES PÚBLICAS — mantidas como pontos de entrada do sistema
# ============================================================

def analisar_editais_ao_vivo(editais: list, perfil_usuario: str) -> list:
    """
    Modo RÍGIDO — disparado manualmente pelo usuário no dashboard.
    Validação estrita em tempo real: zero inferência, zero tolerância a ambiguidade.
    """
    if not editais:
        return []

    prompt_sistema = f"""Você é um FILTRO LITERAL de correspondência exata, operando em tempo real para um teste manual do usuário.

CRITÉRIO EXATO DO USUÁRIO (não parafraseie, não reinterprete): "{perfil_usuario}"

REGRAS INEGOCIÁVEIS:
1. Aprove SOMENTE itens que correspondam de forma DIRETA e EXPLÍCITA ao critério acima.
2. É PROIBIDO fazer inferência, generalização, associação temática ou dedução lógica.
   Exemplo: se o critério menciona "Unicamp", REJEITE itens sobre Fuvest, Enem, USP,
   vestibulares em geral ou qualquer instituição diferente — mesmo que pareçam relacionados.
3. Na dúvida entre aprovar e rejeitar, REJEITE. Falso negativo é aceitável; falso positivo não é.
4. Não amplie o escopo do critério com sinônimos, categorias mais amplas ou contexto que
   o usuário não escreveu explicitamente.
5. Ignore completamente relevância "de carreira" ou "de estudos" genérica — o único critério
   válido é a correspondência literal ao texto fornecido pelo usuário.

Sua tarefa é agir como um filtro determinístico: dado o mesmo input, o mesmo critério deve
sempre produzir o mesmo resultado. Não seja criativo. Não seja útil além do que foi pedido.
"""

    return _processar_via_gemini(editais, prompt_sistema)

def analisar_editais_periodico(editais: list, perfil_usuario: str) -> list:
    """
    Modo CURADOR — roda em background para compilação de relatórios/boletins diários.
    Agora com a MESMA eficiência de captura do modo Ao Vivo, sem perda de dados.
    """
    if not editais:
        return []

    prompt_sistema = f"""Você é um filtro de correspondência exata encarregado de montar um boletim de oportunidades.

CRITÉRIO EXATO DO USUÁRIO (não parafraseie): "{perfil_usuario}"

REGRAS INEGOCIÁVEIS (ALTA EFICIÊNCIA):
1. Aprove TODOS os itens que correspondam de forma DIRETA e EXPLÍCITA ao critério acima. 
2. Se o edital tratar de bolsas, auxílios, assistência ou vagas aplicáveis ao curso/local do usuário, APROVE. Não deduza que o usuário não vai querer; deixe que ele decida.
3. REJEITE apenas lixo absoluto: cardápios, avisos de manutenção, atas de reunião, eventos passados ou chamadas de outras cidades/campi não relacionadas.
4. Cada item aprovado deve receber uma justificativa curta (1 frase) na chave "justificativa", explicando por que atende ao critério.

Sua tarefa é garantir que NENHUMA oportunidade válida fique de fora do boletim.
"""

    return _processar_via_gemini(editais, prompt_sistema)

# ============================================================
# NORMALIZAÇÃO E PARTICIONAMENTO
# ============================================================

def _normalizar_edital(item: dict) -> dict:
    return {
        "titulo": item.get('título', item.get('titulo', 'Sem título')),
        "link": item.get('link', ''),
        "fonte": item.get('fonte', 'Desconhecida')
    }


def _particionar_lista(itens: list, tamanho_lote: int):
    for i in range(0, len(itens), tamanho_lote):
        yield itens[i:i + tamanho_lote]


# ============================================================
# MOTOR COGNITIVO — batching paralelo + fallback em cascata
# ============================================================

def _montar_texto_lote(lote: list) -> str:
    linhas = [f"- {item['titulo']} | Link: {item['link']}" for item in lote]
    return "FRAGMENTOS EXTRAÍDOS DO SITE:\n" + "\n".join(linhas)


PROMPT_ESTRUTURAL = """
RETORNO OBRIGATÓRIO:
Devolva APENAS uma matriz (lista) JSON contendo os itens aprovados.
Cada objeto da lista DEVE ter exatamente as chaves: "titulo", "link", "justificativa".
Não use formatação markdown, não escreva explicações antes ou depois.
Se nada atender ao critério, devolva uma lista vazia: []
"""


def _chamar_gemini_com_fallback(client: genai.Client, instrucao_base: str, texto_lote: str) -> list:
    """
    Percorre a cascata de modelos até um responder com JSON válido no formato esperado.
    Retorna [] se todos falharem (nunca lança exceção para o chamador).
    """
    config_geracao = types.GenerateContentConfig(
        temperature=0.1,
        response_mime_type="application/json"
    )

    # É mais seguro concatenar o prompt em uma única string clara para a IA
    prompt_completo = f"{instrucao_base}\n\n{PROMPT_ESTRUTURAL}\n\n{texto_lote}"

    for modelo in MODELOS_DISPONIVEIS:
        try:
            resposta = client.models.generate_content(
                model=modelo,
                contents=prompt_completo,
                config=config_geracao
            )

            # CORREÇÃO: Limpeza robusta contra blocos de Markdown ("""json)
            texto_limpo = resposta.text.strip()
            if texto_limpo.startswith('```json'):
                texto_limpo = texto_limpo[7:]
            elif texto_limpo.startswith('```'):
                texto_limpo = texto_limpo[3:]
            if texto_limpo.endswith('```'):
                texto_limpo = texto_limpo[:-3]
            
            texto_limpo = texto_limpo.strip()

            resultados = json.loads(texto_limpo)

            # Validação de shape: garante que é lista, não dict/None/string
            if not isinstance(resultados, list):
                print(f"[IA] Modelo {modelo} retornou formato inesperado ({type(resultados).__name__}), tentando próximo...")
                continue

            return resultados

        except json.JSONDecodeError as erro:
            print(f"[IA] JSON malformado do modelo {modelo}: {erro}. Alternando rotas...")
            continue
        except Exception as erro:
            erro_str = str(erro).lower()
            eh_rate_limit = any(termo in erro_str for termo in ("429", "quota", "exhausted", "rate"))
            if eh_rate_limit:
                print(f"[IA] Rate limit / cota esgotada em {modelo}. Engatando fallback...")
            else:
                print(f"[IA] Anomalia na inferência do modelo {modelo}: {erro}. Alternando rotas...")
            continue

    print("[IA] FALHA CRÍTICA: Esgotamento total do pool de modelos para este lote.")
    return []


def _processar_lote(client: genai.Client, instrucao_base: str, lote: list, indice: int) -> list:
    texto_lote = _montar_texto_lote(lote)
    resultados = _chamar_gemini_com_fallback(client, instrucao_base, texto_lote)
    if resultados:
        print(f"[IA] Lote {indice + 1}: {len(resultados)} item(ns) aprovado(s).")
    return resultados


def _processar_via_gemini(
    editais: list,
    instrucao_base: str,
    tamanho_lote: int = TAMANHO_LOTE_PADRAO,
    max_workers: int = MAX_WORKERS_PADRAO
) -> list:
    chave_api = os.getenv("GEMINI_API_KEY")
    if not chave_api:
        print("[SISTEMA] GEMINI_API_KEY não encontrada no ambiente.")
        return []

    editais_normalizados = [_normalizar_edital(item) for item in editais]

    # Mapa O(1) para reconciliação de fonte — evita busca linear repetida
    mapa_fonte = {item['link']: item['fonte'] for item in editais_normalizados if item['link']}

    client = genai.Client(api_key=chave_api)
    lotes = list(_particionar_lista(editais_normalizados, tamanho_lote))

    print(f"[IA] {len(editais_normalizados)} itens em {len(lotes)} lote(s), processando em paralelo (max {max_workers} workers)...")

    resultados_finais = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futuros = {
            executor.submit(_processar_lote, client, instrucao_base, lote, i): i
            for i, lote in enumerate(lotes)
        }
        for futuro in as_completed(futuros):
            indice = futuros[futuro]
            try:
                resultados_finais.extend(futuro.result())
            except Exception as erro:
                print(f"[IA] Falha inesperada no lote {indice + 1}: {erro}")

    # Reconciliação O(1): resgata a fonte original de cada item aprovado
    for r in resultados_finais:
        if not r.get('fonte'):
            r['fonte'] = mapa_fonte.get(r.get('link'), 'Desconhecida')

    return resultados_finais
