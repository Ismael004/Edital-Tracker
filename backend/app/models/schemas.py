from pydantic import BaseModel, Field
from typing import List

class Configuracao_usuario(BaseModel):
    user_id: str
    email: str
    target_sites: List[str]
    prompt_perfil: str

class Edital_aprovado(BaseModel):
    titulo: str = Field(..., description = "O título da notícia ou oportunidade")
    link: str = Field(..., description = "A URL completa para acessar a oportunidade")
    justificativa: str = Field(..., description = "A explicação da IA do porquê isso é relevante")
    fonte: str = Field(..., description = "De qual site essa informação foi extraída")

class Resposta_da_busca(BaseModel):
    """Molde do pacote final que o servidor devolve para o Dashboard montar a tabela."""
    status: str
    quantidade_bruta: int
    quantidade_aprovada: int
    mensagem: str = ""
    editais: List[Edital_aprovado]