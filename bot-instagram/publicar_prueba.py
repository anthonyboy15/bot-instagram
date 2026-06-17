"""
publicar_prueba.py
==================
Tu primer test real: confirma que tu token funciona y publica UNA foto
de prueba en tu cuenta de Instagram usando la API oficial (Instagram Login).

Si este script publica una foto, significa que TODA la cadena funciona
(token + permisos + cuenta) y ya podemos construir el sistema completo.

------------------------------------------------------------------
ANTES DE CORRERLO (solo la primera vez):

1. Instala las dos librerías que usa:
       pip install requests python-dotenv

2. En esta misma carpeta crea un archivo llamado exactamente  .env
   y dentro pega tu token asi (sin comillas, sin espacios):

       ACCESS_TOKEN=aqui_va_tu_token_largo

3. (Opcional) Cambia IMAGE_URL por el enlace publico de la imagen que
   quieras publicar. OJO: tiene que ser un enlace publico a un .JPG.
   Instagram NO acepta archivos de tu PC ni imagenes PNG por esta via.
------------------------------------------------------------------
"""

import os
import sys
import time
import requests
from dotenv import load_dotenv

# --- Configuracion ---
load_dotenv()                          # lee el archivo .env
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")

API = "https://graph.instagram.com"    # los tokens de Instagram Login usan ESTE host
VERSION = "v22.0"

# Imagen de prueba (un JPG publico de ejemplo). Cambiala por la tuya cuando quieras.
IMAGE_URL = "https://images.unsplash.com/photo-1506744038136-46273834b3fb?w=1080&h=1080&fit=crop&fm=jpg&q=80"
CAPTION = "Publicacion de prueba automatizada \U0001F680"


def verificar_cuenta():
    """Paso 1: comprueba que el token sirve y devuelve el ID de la cuenta."""
    print("1) Verificando el token y la cuenta...")
    r = requests.get(
        f"{API}/me",
        params={"fields": "user_id,username,account_type", "access_token": ACCESS_TOKEN},
    )
    data = r.json()
    if "error" in data:
        sys.exit(f"   [X] Error al verificar: {data['error'].get('message')}")
    print(
        f"   [OK] Conectado como @{data.get('username')} "
        f"(tipo: {data.get('account_type')}, id: {data.get('user_id')})"
    )
    return data["user_id"]


def crear_contenedor(ig_id):
    """Paso 2: prepara la imagen para publicar (crea un 'contenedor')."""
    print("2) Creando el contenedor de la imagen...")
    r = requests.post(
        f"{API}/{VERSION}/{ig_id}/media",
        params={"image_url": IMAGE_URL, "caption": CAPTION, "access_token": ACCESS_TOKEN},
    )
    data = r.json()
    if "error" in data:
        sys.exit(f"   [X] Error al crear contenedor: {data['error'].get('message')}")
    print(f"   [OK] Contenedor creado: {data['id']}")
    return data["id"]


def esperar_listo(container_id):
    """Paso 3: espera a que Instagram termine de procesar la imagen."""
    print("3) Esperando a que Instagram procese la imagen...")
    for _ in range(20):
        r = requests.get(
            f"{API}/{VERSION}/{container_id}",
            params={"fields": "status_code", "access_token": ACCESS_TOKEN},
        )
        status = r.json().get("status_code")
        print(f"   estado: {status}")
        if status == "FINISHED":
            return
        if status in ("ERROR", "EXPIRED"):
            sys.exit("   [X] El contenedor falló. Revisa que la imagen sea un JPG público.")
        time.sleep(3)
    sys.exit("   [X] Se agoto el tiempo de espera.")


def publicar(ig_id, container_id):
    """Paso 4: publica el contenedor ya procesado."""
    print("4) Publicando...")
    r = requests.post(
        f"{API}/{VERSION}/{ig_id}/media_publish",
        params={"creation_id": container_id, "access_token": ACCESS_TOKEN},
    )
    data = r.json()
    if "error" in data:
        sys.exit(f"   [X] Error al publicar: {data['error'].get('message')}")
    print(f"   [!] Publicado con éxito. id del post: {data['id']}")


if __name__ == "__main__":
    if not ACCESS_TOKEN:
        sys.exit("No encontre ACCESS_TOKEN. Crea un archivo .env con: ACCESS_TOKEN=tu_token")
    cuenta_id = verificar_cuenta()
    contenedor = crear_contenedor(cuenta_id)
    esperar_listo(contenedor)
    publicar(cuenta_id, contenedor)
