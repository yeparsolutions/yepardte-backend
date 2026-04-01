# app/routers/dte.py
import json
import io
import traceback
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
    # ── 1. Buscar el documento en BD ──────────────────────────────────────────
    result = await db.execute(
        select(Documento).where(
            Documento.id == doc_id,
            Documento.empresa_id == empresa.id,
        )
    )
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    # Vendedor solo puede ver sus propios documentos
    if user.rol == "vendedor" and doc.vendedor_id != user.id:
        raise HTTPException(status_code=403, detail="Sin permiso para ver este documento")

    # ── 2. Generar PDF con reportlab ──────────────────────────────────────────
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm

        buffer = io.BytesIO()
        doc_pdf = SimpleDocTemplate(buffer, pagesize=letter,
                                    topMargin=2*cm, bottomMargin=2*cm,
                                    leftMargin=2*cm, rightMargin=2*cm)

        styles = getSampleStyleSheet()
        elementos = []

        # Estilos
        estilo_titulo = ParagraphStyle('titulo', parent=styles['Heading1'], fontSize=16, spaceAfter=4)
        estilo_sub    = ParagraphStyle('sub',    parent=styles['Normal'],   fontSize=10, textColor=colors.grey)
        estilo_bold   = ParagraphStyle('bold',   parent=styles['Normal'],   fontSize=11, fontName='Helvetica-Bold')
        estilo_normal = ParagraphStyle('normal', parent=styles['Normal'],   fontSize=10)

        # Encabezado empresa
        elementos.append(Paragraph(empresa.nombre or "Empresa", estilo_titulo))
        elementos.append(Paragraph(f"RUT: {empresa.rut or '—'}", estilo_sub))
        elementos.append(Paragraph(f"Giro: {empresa.giro or '—'}", estilo_sub))
        elementos.append(Paragraph(f"Dirección: {empresa.direccion or '—'}, {empresa.comuna or ''}", estilo_sub))
        elementos.append(Spacer(1, 0.5*cm))

        # Tipo y número
        elementos.append(Paragraph(f"{doc.tipo} Electrónica N° {doc.numero}", estilo_bold))
        if doc.folio:
            elementos.append(Paragraph(f"Folio: {doc.folio}", estilo_sub))
        elementos.append(Paragraph(f"Fecha: {doc.fecha.strftime('%d/%m/%Y %H:%M')}", estilo_sub))
        elementos.append(Spacer(1, 0.5*cm))

        # Datos del receptor
        elementos.append(Paragraph("Receptor", estilo_bold))
        elementos.append(Paragraph(f"Nombre: {doc.receptor_nombre or '—'}", estilo_normal))
        if doc.receptor_rut:
            elementos.append(Paragraph(f"RUT: {doc.receptor_rut}", estilo_normal))
        if doc.receptor_email:
            elementos.append(Paragraph(f"Email: {doc.receptor_email}", estilo_normal))
        if doc.receptor_giro:
            elementos.append(Paragraph(f"Giro: {doc.receptor_giro}", estilo_normal))
        if doc.receptor_direccion:
            elementos.append(Paragraph(f"Dirección: {doc.receptor_direccion}", estilo_normal))
        elementos.append(Spacer(1, 0.5*cm))

        # Tabla de ítems
        items_data = [["Descripción", "Qty", "Precio unit.", "Subtotal"]]

        # ── Parsear items de forma segura ─────────────────────────────────────
        # Analogía: los items pueden venir como string JSON o ya como lista —
        # nos preparamos para ambos casos como un chef que acepta ingredientes
        # frescos o congelados
        items_raw = doc.items
        if isinstance(items_raw, str):
            items_list = json.loads(items_raw or "[]")
        elif isinstance(items_raw, list):
            items_list = items_raw
        else:
            items_list = []

        for item in items_list:
            subtotal = item.get("precio", 0) * item.get("qty", 1)
            items_data.append([
                item.get("nombre", item.get("desc", "")),   # soporta ambas keys
                str(item.get("qty", 1)),
                f"${item.get('precio', 0):,.0f}".replace(",", "."),
                f"${subtotal:,.0f}".replace(",", "."),
            ])

        tabla = Table(items_data, colWidths=[9*cm, 2*cm, 4*cm, 4*cm])
        tabla.setStyle(TableStyle([
            ("BACKGROUND",     (0, 0), (-1, 0),  colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR",      (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",       (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",       (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
            ("GRID",           (0, 0), (-1, -1), 0.5, colors.HexColor("#dddddd")),
            ("ALIGN",          (1, 0), (-1, -1), "RIGHT"),
            ("PADDING",        (0, 0), (-1, -1), 6),
        ]))
        elementos.append(tabla)
        elementos.append(Spacer(1, 0.5*cm))

        # Totales
        totales_data = [["Neto", f"${doc.monto_neto:,.0f}".replace(",", ".")]]
        if doc.monto_iva:
            totales_data.append(["IVA (19%)", f"${doc.monto_iva:,.0f}".replace(",", ".")])
        totales_data.append(["TOTAL", f"${doc.monto_total:,.0f}".replace(",", ".")])

        tabla_totales = Table(totales_data, colWidths=[14*cm, 4*cm], hAlign="RIGHT")
        tabla_totales.setStyle(TableStyle([
            ("FONTNAME",  (0, -1), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE",  (0, 0),  (-1, -1), 10),
            ("ALIGN",     (1, 0),  (1, -1),  "RIGHT"),
            ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
            ("PADDING",   (0, 0),  (-1, -1), 4),
        ]))
        elementos.append(tabla_totales)

        # Estado / Track ID
        elementos.append(Spacer(1, 1*cm))
        elementos.append(Paragraph(f"Estado SII: {doc.estado or '—'}", estilo_sub))
        if doc.track_id:
            elementos.append(Paragraph(f"Track ID: {doc.track_id}", estilo_sub))

        # Construir PDF
        doc_pdf.build(elementos)
        pdf_bytes = buffer.getvalue()

    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Librería reportlab no instalada. Agrega 'reportlab' a requirements.txt"
        )
    except Exception:
        # ── Traceback completo en el detalle para diagnosticar ────────────────
        # TEMPORAL: remover este bloque una vez resuelto el error
        raise HTTPException(status_code=500, detail=traceback.format_exc())

    # ── 3. Retornar el PDF como respuesta binaria ─────────────────────────────
    nombre_archivo = f"{doc.tipo}-{doc.numero}.pdf".replace(" ", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )
