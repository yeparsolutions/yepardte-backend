# YeparDTE Backend

API REST para YeparDTE — Facturación electrónica para Chile.
Construida con **FastAPI + PostgreSQL + SQLAlchemy async**.

## Arquitectura

```
Frontend (React)
      ↓  VITE_API_URL
YeparDTE Backend  ← este servicio
  - Auth JWT
  - Gestión de empresas y vendedores
  - Almacena firma digital cifrada
  - Almacena CAF cifrado
  - Historial de documentos
      ↓  DTECORE_URL
YeparDTECore
  - Firma XML, timbre, envío al SII
```

## Setup local

```bash
# 1. Clonar e instalar dependencias
pip install -r requirements.txt

# 2. Configurar variables de entorno
cp .env.example .env
# Editar .env con tus valores

# 3. Generar ENCRYPTION_KEY
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 4. Levantar PostgreSQL local (con Docker)
docker run -d --name yeparte-db \
  -e POSTGRES_USER=yeparte \
  -e POSTGRES_PASSWORD=yeparte \
  -e POSTGRES_DB=yeparte \
  -p 5432:5432 postgres:16

# 5. Correr el servidor
uvicorn app.main:app --reload --port 8000
```

La API estará en: http://localhost:8000
Docs interactivos: http://localhost:8000/docs

## Variables de entorno

| Variable | Descripción |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/db` |
| `SECRET_KEY` | String aleatorio largo para JWT |
| `ENCRYPTION_KEY` | Clave Fernet para cifrar firma digital y CAF |
| `DTECORE_URL` | URL de tu servicio YeparDTECore |
| `DTECORE_API_KEY` | API key de DTECore |
| `FRONTEND_URL` | URL del frontend (para CORS) |

## Deploy en Railway

1. Crear nuevo servicio en Railway → conectar este repositorio
2. Agregar servicio PostgreSQL en el mismo proyecto
3. Configurar variables de entorno (ver tabla arriba)
4. Railway usará el `Dockerfile` automáticamente

Variables mínimas para Railway:
```
DATABASE_URL=       # Railway lo provee automáticamente si usas su PostgreSQL
SECRET_KEY=         # genera con: openssl rand -hex 32
ENCRYPTION_KEY=     # genera con el comando Python de arriba
FRONTEND_URL=       # https://yepardte.yeparsolutions.com
```

## Conectar DTECore (cuando esté listo)

Edita solo `app/services/dtecore.py`:
1. Ajusta el payload en `emitir_dte()` según los endpoints reales
2. Ajusta `estado_dte()` si DTECore tiene endpoint de consulta
3. Agrega `DTECORE_URL` y `DTECORE_API_KEY` en las variables de entorno

El resto del sistema no cambia.

## Endpoints principales

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/api/auth/login` | Login admin |
| POST | `/api/auth/vendedor` | Login vendedor por PIN |
| POST | `/api/auth/registro` | Registro nueva empresa |
| GET | `/api/empresa` | Datos de la empresa |
| PUT | `/api/empresa` | Actualizar empresa |
| POST | `/api/empresa/firma` | Subir firma digital (.pfx) |
| POST | `/api/empresa/caf` | Subir CAF (XML) |
| GET | `/api/usuarios/vendedores` | Listar vendedores |
| POST | `/api/usuarios/vendedores` | Crear vendedor |
| DELETE | `/api/usuarios/vendedores/{id}` | Eliminar vendedor |
| POST | `/api/dte/emitir` | Emitir boleta/factura |
| GET | `/api/dte/historial` | Historial de documentos |
| GET | `/api/health` | Estado del servicio |
