from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Categoria = Literal[
    "manutencao", "barulho", "duvida", "encomenda", "financeiro", "seguranca", "reclamacao", "outros"
]
Prioridade = Literal["baixa", "media", "alta", "critica"]
Setor = Literal["zeladoria", "portaria", "administracao", "sindico"]
Sentimento = Literal["positivo", "neutro", "negativo"]
Acao = Literal["responder_automaticamente", "abrir_chamado", "emergencia"]
Status = Literal["aberto", "em_andamento", "resolvido"]
# De onde veio a análise: perguntas frequentes, resposta já dada antes, ou o modelo de IA
Origem = Literal["faq", "cache", "ia"]


class MensagemEntrada(BaseModel):
    """O que o morador envia (via n8n)."""

    texto: str = Field(..., min_length=1, max_length=4000, examples=["Tem água vazando no teto da garagem, perto da vaga 12"])
    morador: str = Field("Morador", max_length=120, examples=["Ana Souza"])
    apartamento: Optional[str] = Field(None, max_length=20, examples=["302B"])
    canal: str = Field("webhook", max_length=30, examples=["telegram"])
    # Opcional: áudio ou foto em base64 (só funciona com o provedor gemini)
    anexo_base64: Optional[str] = None
    anexo_mime: Optional[str] = Field(None, examples=["audio/ogg", "image/jpeg"])


class AnaliseIA(BaseModel):
    """Formato que a IA é obrigada a devolver. Tudo que vier fora disso é rejeitado."""

    categoria: Categoria
    prioridade: Prioridade
    setor: Setor
    sentimento: Sentimento
    resumo: str = Field(..., max_length=300, description="Uma frase descrevendo o pedido")
    resposta_morador: str = Field(..., max_length=1200, description="Mensagem a ser enviada ao morador")
    respondido_pelo_regimento: bool = Field(..., description="True se a resposta resolve a dúvida usando a base do FAQ")
    fontes: list[str] = Field(default_factory=list, max_length=5, description="Ids das entradas do FAQ usadas na resposta")
    trecho_regimento: Optional[str] = Field(None, max_length=500, description="Trecho do regimento usado")
    transcricao_anexo: Optional[str] = Field(None, max_length=2000, description="Transcrição do áudio ou descrição da foto")
    confianca: float = Field(..., ge=0, le=1)


TipoEvento = Literal[
    "mensagem_morador",   # o que o morador escreveu
    "analise",            # o que a IA (ou o FAQ/cache) concluiu
    "resposta_morador",   # o que foi enviado de volta ao morador
    "alerta_setor",       # a notificação que o setor recebeu
    "status",             # assumido, resolvido, reaberto
    "nota_interna",       # anotação da equipe, o morador não vê
    "encaminhamento",     # troca de setor
    "prioridade",         # troca de prioridade
]


class Evento(BaseModel):
    id: int
    chamado_id: int
    criado_em: datetime
    tipo: TipoEvento
    autor: str
    destino: Optional[str] = None
    texto: str
    dados: dict = {}


class Chamado(BaseModel):
    id: int
    criado_em: datetime
    atualizado_em: datetime
    morador: str
    apartamento: Optional[str]
    canal: str
    texto: str
    acao: Acao
    status: Status
    analise: AnaliseIA
    regra_seguranca_aplicada: bool = False
    origem: Origem = "ia"
    # Estado atual (pode mudar depois da análise: encaminhamento, troca de prioridade)
    setor: Setor
    prioridade: Prioridade
    responsavel: Optional[str] = None
    resolvido_em: Optional[datetime] = None
    prazo_em: datetime
    atrasado: bool = False


class AtualizarStatus(BaseModel):
    status: Status
    responsavel: Optional[str] = Field(None, max_length=80)
    nota: Optional[str] = Field(None, max_length=1000, description="Obrigatória ao resolver: o que foi feito")


class NovaInteracao(BaseModel):
    tipo: Literal["resposta_morador", "nota_interna", "mensagem_morador"]
    autor: str = Field(..., min_length=1, max_length=80)
    texto: str = Field(..., min_length=1, max_length=2000)


class Encaminhar(BaseModel):
    setor: Setor
    autor: str = Field(..., min_length=1, max_length=80)
    motivo: Optional[str] = Field(None, max_length=500)


class MudarPrioridade(BaseModel):
    prioridade: Prioridade
    autor: str = Field(..., min_length=1, max_length=80)
    motivo: Optional[str] = Field(None, max_length=500)


class ResumoDiario(BaseModel):
    data: str
    total_chamados: int
    resumo: str
    destaques: list[str]
    pendencias_criticas: int
