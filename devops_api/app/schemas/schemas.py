# app/schemas.py

from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, List
from datetime import datetime


from typing import Optional
from pydantic import BaseModel, Field

# ----------------------------
# Utilisateur
# ----------------------------

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    is_admin: bool
    created_at: datetime

    class Config:
        orm_mode = True

# ----------------------------
# Session
# ----------------------------

class SessionCreate(BaseModel):
    request_text: str
    provider: Optional[str] = None
    description: Optional[str] = None

class SessionResponse(BaseModel):
    id: int
    state: str
    request_text: Optional[str]
    provider: Optional[str]
    created_at: datetime

    class Config:
        orm_mode = True

# ----------------------------
# AWS Credentials
# ----------------------------

class AWSCredentialsCreate(BaseModel):
    access_key_id: str = Field(..., min_length=16, max_length=128, alias="accessKeyId")
    secret_access_key: str = Field(..., min_length=16, max_length=128, alias="secretAccessKey")
    region: str = Field(default="us-east-1", min_length=2, max_length=50)
    
    class Config:
        populate_by_name = True

class AWSCredentialsResponse(BaseModel):
    configured: bool
    validated: Optional[bool] = None
    region: Optional[str] = None
    account_id: Optional[str] = None
    message: Optional[str] = None

    class Config:
        orm_mode = True

class AWSCredentialsUpdate(BaseModel):
    access_key_id: Optional[str] = Field(None, min_length=16, max_length=128, alias="accessKeyId")
    secret_access_key: Optional[str] = Field(None, min_length=16, max_length=128, alias="secretAccessKey")
    region: Optional[str] = Field(None, min_length=2, max_length=50)
    
    class Config:
        populate_by_name = True

# ----------------------------
# Intent (nouvelle logique)
# ----------------------------

class IntentCreate(BaseModel):
    session_id: int
    intent_type: str  # create, configure, audit, kubernetes
    prompt: str
    runtime: Optional[str] = "system"
    # On laisse le classifieur remplir ces champs côté backend (pas requis à la création)
    # configure_domain: Optional[str] = None
    # configure_mode: Optional[str] = None


class IntentResponse(BaseModel):
    id: int
    session_id: int
    intent_type: str
    prompt: str
    runtime: Optional[str]
    #  on expose en lecture
    configure_domain: Optional[str] = None
    configure_mode: Optional[str] = None
    created_at: datetime

    class Config:
        orm_mode = True


# ----------------------------
# Provider
# ----------------------------

class ProviderCreate(BaseModel):
    provider_name: str
    credentials: Dict[str, str]

class ProviderResponse(BaseModel):
    id: int
    provider_name: str
    credentials: Dict[str, str]
    created_at: datetime

    class Config:
        orm_mode = True

# ----------------------------
# Déploiement
# ----------------------------

class DeploymentResponse(BaseModel):
    id: int
    file_id: Optional[str]
    terraform_logs: Optional[str]
    ansible_logs: Optional[str]
    public_ip: Optional[str]
    created_at: datetime

    class Config:
        orm_mode = True

# ----------------------------
# Intent Detection (à garder si utile)
# ----------------------------

class IntentDetectionResponse(BaseModel):
    intent: str
    details: str

# ----------------------------
# Chat Message
# ----------------------------


class ChatMessageRequest(BaseModel):
    """
    Schéma officiel pour les messages de chat.
    
    Tous les champs ci-dessous sont OBLIGATOIRES pour un contrat valide.
    """
    session_id: int = Field(..., description="ID de la session (obligatoire)")
    chat_id: int = Field(..., description="ID du chat (obligatoire - voir POST /chats/start_chat)")
    
    # Default si le front l'oublie
    sender: str = Field(default="user", description="Expéditeur du message (ex: 'user')")
    
    # Accepte 'text' OU 'message' (validation_alias)
    text: str = Field(..., validation_alias="message", description="Contenu textuel du message")
    
    selected_instances: Optional[List[int]] = Field(None, description="IDs des instances sélectionnées (liste d'entiers)")
    action: Optional[str] = Field(None, description="Action spéciale (ex: confirm_instances)")
    
    class Config:
        populate_by_name = True





# ----------------------------
# Chat – Renommage
# ----------------------------

class RenameChatRequest(BaseModel):
    chat_id: int
    new_name: str



# ----------------------------
# Chat – Liste des chats
# ----------------------------

class ChatInfo(BaseModel):
    chat_id: int
    name: str
    session_id: int
    created_at: Optional[str]
    mode: Optional[str] = "dac"  # Mode du chat (free ou dac)

    class Config:
        orm_mode = True





# ----------------------------
# Fichiers générés
# ----------------------------

class GeneratedTerraformFileResponse(BaseModel):
    id: int
    session_id: Optional[int]
    user_id: int
    file_path: str
    created_at: datetime

    class Config:
        orm_mode = True

class GeneratedPlaybookResponse(BaseModel):
    id: int
    session_id: Optional[int]
    user_id: int
    file_path: str
    created_at: datetime

    class Config:
        orm_mode = True

class GeneratedAuditFileResponse(BaseModel):
    id: int
    session_id: Optional[int]
    user_id: int
    file_path: str
    created_at: datetime

    class Config:
        orm_mode = True

class GeneratedKubernetesManifestResponse(BaseModel):
    id: int
    session_id: Optional[int]
    user_id: int
    file_path: str
    created_at: datetime

    class Config:
        orm_mode = True

class GeneratedInventoryFileResponse(BaseModel):
    id: int
    session_id: Optional[int]
    user_id: int
    file_path: str
    created_at: datetime

    class Config:
        orm_mode = True

class GeneratedPrivateKeyResponse(BaseModel):
    id: int
    session_id: Optional[int]
    user_id: int
    file_path: str
    created_at: datetime

    class Config:
        orm_mode = True

# ----------------------------
# Admin – Utilisateur (avec is_admin)
# ----------------------------

class AdminUserResponse(BaseModel):
    id: int
    email: EmailStr
    is_admin: bool
    created_at: datetime

    class Config:
        orm_mode = True

class AdminDashboardStatsResponse(BaseModel):
    total_users: int
    total_admin_users: int
    total_sessions: int
    total_executions: int
    recent_users: List[AdminUserResponse]
    message: str

# ----------------------------
# Admin – Execution
# ----------------------------

class ExecutionResponse(BaseModel):
    id: int
    session_id: Optional[int]
    user_id: int
    task_type: str  # create / configure / audit / kubernetes
    status: str     # running / completed / failed
    extra_data: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True

# ----------------------------
# Admin – Execution Logs
# ----------------------------

class ExecutionLogResponse(BaseModel):
    id: int
    execution_id: int
    user_id: int
    event: str
    message: str
    created_at: datetime

    class Config:
        orm_mode = True
