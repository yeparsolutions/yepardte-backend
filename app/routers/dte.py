# app/routers/dte.py v3
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.core.deps import get_current_user, get_empresa
from app.models.models import Documento, Empresa, Usuario
from app.schemas.schemas import EmitirDocumento
from app.services.dtecore import dtecore
from app.services.planes import PLANES
from app.services.email_service import enviar_email, template_documento_email, generar_pdf_documento
import uuid

router = APIRouter(prefix="/api/dte", tags=["dte"])


@router.post("/emitir")
async def emitir(
    body: EmitirDocumento,
    user: Usuario = Depends(get_current_user),
    empresa: Empresa = Depends(get_empresa),
    db: AsyncSession = Depends(get_db),
):
    plan_info = PLANES.get(empresa.plan, PLANES["gratuito"])
    if empresa.docs_usados >= plan_info["docsLimit"]:
        raise HTTPException(
            status_code=403,
            detail=f"Límite de {plan_info['docsLimit']} documentos alcanzado. Actualiza tu plan."
        )

    es_boleta = body.tipoCode == "39"
    neto  = sum(item.precio * item.qty for item in body.items)
    iva   = 0 if es_boleta else round(neto * 0.19)
    total = neto + iva

    try:
        resultado = await dtecore.emitir_dte(
            tipo_code=body.tipoCode,
            receptor=body.receptor.model_dump(),
            items=[i.model_dump() for i in body.items],
            firma_cifrada=empresa.firma_digital or b"",
            firma_password=empresa.firma_password or "",
            caf_cifrado=(empresa.caf_boleta if es_boleta else empresa.caf_factura) or b"",
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error en DTECore: {str(e)}")

    doc = Documento(
        id=str(uuid.uuid4()),
        empresa_id=empresa.id,
        vendedor_id=user.id,
        tipo="Boleta" if es_boleta else "Factura",
        tipo_code=body.tipoCode,
        numero=resultado.get("numero", ""),
        folio=resultado.get("folio"),
        receptor_nombre=body.receptor.nombre,
        receptor_rut=body.receptor.rut,
        receptor_email=body.receptor.email,
        receptor_direccion=body.receptor.direccion,
        receptor_giro=body.receptor.giro,
        monto_neto=neto,
        monto_iva=iva,
        monto_total=total,
        items=json.dumps([i.model_dump() for i in body.items]),
        estado=resultado.get("estado", "enviado"),
        track_id=resultado.get("track_id"),
    )
    db.add(doc)
    empresa.docs_usados = (empresa.docs_usados or 0) + 1
    await db.commit()
    await db.refresh(doc)

    return {"ok": True, "documento": {
        "id": doc.id, "tipo": doc.tipo, "tipoCode": doc.tipo_code,
        "numero": doc.numero, "folio": doc.folio,
        "receptor": doc.receptor_nombre, "rut": doc.receptor_rut,
        "monto": doc.monto_total, "estado": doc.estado,
        "fecha": doc.fecha.isoformat(),
        "vendedor": body.vendedorNombre or user.nombre,
    }}


@router.get("/historial")
async def historial(
    tipo: str | None = None,
    estado: str | None = None,
    page: int = 1,
    limit: int = 20,
    user: Usuario = Depends(get_current_user),
    empresa: Empresa = Depends(get_empresa),
    db: AsyncSession = Depends(get_db),
):
    query = select(Documento).where(Documento.empresa_id == empresa.id)
    if user.rol == "vendedor":
        query = query.where(Documento.vendedor_id == user.id)
    if tipo:
        query = query.where(Documento.tipo_code == tipo)
    if estado:
        query = query.where(Documento.estado == estado)

    query = query.order_by(Documento.fecha.desc()).offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    docs = result.scalars().all()

    count_q = select(func.count()).select_from(Documento).where(Documento.empresa_id == empresa.id)
    total = (await db.execute(count_q)).scalar()

    return {
        "documentos": [{
            "id": d.id, "tipo": d.tipo, "tipoCode": d.tipo_code,
            "numero": d.numero, "receptor": d.receptor_nombre,
            "rut": d.receptor_rut, "monto": d.monto_total,
            "estado": d.estado, "fecha": d.fecha.isoformat(),
            "track_id": d.track_id,
        } for d in docs],
        "total": total,
    }


# ── Rutas específicas ANTES de /{doc_id} ──────────────────────────────────────

@router.post("/{doc_id}/enviar-email")
async def enviar_documento_email(
    doc_id: str,
    user: Usuario = Depends(get_current_user),
    empresa: Empresa = Depends(get_empresa),
    db: AsyncSession = Depends(get_db),
):
    """
    Genera el PDF del documento y lo envía por email al receptor.
    Analogía: la secretaria imprime el documento, lo mete en el sobre
    y lo despacha al destinatario — todo en un solo paso.
    """
    result = await db.execute(
        select(Documento).where(Documento.id == doc_id, Documento.empresa_id == empresa.id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    if user.rol == "vendedor" and doc.vendedor_id != user.id:
        raise HTTPException(status_code=403, detail="Sin permiso")
    if not doc.receptor_email:
        raise HTTPException(
            status_code=400,
            detail="Este documento no tiene email del receptor."
        )

    # Generar PDF para adjuntar
    try:
        pdf_bytes = generar_pdf_documento(doc, empresa)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando PDF: {str(e)}")

    nombre_archivo = f"{doc.tipo}-{doc.numero}.pdf".replace(" ", "_")
    fecha_fmt      = doc.fecha.strftime("%d/%m/%Y")

    ok = enviar_email(
        destinatario=doc.receptor_email,
        asunto=f"{doc.tipo} {doc.numero} — {empresa.nombre}",
        html=template_documento_email(
            empresa_nombre=empresa.nombre,
            empresa_rut=empresa.rut,
            tipo_doc=doc.tipo,
            numero_doc=doc.numero,
            receptor_nombre=doc.receptor_nombre,
            monto_total=doc.monto_total,
            fecha=fecha_fmt,
        ),
        # PDF adjunto al email
        adjuntos=[{"filename": nombre_archivo, "content": pdf_bytes}],
    )

    if not ok:
        raise HTTPException(
            status_code=500,
            detail="No se pudo enviar el email. Verifica RESEND_API_KEY."
        )

    return {"ok": True, "mensaje": f"Documento enviado a {doc.receptor_email}"}


# ── Ruta genérica al final ────────────────────────────────────────────────────

@router.get("/{doc_id}")
async def obtener_documento(
    doc_id: str,
    user: Usuario = Depends(get_current_user),
    empresa: Empresa = Depends(get_empresa),
    db: AsyncSession = Depends(get_db),
):
    """
    Retorna todos los datos del documento para que el frontend
    genere el PDF con generarPDFDocumento().
    """
    result = await db.execute(
        select(Documento).where(Documento.id == doc_id, Documento.empresa_id == empresa.id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    if user.rol == "vendedor" and doc.vendedor_id != user.id:
        raise HTTPException(status_code=403, detail="Sin permiso")

    items_raw = doc.items
    if isinstance(items_raw, str):
        items_list = json.loads(items_raw or "[]")
    elif isinstance(items_raw, list):
        items_list = items_raw
    else:
        items_list = []

    return {
        "documento": {
            "id":                doc.id,
            "tipo":              doc.tipo,
            "tipoCode":          doc.tipo_code,
            "numero":            doc.numero,
            "folio":             doc.folio,
            "receptor":          doc.receptor_nombre,
            "rut":               doc.receptor_rut,
            "receptorNombre":    doc.receptor_nombre,
            "receptorRut":       doc.receptor_rut,
            "receptorEmail":     doc.receptor_email,
            "receptorGiro":      doc.receptor_giro,
            "receptorDireccion": doc.receptor_direccion,
            "monto":             doc.monto_total,
            "neto":              doc.monto_neto,
            "iva":               doc.monto_iva,
            "estado":            doc.estado,
            "fecha":             doc.fecha.isoformat(),
            "track_id":          doc.track_id,
            "items":             items_list,
        }
    }
