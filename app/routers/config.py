# app/routers/config.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.deps import get_current_admin
from app.models.models import Usuario
from app.schemas.schemas import ConexionToggle

router = APIRouter(prefix="/api/config", tags=["config"])

# Estado en memoria (en producción podrías guardarlo en BD o Redis)
_conexion_activa = True


@router.post("/conexion")
async def toggle_conexion(
    body: ConexionToggle,
    admin: Usuario = Depends(get_current_admin),
):
    global _conexion_activa
    _conexion_activa = body.activa
    return {"ok": True, "activa": _conexion_activa}


@router.get("/conexion")
async def estado_conexion(admin: Usuario = Depends(get_current_admin)):
    return {"activa": _conexion_activa}
