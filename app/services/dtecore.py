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
            "Content-Type":  "application/json",
        }

    async def emitir_dte(
        self,
        *,
        tipo_code: str,
        exento: bool = False,
        receptor: dict,
        items: list[dict],
        firma_cifrada: bytes,
        firma_password: str,
        caf_cifrado: bytes,
        monto_neto: int = 0,
        monto_exento: int = 0,
        monto_iva: int = 0,
        monto_total: int = 0,
    ) -> dict:
        """
        Envía un DTE a DTECore para que lo firme y lo envíe al SII.

        tipo_code:    "39" boleta afecta | "41" boleta exenta | "33" factura
        exento:       True cuando es Tipo 41
        monto_neto:   Monto neto afecto (0 si es exento)
        monto_exento: Monto exento (>0 si tipo 41)
        monto_iva:    IVA calculado (0 si es exento o boleta afecta sin desglose)
        monto_total:  Total del documento

        Retorna:
          {
            "folio":       int,
            "numero":      str,
            "xml_firmado": str (base64),
            "track_id":    str,
            "estado":      str
          }
        """
        if not self.base_url:
            # ── MOCK hasta tener DTECore documentado ──────────────────────────
            import random
            folio = random.randint(1000, 9999)
            if tipo_code == "41":
                prefijo = "BE"   # Boleta Exenta
            elif tipo_code == "39":
                prefijo = "B"    # Boleta
            else:
                prefijo = "F"    # Factura
            return {
                "folio":       folio,
                "numero":      f"{prefijo}-{folio}",
                "xml_firmado": "",
                "track_id":    f"TK{folio}",
                "estado":      "aceptado",
            }

        # ── Implementación real ────────────────────────────────────────────────
        firma_bytes = decrypt_firma(firma_cifrada)
        caf_bytes   = decrypt_firma(caf_cifrado)

        # Construir ítems con indicador de exención para el SII
        # IndExe: 1 = exento, 0 = afecto
        items_con_ind = []
        for item in items:
            item_dto = dict(item)
            if exento:
                item_dto["IndExe"] = 1   # exento de IVA
            items_con_ind.append(item_dto)

        payload = {
            "tipo_dte":       int(tipo_code),
            "exento":         exento,
            "receptor":       receptor,
            "items":          items_con_ind,
            "firma":          firma_bytes.hex(),       # o base64, según DTECore
            "firma_password": firma_password,
            "caf":            caf_bytes.decode("utf-8"),  # CAF es XML
            # Montos pre-calculados — DTECore puede usarlos directamente
            "monto_neto":     monto_neto,
            "monto_exento":   monto_exento,
            "monto_iva":      monto_iva,
            "monto_total":    monto_total,
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
