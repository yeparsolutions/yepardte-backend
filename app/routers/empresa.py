# app/routers/empresa.py
import base64
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.deps import get_current_admin, get_empresa
from app.core.security import encrypt_firma, decrypt_firma
from app.models.models import Empresa, Usuario
from app.schemas.schemas import EmpresaOut, EmpresaUpdate

router = APIRouter(prefix="/api/empresa", tags=["empresa"])

# Formatos de imagen permitidos para el logo
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


# ── Logo de la empresa ────────────────────────────────────────────────────────
# Analogía: el membrete de una empresa — aparece en el encabezado
# de todas las boletas y facturas que emite.

@router.get("/logo")
async def obtener_logo(empresa: Empresa = Depends(get_empresa)):
    """
    Retorna el logo actual como base64 para mostrarlo en el frontend
    y en el generador de PDFs.
    """
    if not empresa.logo:
        return {"logo_base64": None}

    # Detectar tipo de imagen por los primeros bytes
    # Analogía: el tipo MIME es como el idioma del archivo —
    # PNG, JPEG, SVG hablan distinto pero todos son imágenes
    logo_bytes = empresa.logo
    if logo_bytes[:4] == b'\x89PNG':
        mime = "image/png"
    elif logo_bytes[:2] == b'\xff\xd8':
        mime = "image/jpeg"
    elif logo_bytes[:4] == b'<svg' or b'<svg' in logo_bytes[:100]:
        mime = "image/svg+xml"
    elif logo_bytes[:4] == b'RIFF':
        mime = "image/webp"
    else:
        mime = "image/png"  # fallback

    b64 = base64.b64encode(logo_bytes).decode("utf-8")
    return {"logo_base64": f"data:{mime};base64,{b64}"}


@router.post("/logo")
async def subir_logo(
    archivo: UploadFile = File(...),
    empresa: Empresa = Depends(get_empresa),
    admin: Usuario = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Sube y guarda el logo de la empresa.
    Máximo 500KB — PNG, JPG, SVG o WEBP.
    """
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
            detail=f"El logo no debe superar 500KB. Tamaño recibido: {len(contenido) // 1024}KB"
        )

    empresa.logo = contenido
    await db.commit()
    return {"ok": True, "mensaje": "Logo guardado correctamente"}


@router.delete("/logo")
async def eliminar_logo(
    empresa: Empresa = Depends(get_empresa),
    admin: Usuario = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Elimina el logo de la empresa."""
    empresa.logo = None
    await db.commit()
    return {"ok": True, "mensaje": "Logo eliminado"}
