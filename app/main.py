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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
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
