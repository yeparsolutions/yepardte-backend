# app/models/models.py
import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    String, Integer, BigInteger, Boolean, DateTime,
    ForeignKey, LargeBinary, Text, Enum as SAEnum
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


def now_utc():
    return datetime.now(timezone.utc)


class Empresa(Base):
    __tablename__ = "empresas"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    nombre: Mapped[str] = mapped_column(String(200))
    rut: Mapped[str] = mapped_column(String(12), unique=True, index=True)
    giro: Mapped[str] = mapped_column(String(300))
    direccion: Mapped[str] = mapped_column(String(300))
    comuna: Mapped[str] = mapped_column(String(100))
    ciudad: Mapped[str] = mapped_column(String(100))

    firma_digital: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    firma_password: Mapped[str | None] = mapped_column(String(500), nullable=True)
    firma_vencimiento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    caf_boleta: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    caf_factura: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    plan: Mapped[str] = mapped_column(String(20), default="gratuito")
    docs_usados: Mapped[int] = mapped_column(Integer, default=0)
    mp_suscripcion_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    tributario_completo: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    usuarios: Mapped[list["Usuario"]] = relationship("Usuario", back_populates="empresa", cascade="all, delete-orphan")
    documentos: Mapped[list["Documento"]] = relationship("Documento", back_populates="empresa", cascade="all, delete-orphan")
    pagos: Mapped[list["Pago"]] = relationship("Pago", back_populates="empresa", cascade="all, delete-orphan")


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    empresa_id: Mapped[str] = mapped_column(ForeignKey("empresas.id"), index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(500), nullable=True)
    pin_hash: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rol: Mapped[str] = mapped_column(String(20), default="vendedor")
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    # ── Verificación de email ─────────────────────────────────────────────────
    # Analogía: el casillero del correo — el usuario no puede entrar hasta
    # que demuestre que tiene la llave (código en su email)
    email_verificado: Mapped[bool] = mapped_column(Boolean, default=False)

    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    empresa: Mapped["Empresa"] = relationship("Empresa", back_populates="usuarios")
    documentos: Mapped[list["Documento"]] = relationship("Documento", back_populates="vendedor")


class CodigoVerificacion(Base):
    """
    Almacena códigos OTP temporales para verificar emails al registrarse.
    Analogía: el ticket numerado de la panadería — tiene un número,
    pertenece a alguien, y expira después de un tiempo.
    """
    __tablename__ = "codigos_verificacion"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(200), index=True)
    codigo: Mapped[str] = mapped_column(String(6))
    expira_en: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    usado: Mapped[bool] = mapped_column(Boolean, default=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class Documento(Base):
    __tablename__ = "documentos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    empresa_id: Mapped[str] = mapped_column(ForeignKey("empresas.id"), index=True)
    vendedor_id: Mapped[str | None] = mapped_column(ForeignKey("usuarios.id"), nullable=True)

    tipo: Mapped[str] = mapped_column(String(50))
    tipo_code: Mapped[str] = mapped_column(String(5))
    numero: Mapped[str] = mapped_column(String(20))
    folio: Mapped[int | None] = mapped_column(Integer, nullable=True)

    receptor_nombre: Mapped[str] = mapped_column(String(200))
    receptor_rut: Mapped[str] = mapped_column(String(12))
    receptor_email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    receptor_direccion: Mapped[str | None] = mapped_column(String(300), nullable=True)
    receptor_giro: Mapped[str | None] = mapped_column(String(300), nullable=True)

    monto_neto: Mapped[int] = mapped_column(BigInteger, default=0)
    monto_iva: Mapped[int] = mapped_column(BigInteger, default=0)
    monto_total: Mapped[int] = mapped_column(BigInteger, default=0)

    items: Mapped[str] = mapped_column(Text, default="[]")
    estado: Mapped[str] = mapped_column(String(30), default="pendiente")

    xml_firmado: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    track_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sii_response: Mapped[str | None] = mapped_column(Text, nullable=True)

    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    empresa: Mapped["Empresa"] = relationship("Empresa", back_populates="documentos")
    vendedor: Mapped["Usuario | None"] = relationship("Usuario", back_populates="documentos")


class Pago(Base):
    __tablename__ = "pagos"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    empresa_id: Mapped[str] = mapped_column(ForeignKey("empresas.id"), index=True)
    mp_payment_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    mp_suscripcion_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    plan: Mapped[str] = mapped_column(String(20))
    monto: Mapped[int] = mapped_column(Integer, default=0)
    tipo: Mapped[str] = mapped_column(String(20), default="unico")
    estado: Mapped[str] = mapped_column(String(20), default="pendiente")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    empresa: Mapped["Empresa"] = relationship("Empresa", back_populates="pagos")


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    empresa_id: Mapped[str] = mapped_column(ForeignKey("empresas.id"), index=True)
    rut: Mapped[str] = mapped_column(String(12), index=True)
    nombre: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    giro: Mapped[str | None] = mapped_column(String(300), nullable=True)
    direccion: Mapped[str | None] = mapped_column(String(300), nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc, nullable=True)
