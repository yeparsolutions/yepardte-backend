# app/routers/empresa.py
import base64
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.deps import get_current_admin, get_empresa
from app.core.security import encrypt_firma
from app.models.models import Empresa, Usuario
from app.schemas.schemas import EmpresaOut, EmpresaUpdate
from pydantic import BaseModel

router = APIRouter(prefix="/api/empresa", tags=["empresa"])

LOGO_TIPOS_PERMITIDOS = {
    "image/png", "image/jpeg", "image/jpg",
    "image/svg+xml", "image/webp",
}
LOGO_MAX_BYTES = 500 * 1024  # 500 KB


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
    if not archivo.filename.endswith((".pfx", ".p12")):
        raise HTTPException(status_code=400, detail="Solo se aceptan archivos .pfx o .p12")
    contenido = await archivo.read()
    empresa.firma_digital       = encrypt_firma(contenido)
    empresa.firma_password      = password
    empresa.tributario_completo = True
    await db.commit()
    return {"ok": True, "mensaje": "Firma digital cargada correctamente"}


@router.post("/caf")
async def subir_caf(
    archivo: UploadFile = File(...),
    tipo: str = "39",
    empresa: Empresa = Depends(get_empresa),
    admin: Usuario = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    contenido = await archivo.read()
    cifrado   = encrypt_firma(contenido)

    if tipo == "39":
        empresa.caf_boleta = cifrado
    elif tipo == "41":
        empresa.caf_boleta_exenta = cifrado
    elif tipo == "33":
        empresa.caf_factura = cifrado
    else:
        raise HTTPException(status_code=400, detail="Tipo debe ser 39, 41 o 33")

    await db.commit()
    return {"ok": True, "mensaje": f"CAF tipo {tipo} cargado correctamente"}


# ── Logo ──────────────────────────────────────────────────────────────────────

@router.get("/logo")
async def obtener_logo(empresa: Empresa = Depends(get_empresa)):
    """
    Retorna logo como base64 + ancho guardado.
    El frontend usa esto para previsualizar y para generar los PDFs.
    """
    if not empresa.logo:
        return {"logo_base64": None, "logo_ancho": empresa.logo_ancho or 70}

    # Detectar MIME por magic bytes
    logo_bytes = empresa.logo
    if logo_bytes[:4] == b'\x89PNG':
        mime = "image/png"
    elif logo_bytes[:2] == b'\xff\xd8':
        mime = "image/jpeg"
    elif b'<svg' in logo_bytes[:200]:
        mime = "image/svg+xml"
    elif logo_bytes[:4] == b'RIFF':
        mime = "image/webp"
    else:
        mime = "image/png"

    b64 = base64.b64encode(logo_bytes).decode("utf-8")
    return {
        "logo_base64": f"data:{mime};base64,{b64}",
        "logo_ancho":  empresa.logo_ancho or 70,
    }


@router.post("/logo")
async def subir_logo(
    archivo: UploadFile = File(...),
    empresa: Empresa = Depends(get_empresa),
    admin: Usuario = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Sube y guarda el logo en la BD. Máx 500KB."""
    content_type = archivo.content_type or ""
    if content_type not in LOGO_TIPOS_PERMITIDOS:
        raise HTTPException(
            status_code=400,
            detail="Formato no permitido. Usa PNG, JPG, SVG o WEBP."
        )
    contenido = await archivo.read()
    if len(contenido) > LOGO_MAX_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"El logo no debe superar 500KB. Recibido: {len(contenido)//1024}KB"
        )

    # Guardar en BD — persiste entre sesiones
    empresa.logo = contenido
    await db.commit()
    return {"ok": True, "mensaje": "Logo guardado en la base de datos"}


class LogoAnchoBody(BaseModel):
    ancho: int  # px, entre 40 y 200


@router.put("/logo/ancho")
async def actualizar_ancho_logo(
    body: LogoAnchoBody,
    empresa: Empresa = Depends(get_empresa),
    admin: Usuario = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Guarda el ancho preferido del logo en px."""
    if not (40 <= body.ancho <= 200):
        raise HTTPException(status_code=400, detail="El ancho debe estar entre 40 y 200 px")
    empresa.logo_ancho = body.ancho
    await db.commit()
    return {"ok": True, "logo_ancho": body.ancho}


@router.delete("/logo")
async def eliminar_logo(
    empresa: Empresa = Depends(get_empresa),
    admin: Usuario = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Elimina el logo de la empresa."""
    empresa.logo       = None
    empresa.logo_ancho = 70
    await db.commit()
    return {"ok": True, "mensaje": "Logo eliminado"}
