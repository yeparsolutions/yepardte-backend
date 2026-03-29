# app/routers/empresa.py
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.deps import get_current_admin, get_empresa
from app.core.security import encrypt_firma, decrypt_firma
from app.models.models import Empresa, Usuario
from app.schemas.schemas import EmpresaOut, EmpresaUpdate

router = APIRouter(prefix="/api/empresa", tags=["empresa"])


@router.get("", response_model=EmpresaOut)
async def obtener_empresa(empresa: Empresa = Depends(get_empresa)):
    return empresa


@router.put("")
async def actualizar_empresa(
    body: EmpresaUpdate,
    empresa: Empresa = Depends(get_empresa),
    admin: Usuario = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(empresa, field, value)
    await db.commit()
    return {"ok": True}


@router.post("/firma")
async def subir_firma(
    archivo: UploadFile = File(...),
    password: str = "",
    empresa: Empresa = Depends(get_empresa),
    admin: Usuario = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Sube y cifra la firma digital (.pfx/.p12) de la empresa."""
    if not archivo.filename.endswith((".pfx", ".p12")):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos .pfx o .p12")

    contenido = await archivo.read()
    empresa.firma_digital = encrypt_firma(contenido)
    empresa.firma_password = password   # TODO: cifrar también con Fernet
    empresa.tributario_completo = True
    await db.commit()
    return {"ok": True, "mensaje": "Firma digital cargada correctamente"}


@router.post("/caf")
async def subir_caf(
    archivo: UploadFile = File(...),
    tipo: str = "39",  # 39=boleta 33=factura
    empresa: Empresa = Depends(get_empresa),
    admin: Usuario = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Sube y cifra el CAF (XML de folios) de la empresa."""
    contenido = await archivo.read()
    cifrado = encrypt_firma(contenido)
    if tipo == "39":
        empresa.caf_boleta = cifrado
    elif tipo == "33":
        empresa.caf_factura = cifrado
    else:
        raise HTTPException(status_code=400, detail="Tipo debe ser 39 o 33")
    await db.commit()
    return {"ok": True, "mensaje": f"CAF tipo {tipo} cargado correctamente"}
