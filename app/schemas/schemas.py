# app/schemas/schemas.py
from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List
from datetime import datetime


# ── Auth ──────────────────────────────────────────────────────
class LoginAdmin(BaseModel):
    email: EmailStr
    password: str


class LoginVendedor(BaseModel):
    adminRut: str
    pin: str


class RegistroEmpresa(BaseModel):
    nombre: str
    rut: str
    giro: str
    direccion: str
    comuna: str
    ciudad: str
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    token: str
    usuario: dict


# ── Empresa ───────────────────────────────────────────────────
class EmpresaUpdate(BaseModel):
    nombre: Optional[str] = None
    giro: Optional[str] = None
    direccion: Optional[str] = None
    comuna: Optional[str] = None
    ciudad: Optional[str] = None


class EmpresaOut(BaseModel):
    id: str
    nombre: str
    rut: str
    giro: str
    direccion: str
    comuna: str
    ciudad: str
    plan: str
    docs_usados: int
    tributario_completo: bool
    firma_vencimiento: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Vendedores ────────────────────────────────────────────────
class VendedorCreate(BaseModel):
    nombre: str
    pin: str

    @field_validator("pin")
    @classmethod
    def pin_largo(cls, v):
        if len(v) < 4:
            raise ValueError("El PIN debe tener al menos 4 dígitos")
        return v


class VendedorOut(BaseModel):
    id: str
    nombre: str
    creado_en: datetime

    class Config:
        from_attributes = True


# ── Documentos ────────────────────────────────────────────────
class ItemDocumento(BaseModel):
    nombre: str
    precio: int
    qty: int


class ReceptorDocumento(BaseModel):
    nombre: str
    rut: str
    email: Optional[str] = None
    direccion: Optional[str] = None
    giro: Optional[str] = None


class EmitirDocumento(BaseModel):
    tipoCode: str           # "39" boleta | "33" factura
    receptor: ReceptorDocumento
    items: List[ItemDocumento]
    vendedorNombre: Optional[str] = None


class DocumentoOut(BaseModel):
    id: str
    tipo: str
    tipo_code: str
    numero: str
    folio: Optional[int]
    receptor_nombre: str
    receptor_rut: str
    monto_neto: int
    monto_iva: int
    monto_total: int
    estado: str
    fecha: datetime
    track_id: Optional[str] = None

    class Config:
        from_attributes = True


# ── Config ────────────────────────────────────────────────────
class ConexionToggle(BaseModel):
    activa: bool
