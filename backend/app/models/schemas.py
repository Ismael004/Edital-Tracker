from pydantic import BaseModel, Field
from typing import List


class ConfiguracaoUsuario(BaseModel):
    user_id: str
    email: str
    target_sites: List[str]
    prompt_perfil: str


class EditalAprovado(BaseModel):
    titulo: str = Field(..., description="O título da notícia ou oportunidade")
    link: str = Field(..., description="A URL completa para acessar a oportunidade")
    # Default vazio em vez de obrigatório: se a IA devolver um item sem justificativa
    # (variação de resposta do modelo), a rota não quebra com erro 500 por causa disso.
    justificativa: str = Field(default="", description="A explicação da IA do porquê isso é relevante")
    fonte: str = Field(default="Desconhecido", description="De qual site essa informação foi extraída")


class Estatisticas(BaseModel):
    total_extraido_dos_sites: int
    total_aprovados_pela_ia: int


class RespostaDaBusca(BaseModel):
    """
    Molde do pacote que a rota /varredura-ao-vivo devolve para o dashboard montar a tabela.
    Alinhado com o que api/rotas.py de fato retorna (chaves resultados_aprovados,
    estatisticas.total_aprovados_pela_ia) — a versão anterior deste schema (editais,
    quantidade_aprovada) não batia com o dict real devolvido pela rota e nunca era
    usado como response_model, então nunca foi validado. Agora está conectado.
    """
    status: str
    estatisticas: Estatisticas
    resultados_aprovados: List[EditalAprovado]
    logs_brutos: List[dict] = Field(default_factory=list)


# Aliases para compatibilidade, caso algo no projeto ainda importe os nomes antigos
# com underscore. Remover depois de confirmar que nada mais referencia esses nomes.
Configuracao_usuario = ConfiguracaoUsuario
Edital_aprovado = EditalAprovado
Resposta_da_busca = RespostaDaBusca