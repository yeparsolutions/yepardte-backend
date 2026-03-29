# app/routers/usuarios.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.deps import get_current_admin, get_empresa
from app.core.security import hash_password
from app.models.models import Usuario, Empresa
from app.schemas.schemas import VendedorCreate, VendedorOut
from app.services.planes import PLANES
import uuid

router = APIRouter(prefix="/api/usuarios", tags=["usuarios"])


@router.get("/vendedores")
async def listar_vendedores(
    empresa: Empresa = Depends(get_empresa),
    admin: Usuario = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Usuario).where(
            Usuario.empresa_id == empresa.id,
            Usuario.rol == "vendedor",
            Usuario.activo == True,
        )
    )
    vendedores = result.scalars().all()
    return {"vendedores": [{"id": v.id, "nombre": v.nombre, "creado_en": v.creado_en} for v in vendedores]}


@router.post("/vendedores", status_code=201)
async def crear_vendedor(
    body: VendedorCreate,
    empresa: Empresa = Depends(get_empresa),
    admin: Usuario = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    plan_info = PLANES.get(empresa.plan, PLANES["gratuito"])
    limite = plan_info["vendedoresLimit"]

    # Contar vendedores actuales
    result = await db.execute(
        select(Usuario).where(
            Usuario.empresa_id == empresa.id,
            Usuario.rol == "vendedor",
            Usuario.activo == True,
        )
    )
    actuales = len(result.scalars().all())

    if actuales >= limite:
        raise HTTPException(
            status_code=403,
            detail=f"Tu plan {empresa.plan} permite máximo {limite} vendedor(es). Actualiza tu plan."
        )

    vendedor = Usuario(
        id=str(uuid.uuid4()),
        empresa_id=empresa.id,
        nombre=body.nombre,
        pin_hash=hash_password(body.pin),
        rol="vendedor",
    )
    db.add(vendedor)
    await db.commit()
    return {"vendedor": {"id": vendedor.id, "nombre": vendedor.nombre}}


@router.delete("/vendedores/{vendedor_id}")
async def eliminar_vendedor(
    vendedor_id: str,
    empresa: Empresa = Depends(get_empresa),
    admin: Usuario = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Usuario).where(Usuario.id == vendedor_id, Usuario.empresa_id == empresa.id)
    )
    vendedor = result.scalar_one_or_none()
    if not vendedor:
        raise HTTPException(status_code=404, detail="Vendedor no encontrado")
    vendedor.activo = False
    await db.commit()
    return {"ok": True}
