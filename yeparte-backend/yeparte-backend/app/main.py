# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.database import engine, Base
from app.routers import auth, empresa, usuarios, dte, config

settings = get_settings()

app = FastAPI(
    title="YeparDTE API",
    version="1.0.0",
    description="Backend de YeparDTE — Facturación electrónica para Chile",
)

# ── CORS ──────────────────────────────────────────────────────
origins = [
    settings.FRONTEND_URL,
    "http://localhost:3000",
    "http://localhost:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(empresa.router)
app.include_router(usuarios.router)
app.include_router(dte.router)
app.include_router(config.router)


# ── Health ────────────────────────────────────────────────────
@app.get("/api/health")
async def health():
    return {"ok": True, "service": "YeparDTE API"}


# ── Crear tablas al iniciar (dev) ─────────────────────────────
# En producción usa Alembic en lugar de esto
@app.on_event("startup")
async def startup():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
