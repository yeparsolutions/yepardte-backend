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

# ── Startup ───────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    print("=== STARTUP v5 - migración columnas nuevas ===")

    async with engine.begin() as conn:
        # Crear tablas nuevas que no existan
        await conn.run_sync(Base.metadata.create_all)

        # Migración inline: agregar columnas nuevas si no existen
        # (create_all no altera tablas existentes, hay que hacerlo manual)
        migraciones = [
            # Documento: monto_exento
            """
            DO $$ BEGIN
                ALTER TABLE documentos ADD COLUMN monto_exento BIGINT DEFAULT 0;
            EXCEPTION WHEN duplicate_column THEN NULL;
            END $$;
            """,
            # Documento: condicion_pago
            """
            DO $$ BEGIN
                ALTER TABLE documentos ADD COLUMN condicion_pago VARCHAR(50) DEFAULT 'Contado';
            EXCEPTION WHEN duplicate_column THEN NULL;
            END $$;
            """,
            # Empresa: caf_boleta_exenta
            """
            DO $$ BEGIN
                ALTER TABLE empresas ADD COLUMN caf_boleta_exenta BYTEA;
            EXCEPTION WHEN duplicate_column THEN NULL;
            END $$;
            """,
        ]

        for sql in migraciones:
            try:
                await conn.execute(__import__('sqlalchemy').text(sql))
                print(f"Migración OK: {sql.strip()[:60]}…")
            except Exception as e:
                print(f"Migración skip: {e}")

    print("=== STARTUP completo ===")
