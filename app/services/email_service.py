# app/services/email_service.py
# ============================================================
# YeparDTE — Servicio de Email via Resend API
# ============================================================

import os
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


def template_codigo_verificacion(nombre: str, codigo: str) -> str:
    logo_url    = f"{FRONTEND_URL}/logo-1200x520.png"
    isotipo_url = f"{FRONTEND_URL}/IsotipoYS.png"
    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Código de verificación — YeparDTE</title></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:40px 20px;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
        <tr><td style="background:#fff;padding:32px 40px 24px;text-align:center;border-bottom:1px solid #e2e8f0;">
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
    """
    Email con botón de descarga PDF.
    El botón apunta al endpoint pdf-publico del backend que genera
    el PDF con reportlab y lo descarga directamente.
    """
    logo_url  = f"{FRONTEND_URL}/logo-1200x520.png"
    monto_fmt = f"${monto_total:,.0f}".replace(",", ".")

    # Link directo al PDF via endpoint público con token HMAC
    pdf_url = f"{BACKEND_URL}/api/dte/{doc_id}/pdf-publico?token={token}" if doc_id and token else ""

    boton_pdf = f"""
    <div style="text-align:center;margin:28px 0;">
      <a href="{pdf_url}"
         style="display:inline-block;background:#00C77B;color:#ffffff;
                font-size:15px;font-weight:700;text-decoration:none;
                padding:14px 32px;border-radius:10px;letter-spacing:0.3px;">
        ⬇ Descargar documento PDF
      </a>
      <p style="margin:8px 0 0;font-size:11px;color:#94a3b8;">
        El link expira en 30 días
      </p>
    </div>
    """ if pdf_url else """
    <p style="margin:0 0 8px;font-size:14px;color:#475569;">
      Solicita el PDF directamente al emisor.
    </p>
    """

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{tipo_doc} {numero_doc} — {empresa_nombre}</title></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:40px 20px;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0"
             style="background:#fff;border-radius:16px;overflow:hidden;box-shadow:0 4px 24px rgba(0,0,0,0.08);">
        <tr><td style="background:#fff;padding:32px 40px 24px;text-align:center;border-bottom:1px solid #e2e8f0;">
          <img src="{logo_url}" alt="YeparDTE" width="180" height="auto"
               style="display:block;margin:0 auto;" onerror="this.style.display='none'">
        </td></tr>
        <tr><td style="padding:40px 40px 32px;">
          <h2 style="margin:0 0 8px;font-size:20px;font-weight:800;color:#0f172a;">Hola, {receptor_nombre} 👋</h2>
          <p style="margin:0 0 24px;font-size:15px;color:#475569;line-height:1.6;">
            <strong>{empresa_nombre}</strong> (RUT {empresa_rut}) te ha enviado el siguiente
            documento tributario electrónico:
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
