# app/services/email_service.py
# ============================================================
# YeparDTE — Servicio de Email
# Envío de correos transaccionales via Resend API
# ============================================================

import os
import base64
import resend
from dotenv import load_dotenv

load_dotenv()

RESEND_API_KEY  = os.getenv("RESEND_API_KEY", "")
EMAIL_FROM      = os.getenv("EMAIL_FROM",      "soporte@yeparsolutions.com")
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "YeparDTE")
FRONTEND_URL    = os.getenv("VITE_FRONTEND_URL", "https://yepardte.yeparsolutions.com")
BACKEND_URL     = os.getenv("BACKEND_URL", "https://yepardte-backend-production.up.railway.app")


def enviar_email(destinatario: str, asunto: str, html: str, adjuntos: list = None) -> bool:
    """
    Envía un email HTML via Resend.
    adjuntos: ignorado en plan gratuito — el PDF va como link en el HTML.
    """
    if not RESEND_API_KEY:
        print("[EMAIL ERROR] RESEND_API_KEY no configurado")
        return False

    if not destinatario or "@" not in destinatario:
        print(f"[EMAIL ERROR] Destinatario inválido: {destinatario}")
        return False

    try:
        resend.api_key = RESEND_API_KEY

        params = {
            "from":    f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>",
            "to":      [destinatario],
            "subject": asunto,
            "html":    html,
        }

        response = resend.Emails.send(params)

        if response and response.get("id"):
            print(f"[EMAIL OK] Enviado a {destinatario} — ID: {response['id']}")
            return True
        else:
            print(f"[EMAIL ERROR] Respuesta inesperada: {response}")
            return False

    except Exception as e:
        print(f"[EMAIL ERROR] No se pudo enviar a {destinatario}: {e}")
        return False


# ── Generador de PDF (usado internamente si se necesita) ──────────────────────

def generar_pdf_documento(doc, empresa) -> bytes:
    """
    Genera el PDF del documento DTE usando reportlab.
    Retorna los bytes del PDF.
    """
    import io
    import json
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm

    buffer  = io.BytesIO()
    doc_pdf = SimpleDocTemplate(buffer, pagesize=letter,
                                topMargin=2*cm, bottomMargin=2*cm,
                                leftMargin=2*cm, rightMargin=2*cm)

    styles    = getSampleStyleSheet()
    elementos = []

    estilo_titulo = ParagraphStyle('titulo', parent=styles['Heading1'], fontSize=16, spaceAfter=4)
    estilo_sub    = ParagraphStyle('sub',    parent=styles['Normal'],   fontSize=10, textColor=colors.grey)
    estilo_bold   = ParagraphStyle('bold',   parent=styles['Normal'],   fontSize=11, fontName='Helvetica-Bold')
    estilo_normal = ParagraphStyle('normal', parent=styles['Normal'],   fontSize=10)

    elementos.append(Paragraph(empresa.nombre or "Empresa", estilo_titulo))
    elementos.append(Paragraph(f"RUT: {empresa.rut or '—'}", estilo_sub))
    elementos.append(Paragraph(f"Giro: {empresa.giro or '—'}", estilo_sub))
    elementos.append(Paragraph(f"Dirección: {empresa.direccion or '—'}, {empresa.comuna or ''}", estilo_sub))
    elementos.append(Spacer(1, 0.5*cm))

    elementos.append(Paragraph(f"{doc.tipo} Electrónica N° {doc.numero}", estilo_bold))
    if doc.folio:
        elementos.append(Paragraph(f"Folio: {doc.folio}", estilo_sub))
    elementos.append(Paragraph(f"Fecha: {doc.fecha.strftime('%d/%m/%Y %H:%M')}", estilo_sub))
    elementos.append(Spacer(1, 0.5*cm))

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

    items_raw = doc.items
    if isinstance(items_raw, str):
        items_list = json.loads(items_raw or "[]")
    elif isinstance(items_raw, list):
        items_list = items_raw
    else:
        items_list = []

    items_data = [["Descripción", "Qty", "Precio unit.", "Subtotal"]]
    for item in items_list:
        subtotal = item.get("precio", 0) * item.get("qty", 1)
        items_data.append([
            item.get("nombre", item.get("desc", "")),
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

    elementos.append(Spacer(1, 1*cm))
    elementos.append(Paragraph(f"Estado SII: {doc.estado or '—'}", estilo_sub))
    if doc.track_id:
        elementos.append(Paragraph(f"Track ID: {doc.track_id}", estilo_sub))

    doc_pdf.build(elementos)
    return buffer.getvalue()


# ── Templates HTML ────────────────────────────────────────────────────────────

def template_codigo_verificacion(nombre: str, codigo: str) -> str:
    logo_url    = f"{FRONTEND_URL}/logo-1200x520.png"
    isotipo_url = f"{FRONTEND_URL}/IsotipoYS.png"

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Código de verificación — YeparDTE</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:40px 20px;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
        <tr>
          <td style="background:#ffffff;padding:32px 40px 24px;text-align:center;border-bottom:1px solid #e2e8f0;">
            <img src="{logo_url}" alt="YeparDTE" width="200" height="auto"
                 style="display:block;margin:0 auto;" onerror="this.style.display='none'">
          </td>
        </tr>
        <tr>
          <td style="padding:40px 40px 32px;text-align:center;">
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
          </td>
        </tr>
        <tr>
          <td style="background:#f8fafc;padding:20px 40px;border-top:1px solid #e2e8f0;">
            <table width="100%" cellpadding="0" cellspacing="0"><tr>
              <td style="font-size:12px;color:#94a3b8;">
                <a href="https://yeparsolutions.com" style="color:#94a3b8;text-decoration:none;">https://yeparsolutions.com</a>
              </td>
              <td style="font-size:12px;color:#94a3b8;text-align:right;">© 2026 Yepar Solutions SpA.</td>
            </tr></table>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


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
    """
    Email con botón de descarga PDF en vez de adjunto.
    Analogía: en vez de meter el documento en el sobre,
    le damos al receptor la dirección donde puede retirarlo.
    """
    logo_url  = f"{FRONTEND_URL}/logo-1200x520.png"
    monto_fmt = f"${monto_total:,.0f}".replace(",", ".")

    # Link de descarga del PDF con token temporal
    pdf_url = f"{BACKEND_URL}/api/dte/{doc_id}/pdf-publico?token={token}" if doc_id and token else ""

    boton_pdf = f"""
    <div style="text-align:center;margin:28px 0;">
      <a href="{pdf_url}"
         style="display:inline-block;background:#00C77B;color:#ffffff;
                font-size:15px;font-weight:700;text-decoration:none;
                padding:14px 32px;border-radius:10px;letter-spacing:0.3px;">
        ⬇ Descargar documento PDF
      </a>
    </div>
    """ if pdf_url else """
    <p style="margin:0 0 8px;font-size:14px;color:#475569;line-height:1.6;">
      Puedes solicitar el PDF directamente al emisor.
    </p>
    """

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{tipo_doc} {numero_doc} — {empresa_nombre}</title>
</head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:40px 20px;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
        <tr>
          <td style="background:#ffffff;padding:32px 40px 24px;text-align:center;border-bottom:1px solid #e2e8f0;">
            <img src="{logo_url}" alt="YeparDTE" width="180" height="auto"
                 style="display:block;margin:0 auto;" onerror="this.style.display='none'">
          </td>
        </tr>
        <tr>
          <td style="padding:40px 40px 32px;">
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
          </td>
        </tr>
        <tr>
          <td style="background:#f8fafc;padding:20px 40px;border-top:1px solid #e2e8f0;">
            <table width="100%" cellpadding="0" cellspacing="0"><tr>
              <td style="font-size:12px;color:#94a3b8;">
                Enviado con <a href="https://yeparsolutions.com" style="color:#00C77B;text-decoration:none;">YeparDTE</a>
              </td>
              <td style="font-size:12px;color:#94a3b8;text-align:right;">© 2026 Yepar Solutions SpA.</td>
            </tr></table>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
