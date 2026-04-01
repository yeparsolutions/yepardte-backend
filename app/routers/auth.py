# app/routers/auth.py
import uuid
import random
import string
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.models.models import Empresa, Usuario, CodigoVerificacion
from app.schemas.schemas import LoginAdmin, LoginVendedor, RegistroEmpresa, TokenResponse
from app.services.planes import PLANES
from app.services.email_service import enviar_email, template_codigo_verificacion

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _usuario_payload(user: Usuario, empresa: Empresa) -> dict:
    plan_info = PLANES.get(empresa.plan, PLANES["gratuito"])
    return {
        "id":                 user.id,
        "nombre":             empresa.nombre if user.rol == "admin" else user.nombre,
        "email":              user.email,
        "rut":                empresa.rut,
        "rol":                user.rol,
        "plan":               empresa.plan,
        "docsUsados":         empresa.docs_usados,
        "docsLimit":          plan_info["docsLimit"],
        "vendedoresLimit":    plan_info["vendedoresLimit"],
        "tributarioCompleto": empresa.tributario_completo,
    }


def _generar_codigo() -> str:
    """Genera un código OTP de 6 dígitos. Analogía: el ticket numerado de la panadería."""
    return "".join(random.choices(string.digits, k=6))


# ── Login admin ───────────────────────────────────────────────────────────────
@router.post("/login", response_model=TokenResponse)
async def login_admin(body: LoginAdmin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Usuario).where(Usuario.email == body.email, Usuario.rol == "admin", Usuario.activo == True)
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash or ""):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")

    # Bloquear login si el email no fue verificado
    if not user.email_verificado:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email no verificado. Revisa tu correo y confirma tu cuenta."
        )

    empresa_result = await db.execute(select(Empresa).where(Empresa.id == user.empresa_id))
    empresa = empresa_result.scalar_one()

    token = create_access_token({"sub": user.id, "rol": user.rol, "empresa_id": user.empresa_id})
    return {"token": token, "usuario": _usuario_payload(user, empresa)}


# ── Login vendedor ────────────────────────────────────────────────────────────
@router.post("/vendedor", response_model=TokenResponse)
async def login_vendedor(body: LoginVendedor, db: AsyncSession = Depends(get_db)):
    emp_result = await db.execute(select(Empresa).where(Empresa.rut == body.adminRut))
    empresa = emp_result.scalar_one_or_none()
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")

    vend_result = await db.execute(
        select(Usuario).where(
            Usuario.empresa_id == empresa.id,
            Usuario.rol == "vendedor",
            Usuario.activo == True,
        )
    )
    vendedores = vend_result.scalars().all()

    user = next((v for v in vendedores if verify_password(body.pin, v.pin_hash or "")), None)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="PIN incorrecto")

    token = create_access_token({"sub": user.id, "rol": user.rol, "empresa_id": empresa.id})
    return {"token": token, "usuario": _usuario_payload(user, empresa)}


# ── Registro ──────────────────────────────────────────────────────────────────
@router.post("/registro", status_code=201)
async def registro(body: RegistroEmpresa, db: AsyncSession = Depends(get_db)):
    """
    Registra la empresa y el admin, pero NO entrega token todavía.
    Envía un código de verificación al email — el usuario debe confirmarlo
    antes de poder ingresar. Analogía: abrir una cuenta en el banco y
    esperar el PIN que llega por carta antes de poder operar.
    """
    # Verificar email único
    existing = await db.execute(select(Usuario).where(Usuario.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="El email ya está registrado")

    # Crear empresa
    empresa = Empresa(
        id=str(uuid.uuid4()),
        nombre=body.nombre,
        rut=body.rut,
        giro=body.giro,
        direccion=body.direccion,
        comuna=body.comuna,
        ciudad=body.ciudad,
        plan="gratuito",
        tributario_completo=True,
    )
    db.add(empresa)
    await db.flush()

    # Crear admin con email_verificado=False — aún no puede ingresar
    admin = Usuario(
        id=str(uuid.uuid4()),
        empresa_id=empresa.id,
        nombre=body.nombre,
        email=body.email,
        password_hash=hash_password(body.password),
        rol="admin",
        email_verificado=False,
    )
    db.add(admin)

    # Generar y guardar código OTP (expira en 15 minutos)
    codigo = _generar_codigo()
    otp = CodigoVerificacion(
        id=str(uuid.uuid4()),
        email=body.email,
        codigo=codigo,
        expira_en=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    db.add(otp)
    await db.commit()

    # Enviar email con el código — no bloqueamos si falla el envío
    nombre_corto = body.nombre.split()[0] if body.nombre else "Usuario"
    enviar_email(
        destinatario=body.email,
        asunto="Código de verificación — YeparDTE",
        html=template_codigo_verificacion(nombre_corto, codigo),
    )

    return {"ok": True, "mensaje": "Cuenta creada. Revisa tu email para verificar tu cuenta.", "email": body.email}


# ── Verificar código OTP ──────────────────────────────────────────────────────
@router.post("/verificar", response_model=TokenResponse)
async def verificar_codigo(body: dict, db: AsyncSession = Depends(get_db)):
    """
    Valida el código OTP ingresado por el usuario.
    Si es correcto, marca el email como verificado y entrega el token de sesión.
    Analogía: el portero revisa el ticket y te deja entrar al evento.
    """
    email  = body.get("email", "").strip()
    codigo = body.get("codigo", "").strip()

    if not email or not codigo:
        raise HTTPException(status_code=400, detail="Email y código son requeridos")

    # Buscar código válido (no usado, no expirado)
    ahora = datetime.now(timezone.utc)
    result = await db.execute(
        select(CodigoVerificacion).where(
            CodigoVerificacion.email  == email,
            CodigoVerificacion.codigo == codigo,
            CodigoVerificacion.usado  == False,
            CodigoVerificacion.expira_en > ahora,
        )
    )
    otp = result.scalar_one_or_none()

    if not otp:
        raise HTTPException(status_code=400, detail="Código incorrecto o expirado")

    # Marcar OTP como usado
    otp.usado = True

    # Activar email del usuario
    user_result = await db.execute(
        select(Usuario).where(Usuario.email == email)
    )
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    user.email_verificado = True
    await db.commit()

    # Cargar empresa y entregar token de sesión
    empresa_result = await db.execute(select(Empresa).where(Empresa.id == user.empresa_id))
    empresa = empresa_result.scalar_one()

    token = create_access_token({"sub": user.id, "rol": user.rol, "empresa_id": user.empresa_id})
    return {"token": token, "usuario": _usuario_payload(user, empresa)}


# ── Reenviar código ───────────────────────────────────────────────────────────
@router.post("/reenviar-codigo")
async def reenviar_codigo(body: dict, db: AsyncSession = Depends(get_db)):
    """
    Invalida los códigos anteriores y envía uno nuevo al email.
    Analogía: pedir un nuevo ticket en la panadería porque perdiste el anterior.
    """
    email = body.get("email", "").strip()
    if not email:
        raise HTTPException(status_code=400, detail="Email requerido")

    # Verificar que el usuario existe y no está verificado aún
    user_result = await db.execute(select(Usuario).where(Usuario.email == email))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Email no registrado")
    if user.email_verificado:
        raise HTTPException(status_code=400, detail="Este email ya fue verificado")

    # Invalidar códigos anteriores
    await db.execute(
        delete(CodigoVerificacion).where(CodigoVerificacion.email == email)
    )

    # Generar nuevo código
    codigo = _generar_codigo()
    otp = CodigoVerificacion(
        id=str(uuid.uuid4()),
        email=email,
        codigo=codigo,
        expira_en=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    db.add(otp)
    await db.commit()

    nombre_corto = user.nombre.split()[0] if user.nombre else "Usuario"
    enviar_email(
        destinatario=email,
        asunto="Nuevo código de verificación — YeparDTE",
        html=template_codigo_verificacion(nombre_corto, codigo),
    )

    return {"ok": True, "mensaje": "Nuevo código enviado"}
