# app/routers/clientes.py
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.deps import get_current_user, get_empresa
from app.models.models import Cliente, Empresa, Usuario

router = APIRouter(prefix="/api/clientes", tags=["clientes"])


class ClienteUpsert(BaseModel):
    rut: str
    nombre: str
    email: Optional[str] = None
    giro: Optional[str] = None
    direccion: Optional[str] = None


@router.get("/buscar")
async def buscar_cliente(
    rut: str,
    empresa: Empresa = Depends(get_empresa),
    user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Cliente).where(Cliente.empresa_id == empresa.id, Cliente.rut == rut)
    )
    cliente = result.scalar_one_or_none()
    if not cliente:
        return {"cliente": None}
    return {"cliente": {
        "id": cliente.id,
        "rut": cliente.rut,
        "nombre": cliente.nombre,
        "email": cliente.email,
        "giro": cliente.giro,
        "direccion": cliente.direccion,
    }}


@router.post("", status_code=200)
async def upsert_cliente(
    body: ClienteUpsert,
    empresa: Empresa = Depends(get_empresa),
    user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Crea o actualiza un cliente por RUT."""
    result = await db.execute(
        select(Cliente).where(Cliente.empresa_id == empresa.id, Cliente.rut == body.rut)
    )
    cliente = result.scalar_one_or_none()

    if cliente:
        # Actualizar solo campos que llegan con valor
        if body.nombre: cliente.nombre = body.nombre
        if body.email:  cliente.email  = body.email
        if body.giro:   cliente.giro   = body.giro
        if body.direccion: cliente.direccion = body.direccion
    else:
        cliente = Cliente(
            id=str(uuid.uuid4()),
            empresa_id=empresa.id,
            rut=body.rut,
            nombre=body.nombre,
            email=body.email,
            giro=body.giro,
            direccion=body.direccion,
        )
        db.add(cliente)

    await db.commit()
    return {"ok": True}


@router.get("")
async def listar_clientes(
    empresa: Empresa = Depends(get_empresa),
    user: Usuario = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Cliente).where(Cliente.empresa_id == empresa.id).order_by(Cliente.nombre)
    )
    clientes = result.scalars().all()
    return {"clientes": [{
        "id": c.id, "rut": c.rut, "nombre": c.nombre,
        "email": c.email, "giro": c.giro, "direccion": c.direccion,
    } for c in clientes]}
