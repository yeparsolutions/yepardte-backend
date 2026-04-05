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
    # Tipos válidos del SII:
    # "39" = Boleta afecta IVA
    # "41" = Boleta exenta de IVA
    # "33" = Factura afecta IVA (o exenta si exento=True)
    # "56" = Nota de débito
    # "61" = Nota de crédito
    # "52" = Guía de despacho
    tipoCode: str
    exento: bool = False        # True → documento exento de IVA
    ivaIncluido: bool = False   # True → precio ingresado ya incluye IVA
    receptor: ReceptorDocumento
    items: List[ItemDocumento]
    vendedorNombre: Optional[str] = None
    condicionPago: Optional[str] = "Contado"
    # Montos pre-calculados por el frontend para consistencia
    montoNeto:    Optional[int] = None
    montoExento:  Optional[int] = None
    montoIva:     Optional[int] = None
    montoTotal:   Optional[int] = None

    @field_validator("tipoCode")
    @classmethod
    def tipo_valido(cls, v):
        validos = {"39", "41", "33", "56", "61", "52"}
        if v not in validos:
            raise ValueError(f"tipoCode debe ser uno de {validos}")
        return v

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
