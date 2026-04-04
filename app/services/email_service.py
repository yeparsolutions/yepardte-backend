# app/services/email_service.py
# ============================================================
# YeparDTE — Servicio de Email via Resend API
# El PDF adjunto usa el mismo HTML que el frontend (generarPDF.js)
# para que el receptor reciba exactamente lo que ve en la app.
# Analogía: la misma imprenta para el email y para la pantalla.
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
    """
    Envía un email HTML via Resend con adjuntos opcionales.
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
        # Adjuntar archivos — Resend espera content en base64
        if adjuntos:
            params["attachments"] = [
                {
                    "filename": a["filename"],
                    "content":  base64.b64encode(a["content"]).decode("utf-8"),
                }
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


# ── Generador de PDF — mismo HTML que generarPDF.js del frontend ──────────────

def _html_carta_dte(doc, empresa, logo_base64: str | None, logo_ancho: int) -> str:
    """
    Replica el htmlCarta() de generarPDF.js del frontend.
    Carta A4 idéntica a la que ve el usuario en la app.
    """
    items_raw = doc.items
    if isinstance(items_raw, str):
        items_list = json.loads(items_raw or "[]")
    elif isinstance(items_raw, list):
        items_list = items_raw
    else:
        items_list = []

    es_exenta  = getattr(doc, "tipo_code", "") == "41"
    es_boleta  = getattr(doc, "tipo_code", "") in ("39", "41") or doc.tipo in ("Boleta", "Boleta Exenta")
    tipo_label = (
        "BOLETA EXENTA ELECTRÓNICA" if es_exenta else
        "BOLETA ELECTRÓNICA"        if es_boleta else
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

    # ── Filas de items ────────────────────────────────────────────────────────
    items_html = ""
    for i, item in enumerate(items_list):
        qty      = item.get("qty", item.get("cant", 1))
        precio   = item.get("precio", item.get("precioUnit", 0))
        subtotal = qty * precio
        nombre   = item.get("nombre", item.get("desc", item.get("descripcion", "")))
        items_html += f"""
      <tr>
        <td class="num">{i + 1}</td>
        <td>{item.get("codigo", "")}</td>
        <td>{nombre}</td>
        <td class="right">{qty}</td>
        <td class="right">{fmt(precio)}</td>
        <td class="right">{item.get("descuento", 0)}%</td>
        <td class="right">{fmt(subtotal)}</td>
      </tr>"""

    # ── Totales ───────────────────────────────────────────────────────────────
    if es_exenta:
        totales_html = f"""
    <div class="total-row"><span class="total-label">MONTO NETO $</span><span>$0</span></div>
    <div class="total-row"><span class="total-label">MONTO EXENTO $</span><span>{fmt(neto_exento)}</span></div>
    <div class="total-row"><span class="total-label">I.V.A. 19% $</span>
      <span style="font-size:9px;font-weight:bold;color:#1a56db;background:#e8f0fe;
                   border:1px solid #a8c0f8;border-radius:4px;padding:1px 6px;">EXENTO</span></div>
    <div class="total-row final"><span class="total-label">TOTAL $</span><span>{fmt(total)}</span></div>"""
    else:
        totales_html = f"""
    <div class="total-row"><span class="total-label">MONTO NETO $</span><span>{fmt(neto)}</span></div>
    <div class="total-row"><span class="total-label">I.V.A. 19% $</span><span>{fmt(iva)}</span></div>
    <div class="total-row final"><span class="total-label">TOTAL $</span><span>{fmt(total)}</span></div>"""

    # ── Header izquierdo — logo si existe, texto si no ───────────────────────
    if logo_base64:
        header_izq = f"""
      <div style="display:flex;flex-direction:column;align-items:flex-start;gap:4px;">
        <img src="{logo_base64}"
             style="width:{logo_ancho}px;height:auto;max-height:90px;object-fit:contain;" />
        <div style="margin-top:6px;">
          <div class="emisor-nombre">{empresa_nombre}</div>
          <div class="emisor-datos">
            Giro: {empresa.giro or "—"}<br/>
            {empresa.direccion or ""} - {empresa_comuna} - {empresa_ciudad}<br/>
            {"Tel: " + empresa_tel if empresa_tel else ""}
          </div>
        </div>
      </div>"""
    else:
        header_izq = f"""
      <div class="emisor-rut">R.U.T. {empresa.rut}</div>
      <div class="emisor-tipo">{tipo_label}</div>
      <div class="emisor-num">N° {folio_str}</div>
      <div class="sii-logo">S.I.I. — {empresa_ciudad}</div><br/>
      <div class="emisor-nombre">{empresa_nombre}</div>
      <div class="emisor-datos">
        Giro: {empresa.giro or "—"}<br/>
        {empresa.direccion or ""} - {empresa_comuna} - {empresa_ciudad}<br/>
        {"Tel: " + empresa_tel if empresa_tel else ""}
      </div>"""

    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="UTF-8">
<title>{tipo_label} N° {doc.numero}</title>
<style>
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{font-family:Arial,Helvetica,sans-serif;font-size:11px;color:#000;background:#fff}}
  .page{{width:210mm;min-height:297mm;padding:12mm;position:relative}}
  .header{{display:flex;justify-content:space-between;align-items:flex-start;
           margin-bottom:8px;border-bottom:2px solid #000;padding-bottom:8px}}
  .header-left{{flex:1}}
  .emisor-rut{{font-size:14px;font-weight:bold;margin-bottom:2px}}
  .emisor-tipo{{font-size:18px;font-weight:bold;margin-bottom:2px}}
  .emisor-num{{font-size:13px;font-weight:bold;color:#333;margin-bottom:4px}}
  .sii-logo{{font-size:10px;color:#555;margin-bottom:4px}}
  .emisor-nombre{{font-size:13px;font-weight:bold;margin-bottom:2px}}
  .emisor-datos{{font-size:10px;color:#333;line-height:1.5}}
  .doc-box{{border:2px solid {color_doc};border-radius:4px;padding:8px 14px;
            text-align:center;min-width:160px}}
  .doc-box-rut{{font-size:11px;font-weight:bold;color:{color_doc};
                margin-bottom:4px;letter-spacing:0.3px}}
  .doc-box-tipo{{font-size:12px;font-weight:bold;color:{color_doc};margin-bottom:4px}}
  .doc-box-num{{font-size:22px;font-weight:bold;color:{color_doc}}}
  .receptor-section{{background:#f5f5f5;border:1px solid #ddd;border-radius:3px;
                     padding:8px 10px;margin-bottom:10px}}
  .receptor-grid{{display:grid;grid-template-columns:1fr 1fr;gap:4px 16px}}
  .r-field{{display:flex;gap:4px;align-items:baseline}}
  .r-label{{font-size:9px;font-weight:bold;text-transform:uppercase;
            color:#666;white-space:nowrap}}
  .r-val{{font-size:11px;font-weight:600;border-bottom:1px solid #ccc;
          flex:1;min-width:0;word-break:break-all}}
  .r-full{{grid-column:1/-1}}
  .items-table{{width:100%;border-collapse:collapse;margin-bottom:10px}}
  .items-table th{{background:#333;color:#fff;font-size:9px;font-weight:bold;
                   text-transform:uppercase;padding:5px 6px;text-align:left}}
  .items-table th.right{{text-align:right}}
  .items-table td{{padding:5px 6px;font-size:10px;border-bottom:1px solid #eee}}
  .items-table td.right{{text-align:right}}
  .items-table tr:nth-child(even) td{{background:#fafafa}}
  .items-table .num{{width:30px;text-align:center}}
  .totales-wrap{{display:flex;justify-content:flex-end;margin-bottom:12px}}
  .totales-box{{width:220px}}
  .total-row{{display:flex;justify-content:space-between;padding:3px 0;
              font-size:11px;border-bottom:1px solid #eee}}
  .total-row.final{{font-size:13px;font-weight:bold;
                    border-bottom:2px solid #000;padding:5px 0}}
  .total-label{{color:#333}}
  .timbre-section{{border-top:2px solid #000;padding-top:8px;
                   display:flex;justify-content:space-between;align-items:flex-start}}
  .timbre-left{{flex:1}}
  .timbre-title{{font-size:9px;font-weight:bold;text-transform:uppercase;margin-bottom:4px}}
  .timbre-sii{{font-size:9px;color:#555}}
  .timbre-right{{text-align:right;font-size:9px}}
  .footer{{margin-top:20px;border-top:1px solid #ccc;padding-top:6px;
           font-size:8px;color:#999;text-align:center}}
</style></head><body>
<div class="page">
  <div class="header">
    <div class="header-left">{header_izq}</div>
    <div class="doc-box">
      <div class="doc-box-rut">R.U.T. {empresa.rut}</div>
      <div class="doc-box-tipo">{tipo_label}</div>
      <div class="doc-box-num">N° {folio_str}</div>
    </div>
  </div>
  <div class="receptor-section">
    <div class="receptor-grid">
      <div class="r-field r-full">
        <span class="r-label">SEÑOR(ES):</span>
        <span class="r-val">{doc.receptor_nombre or ""}</span>
      </div>
      <div class="r-field">
        <span class="r-label">R.U.T.:</span>
        <span class="r-val">{doc.receptor_rut or ""}</span>
      </div>
      <div class="r-field">
        <span class="r-label">GIRO:</span>
        <span class="r-val">{doc.receptor_giro or ""}</span>
      </div>
      <div class="r-field r-full">
        <span class="r-label">DIRECCIÓN:</span>
        <span class="r-val">{doc.receptor_direccion or ""}</span>
      </div>
      <div class="r-field">
        <span class="r-label">FECHA EMISIÓN:</span>
        <span class="r-val">{fecha_str}</span>
      </div>
      <div class="r-field">
        <span class="r-label">CONDICIÓN PAGO:</span>
        <span class="r-val">{cond_pago}</span>
      </div>
    </div>
  </div>
  <table class="items-table">
    <thead><tr>
      <th class="num">N°</th><th>Codigo</th><th>Descripcion</th>
      <th class="right">Cant.</th><th class="right">Precio Unit.</th>
      <th class="right">%Desc.</th><th class="right">Valor</th>
    </tr></thead>
    <tbody>{items_html}</tbody>
  </table>
  <div class="totales-wrap"><div class="totales-box">{totales_html}</div></div>
  <div class="timbre-section">
    <div class="timbre-left">
      <div class="timbre-title">Timbre Electrónico SII</div>
      <div class="timbre-sii">Verifique documento en: www.sii.cl</div>
    </div>
    <div class="timbre-right">
      {tipo_label}<br/>N° {folio_str}<br/>
      Emisión: {fecha_str}<br/>RUT: {empresa.rut}
    </div>
  </div>
  <div class="footer">Generado con YeparDTE · by YeparSolutions · yepardte.yeparsolutions.com</div>
</div></body></html>"""


def generar_pdf_documento(doc, empresa) -> bytes:
    """
    Genera el PDF del DTE con weasyprint usando el mismo HTML que el frontend.
    Incluye logo si la empresa lo tiene guardado en la BD.
    """
    # Obtener logo desde la BD si existe
    logo_base64 = None
    logo_ancho  = 70
    if empresa.logo:
        mime = "image/png"
        if empresa.logo[:2] == b"\xff\xd8":
            mime = "image/jpeg"
        elif b"<svg" in empresa.logo[:200]:
            mime = "image/svg+xml"
        elif empresa.logo[:4] == b"RIFF":
            mime = "image/webp"
        logo_base64 = f"data:{mime};base64,{base64.b64encode(empresa.logo).decode()}"
        logo_ancho  = getattr(empresa, "logo_ancho", 70) or 70

    html = _html_carta_dte(doc, empresa, logo_base64, logo_ancho)

    try:
        from weasyprint import HTML as WeasyprintHTML
        return WeasyprintHTML(string=html).write_pdf()
    except ImportError:
        raise RuntimeError("weasyprint no instalado. Agrega 'weasyprint' a requirements.txt")
    except Exception as e:
        raise RuntimeError(f"Error generando PDF con weasyprint: {e}")


# ── Templates HTML de email ───────────────────────────────────────────────────

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
