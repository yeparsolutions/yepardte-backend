# app/routers/dte.py v4 — soporte Tipo 41 (boleta exenta)
import json
import logging
import secrets
import hashlib
import hmac
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.core.database import get_db
from app.core.deps import get_current_user, get_empresa
from app.models.models import Documento, Empresa, Usuario
from app.schemas.schemas import EmitirDocumento
from app.services.dtecore import dtecore
from app.services.planes import PLANES
from app.services.email_service import enviar_email, template_documento_email, generar_pdf_documento
from datetime import datetime, timezone, timedelta
import os
import uuid

router = APIRouter(prefix="/api/dte", tags=["dte"])

SECRET_KEY = os.getenv("SECRET_KEY", "changeme")


def _generar_token_pdf(doc_id: str) -> str:
    msg = f"{doc_id}:{SECRET_KEY}".encode()
    return hmac.new(SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()[:32]


def _verificar_token_pdf(doc_id: str, token: str) -> bool:
    return hmac.compare_digest(_generar_token_pdf(doc_id), token)


@router.post("/emitir")
async def emitir(
    body: EmitirDocumento,
    user: Usuario = Depends(get_current_user),
    empresa: Empresa = Depends(get_empresa),
    db: AsyncSession = Depends(get_db),
):
    plan_info = PLANES.get(empresa.plan, PLANES["gratuito"])

    # ── Verificar límite de folios ────────────────────────────────────────────
    if empresa.docs_usados >= plan_info["docsLimit"]:
        if plan_info["excedentePorDoc"] > 0:
            from app.routers.pagos import cobrar_excedente
            from sqlalchemy import select as sa_select
            from app.models.models import Usuario as Usr
            admin_result = await db.execute(
                sa_select(Usr).where(Usr.empresa_id == empresa.id, Usr.rol == "admin")
            )
            admin = admin_result.scalar_one_or_none()
            admin_email = admin.email if admin else ""

            init_point = await cobrar_excedente(empresa, admin_email, 10)
            raise HTTPException(
                status_code=402,
                detail={
                    "mensaje":      f"Límite de {plan_info['docsLimit']} folios alcanzado. Puedes comprar folios adicionales.",
                    "init_point":   init_point,
                    "precio_folio": plan_info["excedentePorDoc"],
                    "tipo":         "excedente",
                }
            )
        else:
            raise HTTPException(
                status_code=403,
                detail=f"Límite de {plan_info['docsLimit']} documentos alcanzado. Actualiza tu plan."
            )

    # ── Determinar tipo real de DTE ───────────────────────────────────────────
    # Tipo 39 = Boleta afecta | Tipo 41 = Boleta exenta | Tipo 33 = Factura
    es_exento  = body.exento
    es_boleta  = body.tipoCode in ("39", "41")
    es_factura = body.tipoCode == "33"

    # Si el frontend marcó exento pero mandó tipoCode "39", corregimos a "41"
    tipo_code_real = body.tipoCode
    if es_boleta and es_exento:
        tipo_code_real = "41"

    # ── Usar montos pre-calculados por el frontend ────────────────────────────
    # El frontend ya resolvió la lógica de IVA incluido / exento / neto.
    # Usamos sus valores directamente para mantener consistencia.
    if body.montoTotal is not None:
        neto_afecto = body.montoNeto   or 0
        neto_exento = body.montoExento or 0
        iva         = body.montoIva    or 0
        total       = body.montoTotal
    else:
        # Fallback: calcular en backend (casos sin frontend YeparDTE)
        subtotal = sum(item.precio * item.qty for item in body.items)
        if es_exento:
            neto_afecto = 0
            neto_exento = subtotal
            iva         = 0
            total       = subtotal
        elif es_boleta:
            # Boleta afecta: monto total sin desglose de IVA (estándar SII boletas)
            neto_afecto = subtotal
            neto_exento = 0
            iva         = 0
            total       = subtotal
        else:
            # Factura: IVA desglosado
            neto_afecto = subtotal
            neto_exento = 0
            iva         = round(subtotal * 0.19)
            total       = subtotal + iva

    # Tipo descriptivo para guardar en DB
    if tipo_code_real == "41":
        tipo_label = "Boleta Exenta"
    elif tipo_code_real == "39":
        tipo_label = "Boleta"
    else:
        tipo_label = "Factura"

    # CAF a usar según tipo de documento
    if tipo_code_real == "41":
        caf_a_usar = empresa.caf_boleta_exenta or empresa.caf_boleta or b""
    elif tipo_code_real == "39":
        caf_a_usar = empresa.caf_boleta or b""
    else:
        caf_a_usar = empresa.caf_factura or b""

    try:
        resultado = await dtecore.emitir_dte(
            tipo_code=tipo_code_real,
            exento=es_exento,
            receptor=body.receptor.model_dump(),
            items=[i.model_dump() for i in body.items],
            firma_cifrada=empresa.firma_digital or b"",
            firma_password=empresa.firma_password or "",
            caf_cifrado=caf_a_usar,
            monto_neto=neto_afecto,
            monto_exento=neto_exento,
            monto_iva=iva,
            monto_total=total,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error en DTECore: {str(e)}")

    doc = Documento(
        id=str(uuid.uuid4()),
        empresa_id=empresa.id,
        vendedor_id=user.id,
        tipo=tipo_label,
        tipo_code=tipo_code_real,
        numero=resultado.get("numero", ""),
        folio=resultado.get("folio"),
        receptor_nombre=body.receptor.nombre,
        receptor_rut=body.receptor.rut,
        receptor_email=body.receptor.email,
        receptor_direccion=body.receptor.direccion,
        receptor_giro=body.receptor.giro,
        monto_neto=neto_afecto,
        monto_exento=neto_exento,
        monto_iva=iva,
        monto_total=total,
        items=json.dumps([i.model_dump() for i in body.items]),
        estado=resultado.get("estado", "enviado"),
        track_id=resultado.get("track_id"),
        condicion_pago=body.condicionPago,
    )
    db.add(doc)
    empresa.docs_usados = (empresa.docs_usados or 0) + 1
    await db.commit()
    await db.refresh(doc)

    docs_restantes = plan_info["docsLimit"] - empresa.docs_usados
    alerta_limite  = docs_restantes <= max(1, plan_info["docsLimit"] * 0.10)

    return {
        "ok": True,
        "documento": {
            "id":        doc.id,
            "tipo":      doc.tipo,
            "tipoCode":  doc.tipo_code,
            "numero":    doc.numero,
            "folio":     doc.folio,
            "receptor":  doc.receptor_nombre,
            "rut":       doc.receptor_rut,
            "monto":     doc.monto_total,
            "estado":    doc.estado,
            "fecha":     doc.fecha.isoformat(),
            "vendedor":  body.vendedorNombre or user.nombre,
            "exento":    es_exento,
        },
        "folios": {
            "usados":       empresa.docs_usados,
            "limite":       plan_info["docsLimit"],
            "restantes":    docs_restantes,
            "alertaLimite": alerta_limite,
        }
    }


@router.get("/estadisticas")
async def estadisticas(
    user: Usuario = Depends(get_current_user),
    empresa: Empresa = Depends(get_empresa),
    db: AsyncSession = Depends(get_db),
):
    from datetime import datetime, timezone
    from sqlalchemy import and_, extract

    ahora = datetime.now(timezone.utc)
    mes   = ahora.month
    anio  = ahora.year

    q_mes = select(Documento).where(
        Documento.empresa_id == empresa.id,
        extract('month', Documento.fecha) == mes,
        extract('year',  Documento.fecha) == anio,
    )
    if user.rol == "vendedor":
        q_mes = q_mes.where(Documento.vendedor_id == user.id)

    result   = await db.execute(q_mes)
    docs_mes = result.scalars().all()

    def sumar(tipo_code):
        return sum(d.monto_total for d in docs_mes if d.tipo_code == tipo_code)
    def contar(tipo_code):
        return sum(1 for d in docs_mes if d.tipo_code == tipo_code)

    plan_info  = PLANES.get(empresa.plan, PLANES["gratuito"])
    excedentes = max(0, (empresa.docs_usados or 0) - plan_info["docsLimit"])
    monto_exc  = excedentes * plan_info.get("excedentePorDoc", 0)

    return {
        "totalDocs":            empresa.docs_usados or 0,
        "boletasMes":           contar("39"),
        "boletasExentasMes":    contar("41"),
        "facturasMes":          contar("33"),
        "notasCreditoMes":      contar("61"),
        "notasDebitoMes":       contar("56"),
        "guiasMes":             contar("52"),
        "montoBoletasMes":      sumar("39"),
        "montoBoletasExentasMes": sumar("41"),
        "montoFacturasMes":     sumar("33"),
        "montoNotasCreditoMes": sumar("61"),
        "montoNotasDebitoMes":  sumar("56"),
        "montoGuiasMes":        sumar("52"),
        "excedentes": {
            "cantidad":  excedentes,
            "montoNeto": monto_exc,
        },
    }


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

    query  = query.order_by(Documento.fecha.desc()).offset((page - 1) * limit).limit(limit)
    result = await db.execute(query)
    docs   = result.scalars().all()

    count_q = select(func.count()).select_from(Documento).where(Documento.empresa_id == empresa.id)
    total   = (await db.execute(count_q)).scalar()

    return {
        "documentos": [{
            "id":       d.id,
            "tipo":     d.tipo,
            "tipoCode": d.tipo_code,
            "numero":   d.numero,
            "receptor": d.receptor_nombre,
            "rut":      d.receptor_rut,
            "monto":    d.monto_total,
            "estado":   d.estado,
            "fecha":    d.fecha.isoformat(),
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
    result = await db.execute(
        select(Documento).where(Documento.id == doc_id, Documento.empresa_id == empresa.id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")
    if user.rol == "vendedor" and doc.vendedor_id != user.id:
        raise HTTPException(status_code=403, detail="Sin permiso")
    if not doc.receptor_email:
        raise HTTPException(status_code=400, detail="Este documento no tiene email del receptor.")

    token     = _generar_token_pdf(doc_id)
    fecha_fmt = doc.fecha.strftime("%d/%m/%Y")

    # ── Generar PDF adjunto — mismo HTML que la app ──────────────────────────
    # Analogía: antes de meter la carta en el sobre se imprime en la misma
    # imprenta que la app — el receptor recibe exactamente lo que ve el usuario.
    adjuntos = []
    try:
        pdf_bytes  = generar_pdf_documento(doc, empresa)
        nombre_pdf = f"{doc.tipo}-{doc.numero}.pdf".replace(" ", "_")
        adjuntos   = [{"filename": nombre_pdf, "content": pdf_bytes}]
    except Exception as e:
        logging.warning(f"[DTE] PDF adjunto falló para {doc_id}: {e}")
        # Continúa sin adjunto — el email se envía igual con el botón de descarga

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
            doc_id=doc_id,
            token=token,
        ),
        adjuntos=adjuntos,
    )

    if not ok:
        raise HTTPException(status_code=500, detail="No se pudo enviar el email. Verifica RESEND_API_KEY.")

    return {"ok": True, "mensaje": f"Documento enviado a {doc.receptor_email}"}


@router.get("/{doc_id}/pdf-publico")
async def pdf_publico(
    doc_id: str,
    token: str,
    db: AsyncSession = Depends(get_db),
):
    if not _verificar_token_pdf(doc_id, token):
        raise HTTPException(status_code=403, detail="Token inválido")

    result = await db.execute(select(Documento).where(Documento.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    empresa_result = await db.execute(select(Empresa).where(Empresa.id == doc.empresa_id))
    empresa = empresa_result.scalar_one_or_none()
    if not empresa:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")

    try:
        pdf_bytes = generar_pdf_documento(doc, empresa)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando PDF: {str(e)}")

    nombre_archivo = f"{doc.tipo}-{doc.numero}.pdf".replace(" ", "_")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )


# ── Ruta genérica al final ────────────────────────────────────────────────────

@router.get("/{doc_id}")
async def obtener_documento(
    doc_id: str,
    user: Usuario = Depends(get_current_user),
    empresa: Empresa = Depends(get_empresa),
    db: AsyncSession = Depends(get_db),
):
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
            "netoExento":        getattr(doc, "monto_exento", 0) or 0,
            "iva":               doc.monto_iva,
            "exento":            doc.tipo_code == "41",
            "estado":            doc.estado,
            "fecha":             doc.fecha.isoformat(),
            "track_id":          doc.track_id,
            "items":             items_list,
        }
    }
