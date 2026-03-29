# app/routers/dte.py
import json
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.core.deps import get_current_user, get_empresa
from app.models.models import Documento, Empresa, Usuario
from app.schemas.schemas import EmitirDocumento, DocumentoOut
from app.services.dtecore import dtecore
from app.services.planes import PLANES
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

    # Calcular montos
    es_boleta = body.tipoCode == "39"
    neto = sum(item.precio * item.qty for item in body.items)
    iva  = 0 if es_boleta else round(neto * 0.19)
    total = neto + iva

    # Llamar a DTECore (mock hasta tener la API real)
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

    # Guardar en BD
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

    # Actualizar contador
    empresa.docs_usados = (empresa.docs_usados or 0) + 1
    await db.commit()
    await db.refresh(doc)

    return {"ok": True, "documento": {
        "id": doc.id,
        "tipo": doc.tipo,
        "tipoCode": doc.tipo_code,
        "numero": doc.numero,
        "folio": doc.folio,
        "receptor": doc.receptor_nombre,
        "rut": doc.receptor_rut,
        "monto": doc.monto_total,
        "estado": doc.estado,
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

    # Vendedor solo ve sus propios documentos
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
            "id": d.id,
            "tipo": d.tipo,
            "tipoCode": d.tipo_code,
            "numero": d.numero,
            "receptor": d.receptor_nombre,
            "rut": d.receptor_rut,
            "monto": d.monto_total,
            "estado": d.estado,
            "fecha": d.fecha.isoformat(),
            "track_id": d.track_id,
        } for d in docs],
        "total": total,
    }


@router.get("/{doc_id}/pdf")
async def pdf_documento(
    doc_id: str,
    user: Usuario = Depends(get_current_user),
    empresa: Empresa = Depends(get_empresa),
    db: AsyncSession = Depends(get_db),
):
    """
    TODO: Generar PDF del DTE usando DTECore o librería local.
    Por ahora retorna 501.
    """
    raise HTTPException(status_code=501, detail="PDF en desarrollo")
