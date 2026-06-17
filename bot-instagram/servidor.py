"""
servidor.py — Fase 1 del panel web (estilo "community manager") del bot.

App web movil-first con estetica de Instagram oscuro. Permite:
  - Iniciar sesion con una contrasena.
  - Generar el plan semanal (reutiliza planificador.py).
  - Ver cada pieza previsualizada como en Instagram (post / historia / reel).
  - Editar los textos y subir fotos desde el celular (camara o galeria).
  - Guardar los cambios.

Fase 1 NO publica nada en Instagram (eso llega en la Fase 3).

COMO EJECUTARLO:
    pip install -r requirements.txt
    # en el .env agrega una contrasena para entrar a la app:
    #     APP_PASSWORD=tu_clave_para_entrar
    uvicorn servidor:app --host 0.0.0.0 --port 8000

Luego abre http://localhost:8000  (o, desde el celular, la URL del tunel).
"""

import os
import json
import time
import secrets
from pathlib import Path

from dotenv import load_dotenv
from fastapi import (FastAPI, Cookie, Depends, HTTPException, Request,
                     Response, UploadFile, File, Form)
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import planificador as plan_mod  # reutilizamos toda la logica del planificador

load_dotenv()

# --- Rutas (siempre relativas a este archivo, no al directorio actual) ---
BASE_DIR = Path(__file__).parent
WEB_DIR = BASE_DIR / "web"
SUBIDAS_DIR = BASE_DIR / "subidas"
CONFIG_PATH = BASE_DIR / "config.json"
PLAN_PATH = BASE_DIR / "plan.json"
WEB_DIR.mkdir(exist_ok=True)
SUBIDAS_DIR.mkdir(exist_ok=True)

# --- Contrasena de acceso a la app (NO es la de Instagram) ---
APP_PASSWORD = os.getenv("APP_PASSWORD")
if not APP_PASSWORD:
    APP_PASSWORD = "instagram"  # solo para pruebas locales
    print("[!] No hay APP_PASSWORD en el .env. Uso 'instagram' por defecto. "
          "Agrega APP_PASSWORD=tu_clave al .env antes de exponer la app a internet.")

SESIONES = set()  # tokens de sesion validos (en memoria; se reinician al reiniciar)

app = FastAPI(title="Panel de contenido")
app.mount("/web", StaticFiles(directory=str(WEB_DIR)), name="web")
app.mount("/subidas", StaticFiles(directory=str(SUBIDAS_DIR)), name="subidas")


# ==================================================================
# Seguridad: sesion por cookie
# ==================================================================
def requiere_sesion(sesion: str | None = Cookie(default=None)):
    """Dependencia que protege los endpoints: exige una sesion valida."""
    if sesion is None or sesion not in SESIONES:
        raise HTTPException(status_code=401, detail="No autorizado")
    return sesion


# ==================================================================
# Utilidades de archivos
# ==================================================================
def _cargar_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _guardar_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _leer_plan() -> dict:
    if not PLAN_PATH.exists():
        return {"vacio": True}
    with open(PLAN_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _perfil_dict() -> dict:
    cfg = _cargar_config()
    foto = SUBIDAS_DIR / "perfil.jpg"
    return {
        "usuario": cfg.get("usuario_instagram", ""),
        "foto_url": f"/subidas/perfil.jpg?t={int(time.time())}" if foto.exists() else None,
    }


# ==================================================================
# Paginas y login
# ==================================================================
@app.get("/")
def inicio():
    return FileResponse(str(WEB_DIR / "index.html"))


@app.post("/api/login")
def login(respuesta: Response, password: str = Form(...)):
    if password != APP_PASSWORD:
        raise HTTPException(status_code=401, detail="Contrasena incorrecta")
    token = secrets.token_urlsafe(24)
    SESIONES.add(token)
    respuesta.set_cookie("sesion", token, httponly=True, samesite="lax",
                         max_age=60 * 60 * 24 * 30)
    return {"ok": True}


@app.post("/api/logout")
def logout(respuesta: Response, sesion: str | None = Cookie(default=None)):
    SESIONES.discard(sesion)
    respuesta.delete_cookie("sesion")
    return {"ok": True}


# ==================================================================
# Perfil (usuario + foto para la previsualizacion)
# ==================================================================
@app.get("/api/perfil")
def get_perfil(_=Depends(requiere_sesion)):
    return _perfil_dict()


@app.post("/api/perfil")
async def set_perfil(_=Depends(requiere_sesion),
                     usuario: str | None = Form(None),
                     foto: UploadFile | None = File(None)):
    if usuario is not None:
        cfg = _cargar_config()
        cfg["usuario_instagram"] = usuario
        _guardar_config(cfg)
    if foto is not None:
        with open(SUBIDAS_DIR / "perfil.jpg", "wb") as f:
            f.write(await foto.read())
    return _perfil_dict()


# ==================================================================
# Plan: leer, generar y guardar
# ==================================================================
@app.get("/api/plan")
def get_plan(_=Depends(requiere_sesion)):
    return _leer_plan()


@app.put("/api/plan")
async def put_plan(request: Request, _=Depends(requiere_sesion)):
    """Guarda el plan completo (con las ediciones hechas en la app)."""
    datos = await request.json()
    with open(PLAN_PATH, "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    return {"ok": True}


@app.post("/api/generar")
def generar(_=Depends(requiere_sesion)):
    """Genera un plan nuevo reutilizando el planificador (llama a Gemini)."""
    try:
        config = plan_mod.cargar_configuracion(str(CONFIG_PATH))
        cliente = plan_mod.crear_cliente()
        zona = plan_mod.obtener_zona(config.get("zona_horaria", "America/Lima"))
        ventana = plan_mod.calcular_ventana_fechas(zona)

        tendencias, fuentes = "", []
        if config.get("usar_tendencias", True):
            tendencias, fuentes = plan_mod.investigar_tendencias(cliente, config)

        system, user = plan_mod.construir_prompt(config, ventana, tendencias)
        plan = plan_mod.generar_plan_con_gemini(cliente, config, system, user)
        plan_mod.guardar_plan(plan, config, tendencias, fuentes, str(PLAN_PATH))
    except SystemExit as e:
        # El planificador usa sys.exit ante errores; aqui lo convertimos en HTTP.
        raise HTTPException(status_code=500, detail=f"No se pudo generar el plan: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error inesperado: {e}")
    return _leer_plan()


# ==================================================================
# Subir una foto para una pieza (publicacion / historia / instantanea)
# ==================================================================
@app.post("/api/subir")
async def subir(_=Depends(requiere_sesion),
                categoria: str = Form(...),
                indice: int = Form(...),
                foto: UploadFile = File(...)):
    ext = os.path.splitext(foto.filename or "")[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        ext = ".jpg"
    nombre = f"{categoria}_{indice}_{int(time.time())}{ext}"
    with open(SUBIDAS_DIR / nombre, "wb") as f:
        f.write(await foto.read())
    return {"url": f"/subidas/{nombre}"}
