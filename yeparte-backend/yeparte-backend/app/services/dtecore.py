# app/services/dtecore.py
#
# Adaptador para YeparDTECore
# ─────────────────────────────────────────────────────────────
# Cuando tengas los endpoints de DTECore listos, solo modifica
# este archivo. El resto del sistema no cambia.
#
import httpx
from app.core.config import get_settings
from app.core.security import decrypt_firma

settings = get_settings()


class DTECoreClient:
    """Cliente HTTP para YeparDTECore."""

    def __init__(self):
        self.base_url = settings.DTECORE_URL
        self.api_key  = settings.DTECORE_API_KEY

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def emitir_dte(
        self,
        *,
        tipo_code: str,
        receptor: dict,
        items: list[dict],
        firma_cifrada: bytes,
        firma_password: str,
        caf_cifrado: bytes,
    ) -> dict:
        """
        Envía un DTE a DTECore para que lo firme y lo envíe al SII.

        Retorna:
          {
            "folio": int,
            "numero": str,
            "xml_firmado": str (base64),
            "track_id": str,
            "estado": str
          }

        TODO: Implementar cuando DTECore esté documentado.
        Por ahora retorna un mock para que el frontend funcione.
        """
        if not self.base_url:
            # ── MOCK hasta tener DTECore documentado ──────────
            import random
            es_boleta = tipo_code == "39"
            folio = random.randint(1000, 9999)
            return {
                "folio": folio,
                "numero": f"{'B' if es_boleta else 'F'}-{folio}",
                "xml_firmado": "",
                "track_id": f"TK{folio}",
                "estado": "aceptado",
            }

        # ── Implementación real ────────────────────────────────
        firma_bytes  = decrypt_firma(firma_cifrada)
        caf_bytes    = decrypt_firma(caf_cifrado)

        # Ajustar payload según la API real de DTECore cuando esté lista
        payload = {
            "tipo_dte": int(tipo_code),
            "receptor": receptor,
            "items": items,
            "firma": firma_bytes.hex(),           # o base64, según DTECore
            "firma_password": firma_password,
            "caf": caf_bytes.decode("utf-8"),     # CAF es XML
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self.base_url}/api/dte/emitir",
                json=payload,
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()

    async def estado_dte(self, track_id: str) -> dict:
        """
        Consulta el estado de un DTE en el SII via DTECore.
        TODO: Implementar cuando DTECore esté documentado.
        """
        if not self.base_url:
            return {"track_id": track_id, "estado": "aceptado"}

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{self.base_url}/api/dte/estado/{track_id}",
                headers=self._headers(),
            )
            resp.raise_for_status()
            return resp.json()


# Instancia global
dtecore = DTECoreClient()
