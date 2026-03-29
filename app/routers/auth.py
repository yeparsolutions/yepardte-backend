# app/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.models.models import Empresa, Usuario
from app.schemas.schemas import LoginAdmin, LoginVendedor, RegistroEmpresa, TokenResponse
from app.services.planes import PLANES
import uuid

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _usuario_payload(user: Usuario, empresa: Empresa) -> dict:
    plan_info = PLANES.get(empresa.plan, PLANES["gratuito"])
    return {
        "id": user.id,
        "nombre": empresa.nombre if user.rol == "admin" else user.nombre,
        "email": user.email,
        "rut": empresa.rut,
        "rol": user.rol,
        "plan": empresa.plan,
        "docsUsados": empresa.docs_usados,
        "docsLimit": plan_info["docsLimit"],
        "vendedoresLimit": plan_info["vendedoresLimit"],
        "tributarioCompleto": empresa.tributario_completo,
    }


@router.post("/login", response_model=TokenResponse)
async def login_admin(body: LoginAdmin, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Usuario).where(Usuario.email == body.email, Usuario.rol == "admin", Usuario.activo == True)
    )
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash or ""):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciales incorrectas")

    empresa_result = await db.execute(select(Empresa).where(Empresa.id == user.empresa_id))
    empresa = empresa_result.scalar_one()

    token = create_access_token({"sub": user.id, "rol": user.rol, "empresa_id": user.empresa_id})
    return {"token": token, "usuario": _usuario_payload(user, empresa)}


@router.post("/vendedor", response_model=TokenResponse)
async def login_vendedor(body: LoginVendedor, db: AsyncSession = Depends(get_db)):
    # Busca la empresa por RUT del admin
    emp_result = await db.execute(select(Empresa).where(Empresa.rut == body.adminRut))
    empresa = emp_result.scalar_one_or_none()
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")

    # Busca vendedores de esa empresa
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


@router.post("/registro", response_model=TokenResponse, status_code=201)
async def registro(body: RegistroEmpresa, db: AsyncSession = Depends(get_db)):
    # Verificar email único
    existing = await db.execute(select(Usuario).where(Usuario.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="El email ya está registrado")

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

    admin = Usuario(
        id=str(uuid.uuid4()),
        empresa_id=empresa.id,
        nombre=body.nombre,
        email=body.email,
        password_hash=hash_password(body.password),
        rol="admin",
    )
    db.add(admin)
    await db.commit()
    await db.refresh(empresa)

    token = create_access_token({"sub": admin.id, "rol": "admin", "empresa_id": empresa.id})
    return {"token": token, "usuario": _usuario_payload(admin, empresa)}
