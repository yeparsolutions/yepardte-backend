# app/services/email_service.py
# ============================================================
# YeparDTE — Servicio de Email via Resend API
# ============================================================

import os
import json
import resend
from dotenv import load_dotenv

load_dotenv()

RESEND_API_KEY  = os.getenv("RESEND_API_KEY", "")
EMAIL_FROM      = os.getenv("EMAIL_FROM",      "soporte@yeparsolutions.com")
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "YeparDTE")
FRONTEND_URL    = os.getenv("VITE_FRONTEND_URL", "https://yepardte.yeparsolutions.com")
BACKEND_URL     = os.getenv("BACKEND_URL", "https://yepardte-backend-production.up.railway.app")


def enviar_email(destinatario: str, asunto: str, html: str, adjuntos: list = None) -> bool:
    """Envía un email HTML via Resend."""
    if not RESEND_API_KEY:
        print("[EMAIL ERROR] RESEND_API_KEY no configurado")
        return False
    if not destinatario or "@" not in destinatario:
        print(f"[EMAIL ERROR] Destinatario inválido: {destinatario}")
        return False
    try:
        resend.api_key = RESEND_API_KEY
        response = resend.Emails.send({
            "from":    f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>",
            "to":      [destinatario],
            "subject": asunto,
            "html":    html,
        })
        if response and response.get("id"):
            print(f"[EMAIL OK] Enviado a {destinatario} — ID: {response['id']}")
            return True
        print(f"[EMAIL ERROR] Respuesta inesperada: {response}")
        return False
    except Exception as e:
        print(f"[EMAIL ERROR] No se pudo enviar a {destinatario}: {e}")
        return False


# ── Generador de PDF con formato oficial DTE ──────────────────────────────────

def generar_pdf_documento(doc, empresa) -> bytes:
    """
    Genera el PDF del DTE replicando el formato oficial:
    - RUT + tipo doc arriba izquierda
    - Recuadro rojo arriba derecha con número
    - Sección receptor en fondo gris
    - Tabla de items con header oscuro
    - Totales alineados a la derecha
    - Timbre electrónico al pie
    Analogía: la imprenta oficial que produce el documento tributario
    con todos los elementos requeridos por el SII.
    """
    import io
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm, cm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph,
        Spacer, HRFlowable
    )
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER

    # ── Parsear items ─────────────────────────────────────────────────────────
    items_raw = doc.items
    if isinstance(items_raw, str):
        items_list = json.loads(items_raw or "[]")
    elif isinstance(items_raw, list):
        items_list = items_raw
    else:
        items_list = []

    # ── Calcular montos ───────────────────────────────────────────────────────
    es_boleta  = doc.tipo_code == "39" or doc.tipo == "Boleta"
    tipo_label = "BOLETA ELECTRÓNICA" if es_boleta else "FACTURA ELECTRÓNICA"
    neto       = doc.monto_neto  or 0
    iva        = doc.monto_iva   or 0
    total      = doc.monto_total or 0
    folio_str  = str(doc.folio or "").zfill(11)

    # Formatear número con separadores chilenos
    def fmt(n): return f"${n:,.0f}".replace(",", ".")

    # ── Estilos ───────────────────────────────────────────────────────────────
    COLOR_ROJO    = colors.HexColor("#cc0000")
    COLOR_OSCURO  = colors.HexColor("#333333")
    COLOR_GRIS    = colors.HexColor("#f5f5f5")
    COLOR_BORDE   = colors.HexColor("#dddddd")
    COLOR_MUTED   = colors.HexColor("#555555")
    COLOR_HEADER  = colors.HexColor("#333333")

    def estilo(size=9, bold=False, color=colors.black, align=TA_LEFT):
        return ParagraphStyle(
            'x', fontSize=size,
            fontName='Helvetica-Bold' if bold else 'Helvetica',
            textColor=color, alignment=align,
            leading=size * 1.3, spaceAfter=0, spaceBefore=0,
        )

    buffer  = io.BytesIO()
    doc_pdf = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=12*mm, bottomMargin=12*mm,
        leftMargin=12*mm, rightMargin=12*mm,
    )
    elementos = []

    # ── 1. HEADER: emisor izquierda + recuadro rojo derecha ───────────────────
    empresa_nombre = getattr(empresa, 'razon_social', None) or empresa.nombre or "Empresa"
    empresa_rut    = empresa.rut or "—"
    empresa_giro   = empresa.giro or "—"
    empresa_dir    = f"{empresa.direccion or ''} - {(empresa.comuna or '').upper()} - {(empresa.ciudad or '').upper()}"
    empresa_ciudad = (empresa.ciudad or "SANTIAGO").upper()

    # Columna izquierda — datos emisor
    emisor_data = [
        [Paragraph(f"R.U.T. {empresa_rut}", estilo(12, bold=True))],
        [Paragraph(tipo_label, estilo(16, bold=True))],
        [Paragraph(f"N° {folio_str}", estilo(11, bold=True, color=COLOR_OSCURO))],
        [Paragraph(f"S.I.I. — {empresa_ciudad}", estilo(8, color=COLOR_MUTED))],
        [Spacer(1, 4)],
        [Paragraph(empresa_nombre, estilo(11, bold=True))],
        [Paragraph(f"Giro: {empresa_giro}", estilo(9, color=COLOR_OSCURO))],
        [Paragraph(empresa_dir, estilo(9, color=COLOR_OSCURO))],
    ]
    tabla_emisor = Table(emisor_data, colWidths=[120*mm])
    tabla_emisor.setStyle(TableStyle([
        ("PADDING", (0, 0), (-1, -1), 1),
        ("VALIGN",  (0, 0), (-1, -1), "TOP"),
    ]))

    # Columna derecha — recuadro rojo con tipo y número
    recuadro_data = [
        [Paragraph(tipo_label, estilo(10, bold=True, color=COLOR_ROJO, align=TA_CENTER))],
        [Paragraph(f"N° {folio_str}", estilo(18, bold=True, color=COLOR_ROJO, align=TA_CENTER))],
    ]
    tabla_recuadro = Table(recuadro_data, colWidths=[60*mm])
    tabla_recuadro.setStyle(TableStyle([
        ("BOX",     (0, 0), (-1, -1), 2, COLOR_ROJO),
        ("ROUNDED", (0, 0), (-1, -1), 4),
        ("PADDING", (0, 0), (-1, -1), 8),
        ("VALIGN",  (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",   (0, 0), (-1, -1), "CENTER"),
    ]))

    tabla_header = Table(
        [[tabla_emisor, tabla_recuadro]],
        colWidths=[125*mm, 61*mm],
    )
    tabla_header.setStyle(TableStyle([
        ("VALIGN",  (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 0),
    ]))
    elementos.append(tabla_header)
    elementos.append(HRFlowable(width="100%", thickness=2, color=colors.black, spaceAfter=6))

    # ── 2. AVISO sin certificación ────────────────────────────────────────────
    if not getattr(doc, 'certificado', False):
        aviso = Table(
            [[Paragraph(
                "⚠ DOCUMENTO INTERNO — SIN VALIDEZ FISCAL — PENDIENTE CERTIFICACIÓN DTE",
                estilo(8, bold=True, color=colors.HexColor("#856404"), align=TA_CENTER)
            )]],
            colWidths=[186*mm],
        )
        aviso.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fff3cd")),
            ("BOX",        (0, 0), (-1, -1), 1, colors.HexColor("#ffc107")),
            ("PADDING",    (0, 0), (-1, -1), 5),
        ]))
        elementos.append(aviso)
        elementos.append(Spacer(1, 4))

    # ── 3. RECEPTOR ───────────────────────────────────────────────────────────
    def campo_receptor(label, valor):
        return [
            Paragraph(label, estilo(7, bold=True, color=COLOR_MUTED)),
            Paragraph(str(valor or ""), estilo(9, bold=True)),
        ]

    fecha_emision = doc.fecha.strftime("%d/%m/%Y") if hasattr(doc.fecha, 'strftime') else str(doc.fecha)[:10]

    receptor_data = [
        [
            Paragraph("SEÑOR(ES):", estilo(7, bold=True, color=COLOR_MUTED)),
            Paragraph(doc.receptor_nombre or "—", estilo(9, bold=True)),
            Paragraph("", estilo(7)),
            Paragraph("", estilo(9)),
        ],
        [
            Paragraph("R.U.T.:", estilo(7, bold=True, color=COLOR_MUTED)),
            Paragraph(doc.receptor_rut or "—", estilo(9, bold=True)),
            Paragraph("GIRO:", estilo(7, bold=True, color=COLOR_MUTED)),
            Paragraph(doc.receptor_giro or "—", estilo(9, bold=True)),
        ],
        [
            Paragraph("DIRECCIÓN:", estilo(7, bold=True, color=COLOR_MUTED)),
            Paragraph(doc.receptor_direccion or "—", estilo(9, bold=True)),
            Paragraph("", estilo(7)),
            Paragraph("", estilo(9)),
        ],
        [
            Paragraph("FECHA EMISIÓN:", estilo(7, bold=True, color=COLOR_MUTED)),
            Paragraph(fecha_emision, estilo(9, bold=True)),
            Paragraph("CONDICIÓN PAGO:", estilo(7, bold=True, color=COLOR_MUTED)),
            Paragraph("Contado", estilo(9, bold=True)),
        ],
    ]
    tabla_receptor = Table(receptor_data, colWidths=[28*mm, 65*mm, 28*mm, 65*mm])
    tabla_receptor.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_GRIS),
        ("BOX",        (0, 0), (-1, -1), 1, COLOR_BORDE),
        ("GRID",       (0, 0), (-1, -1), 0.3, COLOR_BORDE),
        ("PADDING",    (0, 0), (-1, -1), 4),
        ("VALIGN",     (0, 0), (-1, -1), "TOP"),
        ("SPAN",       (1, 0), (3, 0)),  # nombre ocupa todo el ancho
        ("SPAN",       (1, 2), (3, 2)),  # dirección ocupa todo el ancho
    ]))
    elementos.append(tabla_receptor)
    elementos.append(Spacer(1, 6))

    # ── 4. TABLA DE ÍTEMS ─────────────────────────────────────────────────────
    items_header = [
        Paragraph("N°",          estilo(8, bold=True, color=colors.white, align=TA_CENTER)),
        Paragraph("CÓDIGO",      estilo(8, bold=True, color=colors.white)),
        Paragraph("DESCRIPCIÓN", estilo(8, bold=True, color=colors.white)),
        Paragraph("CANT.",       estilo(8, bold=True, color=colors.white, align=TA_RIGHT)),
        Paragraph("PRECIO UNIT.",estilo(8, bold=True, color=colors.white, align=TA_RIGHT)),
        Paragraph("%DESC.",      estilo(8, bold=True, color=colors.white, align=TA_RIGHT)),
        Paragraph("VALOR",       estilo(8, bold=True, color=colors.white, align=TA_RIGHT)),
    ]
    items_rows = [items_header]
    for i, item in enumerate(items_list):
        qty      = item.get("qty", 1)
        precio   = item.get("precio", 0)
        subtotal = qty * precio
        nombre   = item.get("nombre", item.get("desc", ""))
        items_rows.append([
            Paragraph(str(i + 1),              estilo(9, align=TA_CENTER)),
            Paragraph("",                       estilo(9)),
            Paragraph(nombre,                   estilo(9)),
            Paragraph(str(qty),                 estilo(9, align=TA_RIGHT)),
            Paragraph(fmt(precio),              estilo(9, align=TA_RIGHT)),
            Paragraph("0%",                     estilo(9, align=TA_RIGHT)),
            Paragraph(fmt(subtotal),            estilo(9, align=TA_RIGHT)),
        ])

    tabla_items = Table(
        items_rows,
        colWidths=[10*mm, 18*mm, 80*mm, 15*mm, 25*mm, 15*mm, 23*mm],
    )
    tabla_items.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0),  COLOR_HEADER),
        ("TEXTCOLOR",      (0, 0), (-1, 0),  colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#fafafa")]),
        ("GRID",           (0, 0), (-1, -1), 0.5, COLOR_BORDE),
        ("PADDING",        (0, 0), (-1, -1), 4),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elementos.append(tabla_items)
    elementos.append(Spacer(1, 6))

    # ── 5. TOTALES alineados a la derecha ─────────────────────────────────────
    totales_rows = [
        [Paragraph("MONTO NETO $",  estilo(9, color=COLOR_OSCURO)), Paragraph(fmt(neto),  estilo(9, align=TA_RIGHT))],
        [Paragraph("I.V.A. 19% $",  estilo(9, color=COLOR_OSCURO)), Paragraph(fmt(iva),   estilo(9, align=TA_RIGHT))],
        [Paragraph("TOTAL $",        estilo(11, bold=True)),          Paragraph(fmt(total), estilo(11, bold=True, align=TA_RIGHT))],
    ]
    tabla_totales = Table(totales_rows, colWidths=[30*mm, 30*mm], hAlign="RIGHT")
    tabla_totales.setStyle(TableStyle([
        ("GRID",      (0, 0), (-1, -2), 0.5, COLOR_BORDE),
        ("LINEABOVE", (0, -1), (-1, -1), 2, colors.black),
        ("LINEBELOW", (0, -1), (-1, -1), 2, colors.black),
        ("PADDING",   (0, 0),  (-1, -1), 4),
        ("ALIGN",     (1, 0),  (1, -1),  "RIGHT"),
    ]))
    elementos.append(tabla_totales)
    elementos.append(Spacer(1, 12))

    # ── 6. TIMBRE ELECTRÓNICO ─────────────────────────────────────────────────
    elementos.append(HRFlowable(width="100%", thickness=2, color=colors.black, spaceAfter=6))
    timbre_data = [[
        Table([
            [Paragraph("TIMBRE ELECTRÓNICO SII", estilo(8, bold=True))],
            [Paragraph("Verifique documento en: www.sii.cl", estilo(8, color=COLOR_MUTED))],
        ], colWidths=[120*mm]),
        Table([
            [Paragraph(tipo_label,             estilo(8, align=TA_RIGHT))],
            [Paragraph(f"N° {folio_str}",      estilo(8, align=TA_RIGHT))],
            [Paragraph(f"Emisión: {fecha_emision}", estilo(8, align=TA_RIGHT))],
            [Paragraph(f"RUT: {empresa_rut}",  estilo(8, align=TA_RIGHT))],
        ], colWidths=[66*mm]),
    ]]
    tabla_timbre = Table(timbre_data, colWidths=[120*mm, 66*mm])
    tabla_timbre.setStyle(TableStyle([
        ("VALIGN",  (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 0),
    ]))
    elementos.append(tabla_timbre)

    # ── 7. FOOTER ─────────────────────────────────────────────────────────────
    elementos.append(Spacer(1, 8))
    elementos.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_BORDE))
    elementos.append(Spacer(1, 3))
    elementos.append(Paragraph(
        "Generado con YeparDTE · by YeparSolutions · yepardte.yeparsolutions.com",
        estilo(7, color=colors.HexColor("#999999"), align=TA_CENTER)
    ))

    doc_pdf.build(elementos)
    return buffer.getvalue()


# ── Templates HTML ────────────────────────────────────────────────────────────

def template_codigo_verificacion(nombre: str, codigo: str) -> str:
    logo_url    = f"{FRONTEND_URL}/logo-1200x520.png"
    isotipo_url = f"{FRONTEND_URL}/IsotipoYS.png"
    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Código de verificación — YeparDTE</title></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:40px 20px;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
        <tr><td style="padding:32px 40px 24px;text-align:center;border-bottom:1px solid #e2e8f0;">
          <img src="{logo_url}" alt="YeparDTE" width="200" height="auto"
               style="display:block;margin:0 auto;" onerror="this.style.display='none'">
        </td></tr>
        <tr><td style="padding:40px 40px 32px;text-align:center;">
          <img src="{isotipo_url}" alt="" width="64" height="64"
               style="display:block;margin:0 auto 24px;" onerror="this.style.display='none'">
          <h1 style="margin:0 0 8px;font-size:22px;font-weight:800;color:#0f172a;">HOLA {nombre.upper()}</h1>
          <p style="margin:0 0 8px;font-size:16px;color:#475569;font-weight:600;">AQUÍ ESTÁ TU CÓDIGO</p>
          <p style="margin:0 0 28px;font-size:15px;color:#64748b;">Tu código de verificación es</p>
          <div style="display:inline-block;background:#f0fdf4;border:2px solid #00C77B;
                      border-radius:14px;padding:18px 40px;margin-bottom:28px;">
            <span style="font-family:monospace;font-size:42px;font-weight:900;
                         color:#00C77B;letter-spacing:10px;">{codigo}</span>
          </div>
          <p style="margin:0 0 32px;font-size:14px;color:#94a3b8;">Este código expira en 15 minutos</p>
          <p style="margin:0;font-size:13px;color:#cbd5e1;">
            Si no creaste una cuenta en <span style="color:#00C77B;font-weight:700;">YeparDTE</span>,
            puedes ignorar este mensaje.
          </p>
        </td></tr>
        <tr><td style="background:#f8fafc;padding:20px 40px;border-top:1px solid #e2e8f0;">
          <table width="100%" cellpadding="0" cellspacing="0"><tr>
            <td style="font-size:12px;color:#94a3b8;">
              <a href="https://yeparsolutions.com" style="color:#94a3b8;text-decoration:none;">https://yeparsolutions.com</a>
            </td>
            <td style="font-size:12px;color:#94a3b8;text-align:right;">© 2026 Yepar Solutions SpA.</td>
          </tr></table>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def template_documento_email(
    empresa_nombre: str,
    empresa_rut: str,
    tipo_doc: str,
    numero_doc: str,
    receptor_nombre: str,
    monto_total: int,
    fecha: str,
    doc_id: str = "",
    token: str = "",
) -> str:
    logo_url  = f"{FRONTEND_URL}/logo-1200x520.png"
    monto_fmt = f"${monto_total:,.0f}".replace(",", ".")
    pdf_url   = f"{BACKEND_URL}/api/dte/{doc_id}/pdf-publico?token={token}" if doc_id and token else ""

    boton_pdf = f"""
    <div style="text-align:center;margin:28px 0;">
      <a href="{pdf_url}"
         style="display:inline-block;background:#00C77B;color:#ffffff;
                font-size:15px;font-weight:700;text-decoration:none;
                padding:14px 32px;border-radius:10px;">
        ⬇ Descargar documento PDF
      </a>
    </div>
    """ if pdf_url else ""

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>{tipo_doc} {numero_doc} — {empresa_nombre}</title></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:40px 20px;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
        <tr><td style="padding:32px 40px 24px;text-align:center;border-bottom:1px solid #e2e8f0;">
          <img src="{logo_url}" alt="YeparDTE" width="180" height="auto"
               style="display:block;margin:0 auto;" onerror="this.style.display='none'">
        </td></tr>
        <tr><td style="padding:40px 40px 32px;">
          <h2 style="margin:0 0 8px;font-size:20px;font-weight:800;color:#0f172a;">Hola, {receptor_nombre} 👋</h2>
          <p style="margin:0 0 24px;font-size:15px;color:#475569;line-height:1.6;">
            <strong>{empresa_nombre}</strong> (RUT {empresa_rut}) te ha enviado el siguiente documento tributario electrónico:
          </p>
          <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;padding:24px;margin-bottom:28px;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="padding:8px 0;border-bottom:1px solid #e2e8f0;">
                  <span style="font-size:13px;color:#64748b;">Documento</span>
                </td>
                <td style="padding:8px 0;border-bottom:1px solid #e2e8f0;text-align:right;">
                  <strong style="font-size:14px;color:#0f172a;">{tipo_doc}</strong>
                </td>
              </tr>
              <tr>
                <td style="padding:8px 0;border-bottom:1px solid #e2e8f0;">
                  <span style="font-size:13px;color:#64748b;">Número</span>
                </td>
                <td style="padding:8px 0;border-bottom:1px solid #e2e8f0;text-align:right;">
                  <strong style="font-size:14px;color:#0f172a;font-family:monospace;">{numero_doc}</strong>
                </td>
              </tr>
              <tr>
                <td style="padding:8px 0;border-bottom:1px solid #e2e8f0;">
                  <span style="font-size:13px;color:#64748b;">Fecha emisión</span>
                </td>
                <td style="padding:8px 0;border-bottom:1px solid #e2e8f0;text-align:right;">
                  <span style="font-size:14px;color:#0f172a;">{fecha}</span>
                </td>
              </tr>
              <tr>
                <td style="padding:12px 0 0;">
                  <span style="font-size:15px;font-weight:700;color:#0f172a;">Total</span>
                </td>
                <td style="padding:12px 0 0;text-align:right;">
                  <span style="font-size:20px;font-weight:900;color:#00C77B;">{monto_fmt}</span>
                </td>
              </tr>
            </table>
          </div>
          {boton_pdf}
          <p style="margin:0;font-size:13px;color:#94a3b8;">
            Puedes verificar la autenticidad en
            <a href="https://www.sii.cl" style="color:#00C77B;">www.sii.cl</a>
          </p>
        </td></tr>
        <tr><td style="background:#f8fafc;padding:20px 40px;border-top:1px solid #e2e8f0;">
          <table width="100%" cellpadding="0" cellspacing="0"><tr>
            <td style="font-size:12px;color:#94a3b8;">
              Enviado con <a href="https://yeparsolutions.com" style="color:#00C77B;text-decoration:none;">YeparDTE</a>
            </td>
            <td style="font-size:12px;color:#94a3b8;text-align:right;">© 2026 Yepar Solutions SpA.</td>
          </tr></table>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""
