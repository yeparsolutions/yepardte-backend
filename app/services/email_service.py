# app/services/email_service.py
# ============================================================
# YeparDTE — Servicio de Email via Resend API
# ============================================================

import os
import json
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
    """Envía email HTML via Resend con adjuntos opcionales.
    adjuntos: [{"filename": "doc.pdf", "content": bytes}]
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
        if adjuntos:
            params["attachments"] = [
                {"filename": a["filename"], "content": base64.b64encode(a["content"]).decode("utf-8")}
                for a in adjuntos
            ]
        response = resend.Emails.send(params)
        if response and response.get("id"):
            print(f"[EMAIL OK] Enviado a {destinatario} — ID: {response['id']}")
            return True
        print(f"[EMAIL ERROR] Respuesta inesperada: {response}")
        return False
    except Exception as e:
        print(f"[EMAIL ERROR] No se pudo enviar a {destinatario}: {e}")
        return False


# ── Generador de PDF idéntico al frontend ────────────────────────────────────
# Analogía: la misma imprenta para el email y para la app.

def _html_carta_dte(doc, empresa, logo_base64: str | None, logo_ancho: int) -> str:
    """
    HTML carta A4 compatible con weasyprint.
    Usa SOLO tablas HTML — sin flexbox ni CSS grid
    para garantizar renderizado correcto.
    """
    items_raw = doc.items
    if isinstance(items_raw, str):
        items_list = json.loads(items_raw or "[]")
    elif isinstance(items_raw, list):
        items_list = items_raw
    else:
        items_list = []

    tipo_code  = getattr(doc, "tipo_code", "")
    doc_tipo   = getattr(doc, "tipo", "")
    es_exenta  = tipo_code == "41" or doc_tipo == "Boleta Exenta"
    es_factura_exenta = tipo_code == "33" and doc_tipo in ("Factura Exenta",)
    es_boleta  = tipo_code in ("39", "41") or doc_tipo in ("Boleta", "Boleta Exenta")

    tipo_label = (
        "BOLETA EXENTA ELECTRÓNICA"   if es_exenta else
        "BOLETA ELECTRÓNICA"          if es_boleta else
        "FACTURA EXENTA ELECTRÓNICA"  if es_factura_exenta else
        "FACTURA ELECTRÓNICA"
    )
    color_doc   = "#1a56db" if es_boleta else "#c00"
    neto        = doc.monto_neto   or 0
    iva         = doc.monto_iva    or 0
    total       = doc.monto_total  or 0
    neto_exento = getattr(doc, "monto_exento", 0) or 0
    folio_str   = str(doc.folio or "").zfill(11)
    fecha_str   = doc.fecha.strftime("%d/%m/%Y") if doc.fecha else ""
    cond_pago   = getattr(doc, "condicion_pago", "Contado") or "Contado"

    empresa_nombre = getattr(empresa, "razon_social", None) or empresa.nombre or ""
    empresa_ciudad = (empresa.ciudad or "SANTIAGO").upper()
    empresa_comuna = (empresa.comuna or "").upper()
    empresa_tel    = getattr(empresa, "telefono", "") or ""

    def fmt(n):
        return f"${n:,.0f}".replace(",", ".")

    # ── Header izquierdo: logo o texto ───────────────────────────────────────
    if logo_base64:
        # weasyprint no respeta width= como atributo en SVG
        # el div contenedor fija el espacio y evita que el SVG se agrande
        header_izq = f"""<table cellpadding="0" cellspacing="0"><tr><td>
          <div style="width:{logo_ancho}px;height:80px;overflow:hidden;">
            <img src="{logo_base64}"
                 style="width:{logo_ancho}px;height:80px;object-fit:contain;display:block;" />
          </div>
          <br/>
          <b style="font-size:13px;">{empresa_nombre}</b><br/>
          <span style="font-size:10px;color:#333;">Giro: {empresa.giro or "—"}</span><br/>
          <span style="font-size:10px;color:#333;">{empresa.direccion or ""} - {empresa_comuna} - {empresa_ciudad}</span>
          {"<br/><span style=\"font-size:10px;\">Tel: " + empresa_tel + "</span>" if empresa_tel else ""}
        </td></tr></table>"""
    else:
        header_izq = f"""<span style="font-size:14px;font-weight:bold;">R.U.T. {empresa.rut}</span><br/>
        <span style="font-size:18px;font-weight:bold;">{tipo_label}</span><br/>
        <span style="font-size:13px;font-weight:bold;color:#333;">N&deg; {folio_str}</span><br/>
        <span style="font-size:10px;color:#555;">S.I.I. &mdash; {empresa_ciudad}</span><br/><br/>
        <b style="font-size:13px;">{empresa_nombre}</b><br/>
        <span style="font-size:10px;color:#333;">Giro: {empresa.giro or "—"}</span><br/>
        <span style="font-size:10px;color:#333;">{empresa.direccion or ""} - {empresa_comuna} - {empresa_ciudad}</span>
        {"<br/><span style=\"font-size:10px;\">Tel: " + empresa_tel + "</span>" if empresa_tel else ""}"""

    # ── Filas de items ───────────────────────────────────────────────────────
    items_rows = ""
    for i, item in enumerate(items_list):
        qty      = item.get("qty", item.get("cant", 1))
        precio   = item.get("precio", item.get("precioUnit", 0))
        subtotal = qty * precio
        nombre   = item.get("nombre", item.get("desc", item.get("descripcion", "")))
        bg = "#fafafa" if i % 2 == 1 else "#fff"
        items_rows += f"""<tr style="background:{bg};">
          <td style="padding:4px 6px;font-size:10px;border-bottom:1px solid #eee;text-align:center;">{i+1}</td>
          <td style="padding:4px 6px;font-size:10px;border-bottom:1px solid #eee;">{item.get("codigo","")}</td>
          <td style="padding:4px 6px;font-size:10px;border-bottom:1px solid #eee;">{nombre}</td>
          <td style="padding:4px 6px;font-size:10px;border-bottom:1px solid #eee;text-align:right;">{qty}</td>
          <td style="padding:4px 6px;font-size:10px;border-bottom:1px solid #eee;text-align:right;">{fmt(precio)}</td>
          <td style="padding:4px 6px;font-size:10px;border-bottom:1px solid #eee;text-align:right;">{item.get("descuento",0)}%</td>
          <td style="padding:4px 6px;font-size:10px;border-bottom:1px solid #eee;text-align:right;">{fmt(subtotal)}</td>
        </tr>"""

    # ── Totales ──────────────────────────────────────────────────────────────
    if es_exenta:
        totales_rows = f"""
          <tr><td style="padding:3px 0;font-size:11px;border-bottom:1px solid #eee;color:#333;">MONTO NETO $</td>
              <td style="padding:3px 0;font-size:11px;border-bottom:1px solid #eee;text-align:right;">$0</td></tr>
          <tr><td style="padding:3px 0;font-size:11px;border-bottom:1px solid #eee;color:#333;">MONTO EXENTO $</td>
              <td style="padding:3px 0;font-size:11px;border-bottom:1px solid #eee;text-align:right;">{fmt(neto_exento)}</td></tr>
          <tr><td style="padding:3px 0;font-size:11px;border-bottom:1px solid #eee;color:#333;">I.V.A. 19% $</td>
              <td style="padding:3px 0;font-size:11px;border-bottom:1px solid #eee;text-align:right;">
                <span style="font-size:9px;font-weight:bold;color:#1a56db;background:#e8f0fe;border:1px solid #a8c0f8;border-radius:3px;padding:1px 5px;">EXENTO</span>
              </td></tr>
          <tr><td style="padding:5px 0;font-size:13px;font-weight:bold;border-bottom:2px solid #000;color:#333;">TOTAL $</td>
              <td style="padding:5px 0;font-size:13px;font-weight:bold;border-bottom:2px solid #000;text-align:right;">{fmt(total)}</td></tr>"""
    else:
        totales_rows = f"""
          <tr><td style="padding:3px 0;font-size:11px;border-bottom:1px solid #eee;color:#333;">MONTO NETO $</td>
              <td style="padding:3px 0;font-size:11px;border-bottom:1px solid #eee;text-align:right;">{fmt(neto)}</td></tr>
          <tr><td style="padding:3px 0;font-size:11px;border-bottom:1px solid #eee;color:#333;">I.V.A. 19% $</td>
              <td style="padding:3px 0;font-size:11px;border-bottom:1px solid #eee;text-align:right;">{fmt(iva)}</td></tr>
          <tr><td style="padding:5px 0;font-size:13px;font-weight:bold;border-bottom:2px solid #000;color:#333;">TOTAL $</td>
              <td style="padding:5px 0;font-size:13px;font-weight:bold;border-bottom:2px solid #000;text-align:right;">{fmt(total)}</td></tr>"""

    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8">
<title>{tipo_label} N&deg; {doc.numero}</title>
<style>
  @page {{ size: A4 portrait; margin: 12mm; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html, body {{ width: 210mm; font-family:Arial,Helvetica,sans-serif; font-size:11px; color:#000; background:#fff; }}
  table {{ border-collapse: collapse; }}
</style>
</head><body style="width:186mm; margin:0; padding:0;">

<!-- HEADER: emisor izq + doc-box der -->
<table width="100%" cellpadding="0" cellspacing="0"
       style="border-bottom:2px solid #000;padding-bottom:8px;margin-bottom:8px;">
  <tr>
    <td style="vertical-align:top;padding-right:12px;">{header_izq}</td>
    <td style="vertical-align:top;text-align:center;white-space:nowrap;">
      <table cellpadding="8" cellspacing="0"
             style="border:2px solid {color_doc};border-radius:4px;min-width:160px;">
        <tr><td style="text-align:center;">
          <div style="font-size:11px;font-weight:bold;color:{color_doc};margin-bottom:4px;">R.U.T. {empresa.rut}</div>
          <div style="font-size:12px;font-weight:bold;color:{color_doc};margin-bottom:4px;">{tipo_label}</div>
          <div style="font-size:22px;font-weight:bold;color:{color_doc};">N&deg; {folio_str}</div>
        </td></tr>
      </table>
    </td>
  </tr>
</table>

<!-- RECEPTOR -->
<table width="100%" cellpadding="0" cellspacing="0"
       style="background:#f5f5f5;border:1px solid #ddd;border-radius:3px;padding:8px 10px;margin-bottom:10px;">
  <tr>
    <td colspan="3" style="padding:3px 0;">
      <span style="font-size:9px;font-weight:bold;text-transform:uppercase;color:#666;">SE&Ntilde;OR(ES):</span>
      <span style="font-size:11px;font-weight:600;border-bottom:1px solid #ccc;padding-bottom:1px;">
        &nbsp;{doc.receptor_nombre or ""}</span>
    </td>
  </tr>
  <tr>
    <td width="50%" style="padding:3px 0;padding-right:16px;">
      <span style="font-size:9px;font-weight:bold;text-transform:uppercase;color:#666;">R.U.T.:</span>
      <span style="font-size:11px;font-weight:600;">&nbsp;{doc.receptor_rut or ""}</span>
    </td>
    <td width="50%" style="padding:3px 0;">
      <span style="font-size:9px;font-weight:bold;text-transform:uppercase;color:#666;">GIRO:</span>
      <span style="font-size:11px;font-weight:600;">&nbsp;{doc.receptor_giro or ""}</span>
    </td>
  </tr>
  <tr>
    <td colspan="3" style="padding:3px 0;">
      <span style="font-size:9px;font-weight:bold;text-transform:uppercase;color:#666;">DIRECCI&Oacute;N:</span>
      <span style="font-size:11px;font-weight:600;">&nbsp;{doc.receptor_direccion or ""}</span>
    </td>
  </tr>
  <tr>
    <td width="50%" style="padding:3px 0;padding-right:16px;">
      <span style="font-size:9px;font-weight:bold;text-transform:uppercase;color:#666;">FECHA EMISI&Oacute;N:</span>
      <span style="font-size:11px;font-weight:600;">&nbsp;{fecha_str}</span>
    </td>
    <td width="50%" style="padding:3px 0;">
      <span style="font-size:9px;font-weight:bold;text-transform:uppercase;color:#666;">CONDICI&Oacute;N PAGO:</span>
      <span style="font-size:11px;font-weight:600;">&nbsp;{cond_pago}</span>
    </td>
  </tr>
</table>

<!-- ITEMS -->
<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin-bottom:10px;">
  <thead>
    <tr style="background:#333;">
      <th style="padding:5px 6px;font-size:9px;font-weight:bold;text-transform:uppercase;color:#fff;text-align:center;width:30px;">N&deg;</th>
      <th style="padding:5px 6px;font-size:9px;font-weight:bold;text-transform:uppercase;color:#fff;text-align:left;">Codigo</th>
      <th style="padding:5px 6px;font-size:9px;font-weight:bold;text-transform:uppercase;color:#fff;text-align:left;">Descripcion</th>
      <th style="padding:5px 6px;font-size:9px;font-weight:bold;text-transform:uppercase;color:#fff;text-align:right;">Cant.</th>
      <th style="padding:5px 6px;font-size:9px;font-weight:bold;text-transform:uppercase;color:#fff;text-align:right;">Precio Unit.</th>
      <th style="padding:5px 6px;font-size:9px;font-weight:bold;text-transform:uppercase;color:#fff;text-align:right;">%Desc.</th>
      <th style="padding:5px 6px;font-size:9px;font-weight:bold;text-transform:uppercase;color:#fff;text-align:right;">Valor</th>
    </tr>
  </thead>
  <tbody>{items_rows}</tbody>
</table>

<!-- TOTALES alineados a la derecha -->
<table width="100%" cellpadding="0" cellspacing="0" style="margin-bottom:12px;">
  <tr>
    <td width="55%"></td>
    <td width="45%">
      <table width="100%" cellpadding="0" cellspacing="0">{totales_rows}</table>
    </td>
  </tr>
</table>

<!-- TIMBRE -->
<table width="100%" cellpadding="0" cellspacing="0"
       style="border-top:2px solid #000;padding-top:8px;">
  <tr>
    <td style="vertical-align:top;">
      <div style="font-size:9px;font-weight:bold;text-transform:uppercase;margin-bottom:4px;">Timbre Electr&oacute;nico SII</div>
      <div style="font-size:9px;color:#555;">Verifique documento en: www.sii.cl</div>
    </td>
    <td style="text-align:right;font-size:9px;vertical-align:top;">
      {tipo_label}<br/>N&deg; {folio_str}<br/>
      Emisi&oacute;n: {fecha_str}<br/>RUT: {empresa.rut}
    </td>
  </tr>
</table>

<div style="margin-top:20px;border-top:1px solid #ccc;padding-top:6px;font-size:8px;color:#999;text-align:center;">
  Generado con YeparDTE &middot; by YeparSolutions &middot; yepardte.yeparsolutions.com
</div>

</body></html>"""


def generar_pdf_documento(doc, empresa) -> bytes:
    """Genera PDF con mismo HTML que el frontend usando weasyprint."""
    logo_base64 = None
    logo_ancho  = getattr(empresa, "logo_ancho", 70) or 70
    if getattr(empresa, "logo", None):
        raw  = empresa.logo
        mime = "image/png"
        if len(raw) >= 2 and raw[:2] == b"\xff\xd8": mime = "image/jpeg"
        elif b"<svg" in raw[:200]:                      mime = "image/svg+xml"
        elif len(raw) >= 4 and raw[:4] == b"RIFF":      mime = "image/webp"
        logo_base64 = f"data:{mime};base64,{base64.b64encode(raw).decode()}"

    html = _html_carta_dte(doc, empresa, logo_base64, logo_ancho)
    try:
        from weasyprint import HTML as WeasyprintHTML
        return WeasyprintHTML(string=html).write_pdf()
    except ImportError:
        raise RuntimeError("weasyprint no instalado. Agrega 'weasyprint' a requirements.txt")
    except Exception as e:
        raise RuntimeError(f"Error generando PDF: {e}")


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
        📄 Ver y descargar documento
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
