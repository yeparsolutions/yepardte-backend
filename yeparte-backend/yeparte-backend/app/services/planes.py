# app/services/planes.py

PLANES: dict[str, dict] = {
    "gratuito": {"label": "Gratuito", "precio": 0,     "docsLimit": 50,       "vendedoresLimit": 0},
    "pro":      {"label": "Pro",      "precio": 9990,  "docsLimit": 500,      "vendedoresLimit": 2},
    "business": {"label": "Business", "precio": 19990, "docsLimit": 999999,   "vendedoresLimit": 999999},
}
