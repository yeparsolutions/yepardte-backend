# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.database import engine, Base
from app.routers import auth, empresa, usuarios, dte, config, pagos, clientes

settings = get_settings()

app = FastAPI(
    title="YeparDTE API",
    version="1.0.0",
    description="Backend de YeparDTE — Facturación electrónica para Chile",
)

# ── CORS ──────────────────────────────────────────────────────
# Analogía: la lista de invitados en la puerta —
# solo los dominios autorizados pueden hacer peticiones con credenciales.
# allow_origins=["*"] + allow_credentials=True NO es válido en CORS,
# por eso especificamos los dominios exactos.
ALLOWED_ORIGINS = [
    "https://yepardte.yeparsolutions.com",   # frontend producción
    "https://www.yepardte.yeparsolutions.com",
    "http://localhost:5173",                  # Vite dev local
    "http://localhost:3000",                  # alternativa dev
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(empresa.router)
app.include_router(usuarios.router)
app.include_router(dte.router)
app.include_router(config.router)
app.include_router(pagos.router)
app.include_router(clientes.router)

# ── Health ────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"ok": True, "service": "YeparDTE API"}

# ── Crear tablas al iniciar ───────────────────────────────────
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
