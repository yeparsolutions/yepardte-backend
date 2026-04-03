# app/services/planes.py
# ============================================================
# YeparDTE — Definición de Planes
# Todos los precios incluyen IVA (19%)
# ============================================================

PLANES: dict[str, dict] = {
    "gratuito": {
        "label":             "Gratuito",
        "precio":            0,
        "docsLimit":         20,        # 20 documentos total
        "vendedoresLimit":   0,
        "excedentePorDoc":   0,         # sin cobro de excedentes
        "tiposDoc":          ["Boleta", "Factura"],
        "descripcion":       "Para probar la plataforma",
    },
    "pro": {
        "label":             "Pro",
        "precio":            9990,      # IVA incluido
        "docsLimit":         200,       # 200 folios incluidos
        "vendedoresLimit":   2,         # admin + 2 usuarios
        "excedentePorDoc":   20,        # $20 por folio adicional (IVA incluido)
        "tiposDoc":          ["Boleta", "Factura"],
        "descripcion":       "Ideal para PYMES pequeñas",
    },
    "business": {
        "label":             "Business",
        "precio":            19990,     # IVA incluido
        "docsLimit":         1000,      # 1.000 folios incluidos
        "vendedoresLimit":   999999,    # multiusuario ilimitado
        "excedentePorDoc":   12,        # ~$10-$15 por folio adicional (IVA incluido)
        "tiposDoc":          [
            "Boleta",
            "Factura",
            "Nota de Crédito",
            "Nota de Débito",
            "Guía de Despacho",
        ],
        "descripcion":       "Para empresas en crecimiento",
    },
}
