# app/routers/pagos.py
import hmac
import hashlib
import json
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
import httpx

from app.core.database import get_db
from app.core.deps import get_current_admin, get_empresa
from app.core.config import get_settings
from app.models.models import Empresa, Usuario, Pago
from app.services.planes import PLANES

settings = get_settings()
router = APIRouter(prefix="/api/pagos", tags=["pagos"])

MP_API = "https://api.mercadopago.com"

# Descripción de planes para MercadoPago — precios con IVA incluido
PLANES_MP = {
    "pro": {
        "label":  "Pro",
        "precio": 9990,
        "reason": "YeparDTE Plan Pro — 200 folios/mes · Hasta 3 usuarios · IVA incluido",
    },
    "business": {
        "label":  "Business",
        "precio": 19990,
        "reason": "YeparDTE Plan Business — 1.000 folios/mes · Multiusuario · IVA incluido",
    },
}


def mp_headers():
    return {
        "Authorization": f"Bearer {settings.MP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


class CrearPagoBody(BaseModel):
    plan: str  # 'pro' | 'business'


# ── Crear preferencia de pago único ───────────────────────────────────────────
@router.post("/crear-preferencia")
async def crear_preferencia(
    body: CrearPagoBody,
    empresa: Empresa = Depends(get_empresa),
    admin: Usuario = Depends(get_current_admin),
):
    plan_info = PLANES_MP.get(body.plan)
    if not plan_info:
        raise HTTPException(400, "Plan inválido")

    payload = {
        "items": [{
            "title":      plan_info["reason"],
            "quantity":   1,
            "unit_price": plan_info["precio"],
            "currency_id": "CLP",
        }],
        "payer": {"email": admin.email},
        "back_urls": {
            "success": f"{settings.FRONTEND_URL}/config?pago=ok&plan={body.plan}",
            "failure": f"{settings.FRONTEND_URL}/config?pago=error",
            "pending": f"{settings.FRONTEND_URL}/config?pago=pendiente",
        },
        "auto_return": "approved",
        "notification_url": f"{settings.BACKEND_URL}/api/pagos/webhook",
        "metadata": {
            "empresa_id": empresa.id,
            "plan":       body.plan,
            "tipo":       "unico",
        },
        "statement_descriptor": "YEPARDTE",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{MP_API}/checkout/preferences",
            json=payload,
            headers=mp_headers(),
        )
        if not resp.is_success:
            raise HTTPException(502, f"Error MP: {resp.text}")
        data = resp.json()

    return {
        "preference_id":      data["id"],
        "init_point":         data["init_point"],
        "sandbox_init_point": data["sandbox_init_point"],
    }


# ── Crear suscripción recurrente mensual ──────────────────────────────────────
@router.post("/crear-suscripcion")
async def crear_suscripcion(
    body: CrearPagoBody,
    empresa: Empresa = Depends(get_empresa),
    admin: Usuario = Depends(get_current_admin),
):
    plan_info = PLANES_MP.get(body.plan)
    if not plan_info:
        raise HTTPException(400, "Plan inválido")

    payload = {
        "reason":      plan_info["reason"],
        "payer_email": admin.email,
        "auto_recurring": {
            "frequency":          1,
            "frequency_type":     "months",
            "transaction_amount": plan_info["precio"],
            "currency_id":        "CLP",
        },
        "back_url":         f"{settings.FRONTEND_URL}/config",
        "notification_url": f"{settings.BACKEND_URL}/api/pagos/webhook",
        "status": "pending",
        "metadata": {
            "empresa_id": empresa.id,
            "plan":       body.plan,
            "tipo":       "suscripcion",
        },
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{MP_API}/preapproval",
            json=payload,
            headers=mp_headers(),
        )
        if not resp.is_success:
            import logging
            logging.error(f"MP suscripcion error {resp.status_code}: {resp.text}")
            raise HTTPException(502, f"Error MP: {resp.text}")
        data = resp.json()

    return {
        "suscripcion_id": data["id"],
        "init_point":     data["init_point"],
    }


# ── Cobro de excedentes ───────────────────────────────────────────────────────
# Analogía: el medidor de luz — al final del mes se cobra lo que consumiste
# de más. Aquí se cobra por folio cuando se supera el límite del plan.

async def cobrar_excedente(empresa: Empresa, admin_email: str, cantidad_docs: int) -> str | None:
    """
    Crea una preferencia de pago en MP para cobrar folios excedentes.
    Retorna el init_point para redirigir al usuario, o None si falla.
    """
    plan_info = PLANES.get(empresa.plan)
    if not plan_info or plan_info["excedentePorDoc"] == 0:
        return None

    monto = plan_info["excedentePorDoc"] * cantidad_docs
    if monto <= 0:
        return None

    payload = {
        "items": [{
            "title":       f"YeparDTE — {cantidad_docs} folio(s) adicional(es) Plan {plan_info['label']} (IVA inc.)",
            "quantity":    1,
            "unit_price":  monto,
            "currency_id": "CLP",
        }],
        "payer": {"email": admin_email},
        "back_urls": {
            "success": f"{settings.FRONTEND_URL}/config?pago=excedente_ok",
            "failure": f"{settings.FRONTEND_URL}/config?pago=excedente_error",
            "pending": f"{settings.FRONTEND_URL}/config?pago=excedente_pendiente",
        },
        "auto_return": "approved",
        "notification_url": f"{settings.BACKEND_URL}/api/pagos/webhook",
        "metadata": {
            "empresa_id":   empresa.id,
            "plan":         empresa.plan,
            "tipo":         "excedente",
            "docs_extras":  cantidad_docs,
        },
        "statement_descriptor": "YEPARDTE",
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{MP_API}/checkout/preferences",
                json=payload,
                headers=mp_headers(),
            )
            if not resp.is_success:
                return None
            return resp.json().get("init_point")
    except Exception:
        return None


# ── Endpoint para cobrar excedentes manualmente ───────────────────────────────
class ExcedenteBody(BaseModel):
    cantidad_docs: int


@router.post("/cobrar-excedente")
async def cobrar_excedente_endpoint(
    body: ExcedenteBody,
    empresa: Empresa = Depends(get_empresa),
    admin: Usuario = Depends(get_current_admin),
):
    """
    Genera un link de pago para cobrar folios excedentes al admin.
    """
    if body.cantidad_docs <= 0:
        raise HTTPException(400, "Cantidad de documentos debe ser mayor a 0")

    plan_info = PLANES.get(empresa.plan)
    if not plan_info or plan_info["excedentePorDoc"] == 0:
        raise HTTPException(400, "El plan actual no admite excedentes")

    init_point = await cobrar_excedente(empresa, admin.email, body.cantidad_docs)
    if not init_point:
        raise HTTPException(502, "No se pudo generar el cobro de excedente")

    monto = plan_info["excedentePorDoc"] * body.cantidad_docs
    return {
        "ok":          True,
        "init_point":  init_point,
        "monto":       monto,
        "por_doc":     plan_info["excedentePorDoc"],
        "cantidad":    body.cantidad_docs,
    }


# ── Webhook de Mercado Pago ───────────────────────────────────────────────────
@router.post("/webhook")
async def webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_signature: Optional[str] = Header(None),
    x_request_id: Optional[str] = Header(None),
):
    body_bytes = await request.body()

    # Verificar firma del webhook
    if settings.MP_WEBHOOK_SECRET and x_signature:
        ts, v1 = "", ""
        for part in x_signature.split(","):
            k, _, v = part.partition("=")
            if k.strip() == "ts": ts = v.strip()
            if k.strip() == "v1": v1 = v.strip()

        manifest = f"id:{x_request_id};request-id:{x_request_id};ts:{ts};"
        expected = hmac.new(
            settings.MP_WEBHOOK_SECRET.encode(),
            manifest.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(expected, v1):
            raise HTTPException(401, "Firma webhook inválida")

    data = json.loads(body_bytes)
    topic       = data.get("type") or data.get("topic", "")
    resource_id = data.get("data", {}).get("id") or data.get("id")

    if not resource_id:
        return {"ok": True}

    # ── Pago único o excedente aprobado ───────────────────────────────────────
    if topic == "payment":
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{MP_API}/v1/payments/{resource_id}",
                headers=mp_headers(),
            )
            if not resp.is_success:
                return {"ok": True}
            pago_mp = resp.json()

        if pago_mp.get("status") == "approved":
            meta       = pago_mp.get("metadata", {})
            empresa_id = meta.get("empresa_id")
            plan       = meta.get("plan")
            tipo       = meta.get("tipo", "unico")

            if empresa_id and plan:
                result  = await db.execute(select(Empresa).where(Empresa.id == empresa_id))
                empresa = result.scalar_one_or_none()
                if empresa:
                    if tipo == "excedente":
                        # Pago de excedente — sumar folios adicionales al contador
                        # Analogía: recargar saldo en una tarjeta prepago
                        docs_extras = int(meta.get("docs_extras", 0))
                        empresa.docs_usados = max(0, empresa.docs_usados - docs_extras)
                    else:
                        # Pago de plan — activar el plan
                        empresa.plan = plan

                    registro = Pago(
                        empresa_id=empresa_id,
                        mp_payment_id=str(resource_id),
                        plan=plan,
                        monto=int(pago_mp.get("transaction_amount", 0)),
                        tipo=tipo,
                        estado="aprobado",
                    )
                    db.add(registro)
                    await db.commit()

    # ── Suscripción aprobada/cancelada ────────────────────────────────────────
    elif topic in ("subscription_preapproval", "preapproval"):
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{MP_API}/preapproval/{resource_id}",
                headers=mp_headers(),
            )
            if not resp.is_success:
                return {"ok": True}
            sub = resp.json()

        estado_sub = sub.get("status")
        meta       = sub.get("metadata", {})
        empresa_id = meta.get("empresa_id")
        plan       = meta.get("plan")

        if empresa_id and plan:
            result  = await db.execute(select(Empresa).where(Empresa.id == empresa_id))
            empresa = result.scalar_one_or_none()
            if empresa:
                if estado_sub == "authorized":
                    empresa.plan = plan
                    empresa.mp_suscripcion_id = str(resource_id)
                elif estado_sub in ("cancelled", "paused"):
                    empresa.plan = "gratuito"
                    empresa.mp_suscripcion_id = None
                await db.commit()

    return {"ok": True}


# ── Estado de suscripción ─────────────────────────────────────────────────────
@router.get("/mi-suscripcion")
async def mi_suscripcion(
    empresa: Empresa = Depends(get_empresa),
    admin: Usuario   = Depends(get_current_admin),
):
    plan_info = PLANES.get(empresa.plan, PLANES["gratuito"])
    docs_restantes = max(0, plan_info["docsLimit"] - empresa.docs_usados)
    docs_excedente = max(0, empresa.docs_usados - plan_info["docsLimit"])

    return {
        "plan":              empresa.plan,
        "mp_suscripcion_id": empresa.mp_suscripcion_id,
        "docs_usados":       empresa.docs_usados,
        "docs_limite":       plan_info["docsLimit"],
        "docs_restantes":    docs_restantes,
        "docs_excedente":    docs_excedente,
        "precio_excedente":  plan_info["excedentePorDoc"],
    }
