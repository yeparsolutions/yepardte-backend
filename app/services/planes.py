# app/services/planes.py

PLANES: dict[str, dict] = {
    "gratuito": {
        "label":           "Gratuito",
        "precio":          0,
        "docsLimit":       20,        # 20 documentos total
        "vendedoresLimit": 0,
        "tiposDoc":        ["Boleta", "Factura"],
    },
    "pro": {
        "label":           "Pro",
        "precio":          9990,
        "docsLimit":       250,       # 250 documentos entre boletas y facturas
        "vendedoresLimit": 2,
        "tiposDoc":        ["Boleta", "Factura"],
    },
    "business": {
        "label":           "Business",
        "precio":          19990,
        "docsLimit":       999999,    # ilimitado
        "vendedoresLimit": 999999,
        "tiposDoc":        ["Boleta", "Factura", "Nota de Crédito", "Nota de Débito", "Guía de Despacho"],
    },
}
