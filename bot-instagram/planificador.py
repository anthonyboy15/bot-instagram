"""
planificador.py
===============
El "cerebro" del sistema: decide QUE publicar y CUANDO durante los proximos
7 dias, usando la API de Google Gemini (nivel gratuito).

Planifica CUATRO formatos de Instagram, cada uno con su proposito:
  * PUBLICACIONES (feed: foto / carrusel / reel) -> ALCANCE a nuevos seguidores.
  * HISTORIAS (efimeras 24h)                     -> CONEXION e interaccion diaria.
  * NOTAS (texto corto <=60 caracteres)          -> curiosidad / cercania.
  * INSTANTANEAS (Instagram Instants, en vivo)   -> INTIMIDAD con tu audiencia.

Este modulo SOLO planifica. No publica nada. Genera un plan, lo guarda en
'plan.json' y lo muestra en consola para que tu lo revises y apruebes antes
de que cualquier otro modulo lo publique.

REGLA DE ORO: el contenido debe ser REALISTA y HONESTO. El planificador tiene
prohibido inventar estadisticas, cifras o testimonios (nada de "+500 personas").

------------------------------------------------------------------
ANTES DE CORRERLO (solo la primera vez):

1. Instala las librerias que usa:
       pip install google-genai python-dotenv tzdata

2. Consigue una clave GRATIS de Gemini en https://aistudio.google.com/apikey
   y agregala a tu archivo .env (la misma carpeta):
       GEMINI_API_KEY=tu_clave

3. Revisa 'config.json' (enfoque, zona horaria, temas y la 'cadencia':
   cuantas publicaciones, historias, notas e instantaneas quieres).

------------------------------------------------------------------
ROADMAP (lo que viene despues):
  * Tendencias reales: alimentar el planificador con lo que esta funcionando
    AHORA (busqueda de Google nativa de Gemini / "grounding").
  * Escritura premium opcional: pulir los captions con Claude Opus 4.8.
------------------------------------------------------------------
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel
from google import genai
from google.genai import types
from google.genai import errors

# zoneinfo viene con Python 3.9+. En Windows necesita el paquete 'tzdata'
# para conocer zonas como "America/Lima"; si falta, usamos un respaldo.
try:
    from zoneinfo import ZoneInfo
except ImportError:  # por si se usa un Python muy viejo
    ZoneInfo = None


# --- Constantes de configuracion del modulo ---
CONFIG_PATH = "config.json"
PLAN_PATH = "plan.json"

# Horas "buenas" por defecto para crecimiento general (formato 24h, hora local).
# Son valores razonables de arranque; mas adelante los reemplazaremos con
# datos reales de tu cuenta (cuando tu audiencia este mas activa).
HORAS_RECOMENDADAS = ["07:30", "12:30", "18:30", "20:30"]


# ==================================================================
# 1) MODELOS DE DATOS
#    Definen la "forma" exacta del plan. Gemini esta obligado a
#    devolver justo esta estructura (salida estructurada), asi que el
#    resultado siempre es JSON valido y predecible.
#    (Importante: NO ponemos valores por defecto en estos campos porque
#     Gemini los rechaza dentro de un response_schema.)
# ==================================================================
class DirectivaImagen(BaseModel):
    """Indica de donde sale la imagen de una publicacion o historia."""
    # GENERAR_IA  -> la imagen se crea con IA usando 'prompt_ia'
    # FOTO_PROPIA -> tu tomas la foto siguiendo 'descripcion_foto'
    tipo: Literal["GENERAR_IA", "FOTO_PROPIA"]
    prompt_ia: str        # prompt de imagen (vacio "" si es FOTO_PROPIA)
    descripcion_foto: str  # que foto tomar (vacio "" si es GENERAR_IA)


class Publicacion(BaseModel):
    """Una publicacion del feed (la que da mas ALCANCE a nuevos seguidores)."""
    fecha: str              # YYYY-MM-DD
    hora: str               # HH:MM (24h, en la zona horaria configurada)
    dia_semana: str         # lunes, martes, ...
    tipo: Literal["foto", "carrusel", "idea_reel"]
    idea: str               # de que trata (con su gancho psicologico)
    caption: str            # el texto del pie, con primera linea que detenga el scroll
    hashtags: list[str]     # lista de hashtags (sin el #, ej: "fitness")
    directiva_imagen: DirectivaImagen


class Historia(BaseModel):
    """Una historia (Story) efimera de 24h: sirve para CONEXION e interaccion."""
    fecha: str
    hora: str
    dia_semana: str
    idea: str                # que mostrar / contar
    texto_en_pantalla: str   # el texto breve que va sobre la historia
    # Sticker interactivo para subir el engagement (clave en historias):
    interaccion: Literal["encuesta", "pregunta", "cuestionario",
                          "cuenta_regresiva", "control_deslizante", "ninguno"]
    directiva_imagen: DirectivaImagen


class Nota(BaseModel):
    """Una nota: texto MUY corto (<=60 caracteres) que aparece arriba en mensajes."""
    fecha: str
    texto: str               # maximo 60 caracteres, tono cercano/curioso


class Instantanea(BaseModel):
    """
    Una instantanea (Instagram Instants): foto espontanea EN VIVO, sin filtros
    ni edicion ni galeria. Por eso SIEMPRE la tomas tu en el momento (nunca IA).
    Sirve para INTIMIDAD con tu audiencia actual.
    """
    fecha: str
    hora: str
    dia_semana: str
    idea: str                # el momento del dia que vale la pena capturar
    descripcion_foto: str    # que captar exactamente, en el instante


class PlanContenido(BaseModel):
    """El plan completo de la semana, separado por formato."""
    publicaciones: list[Publicacion]
    historias: list[Historia]
    notas: list[Nota]
    instantaneas: list[Instantanea]


# ==================================================================
# 2) FUNCIONES
# ==================================================================
def cargar_configuracion(ruta: str = CONFIG_PATH) -> dict:
    """Lee config.json y devuelve la configuracion como diccionario."""
    if not os.path.exists(ruta):
        sys.exit(f"[X] No encontre '{ruta}'. Crea el archivo de configuracion primero.")
    with open(ruta, "r", encoding="utf-8") as f:
        config = json.load(f)
    print(f"[OK] Configuracion cargada desde '{ruta}'.")
    return config


def obtener_zona(nombre_zona: str):
    """Devuelve la zona horaria pedida; si no esta disponible, avisa y usa la del sistema."""
    if ZoneInfo is None:
        return None
    try:
        return ZoneInfo(nombre_zona)
    except Exception:
        print(f"[!] No pude cargar la zona '{nombre_zona}'. "
              f"Instala 'tzdata' (pip install tzdata). Usare la hora del sistema por ahora.")
        return None


def calcular_ventana_fechas(zona) -> list[dict]:
    """
    Construye la lista de los proximos 7 dias (desde hoy) con su fecha y
    nombre de dia, para que Gemini sepa exactamente sobre que fechas planificar.
    """
    dias_es = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado", "domingo"]
    hoy = datetime.now(zona) if zona else datetime.now()
    ventana = []
    for i in range(7):
        dia = hoy + timedelta(days=i)
        ventana.append({
            "fecha": dia.strftime("%Y-%m-%d"),
            "dia_semana": dias_es[dia.weekday()],
        })
    return ventana


def construir_prompt(config: dict, ventana: list[dict]) -> tuple[str, str]:
    """
    Arma las instrucciones (system) y la peticion concreta (user) para el modelo.
    Devuelve la tupla (system, user).
    """
    enfoque = config.get("enfoque", "crecimiento general")
    zona_horaria = config.get("zona_horaria", "America/Lima")
    temas = config.get("temas_semilla", [])

    # Cadencia: cuanto de cada formato. Calculamos los totales para la semana.
    cad = config.get("cadencia", {})
    feed_n = cad.get("publicaciones_feed_por_semana", 4)
    hist_dia = cad.get("historias_por_dia", 2)
    hist_n = hist_dia * 7
    notas_n = cad.get("notas_por_semana", 3)
    inst_n = cad.get("instantaneas_por_semana", 3)

    # En las instrucciones metemos marcos reales de marketing/psicologia y, sobre
    # todo, la REGLA DE HONESTIDAD: nada de inventar datos.
    system = (
        "Eres un estratega experto en crecimiento ORGANICO de Instagram y en "
        "psicologia de redes sociales. Planificas contenido realista, accionable y "
        "honesto, en espanol y con tono natural y cercano.\n\n"
        "REGLAS DE HONESTIDAD (obligatorias):\n"
        "- NUNCA inventes estadisticas, cifras, cantidades de personas, resultados "
        "medibles ni testimonios. Prohibido escribir cosas como '+500 personas lo "
        "usaron' o 'aumente mis ventas 10x'.\n"
        "- Si usas prueba social, que sea cualitativa y honesta (sin numeros "
        "inventados), o mejor evitala.\n"
        "- Habla en primera persona, autentico, sin promesas exageradas.\n\n"
        "Aplica de forma natural (no forzada) marcos probados: gancho/scroll-stopper "
        "en la primera linea, brecha de curiosidad, estructura AIDA, principios de "
        "Cialdini (reciprocidad, autoridad, escasez honesta), vinculo parasocial y "
        "llamadas a la accion de baja friccion.\n\n"
        "ESTRATEGIA: las publicaciones del feed (sobre todo los Reels) son el motor "
        "de ALCANCE a gente nueva; las historias, notas e instantaneas construyen "
        "CONEXION y constancia con quienes ya te siguen. Equilibra ambos."
    )

    ventana_texto = "\n".join(
        f"  - {d['fecha']} ({d['dia_semana']})" for d in ventana
    )
    temas_texto = ", ".join(temas) if temas else "(sin temas semilla; tu propones)"

    user = (
        f"Crea un plan de contenido de Instagram para los proximos 7 dias.\n\n"
        f"ENFOQUE de la cuenta: {enfoque}\n"
        f"ZONA HORARIA: {zona_horaria}\n"
        f"TEMAS o intereses semilla: {temas_texto}\n\n"
        f"DIAS disponibles (reparte el contenido entre ellos):\n{ventana_texto}\n\n"
        f"HORAS recomendadas para el feed: {', '.join(HORAS_RECOMENDADAS)}. "
        f"Las historias e instantaneas pueden ir en otros momentos del dia.\n\n"
        f"CANTIDADES EXACTAS a generar para la semana:\n"
        f"  - publicaciones (feed): {feed_n}  (incluye al menos 2 que sean 'idea_reel').\n"
        f"  - historias: {hist_n} en total (aprox. {hist_dia} por dia, repartidas).\n"
        f"  - notas: {notas_n}.\n"
        f"  - instantaneas: {inst_n}.\n\n"
        "QUE ENTREGAR EN CADA FORMATO:\n\n"
        "PUBLICACIONES (feed; dan alcance):\n"
        "  fecha, hora, dia_semana, tipo ('foto'|'carrusel'|'idea_reel'), idea, "
        "caption (primera linea que detenga el scroll), hashtags (5-12, sin #) y "
        "directiva_imagen:\n"
        "    * 'GENERAR_IA': 'prompt_ia' detallado y 'descripcion_foto'='' .\n"
        "    * 'FOTO_PROPIA': 'descripcion_foto' de que foto tomar y 'prompt_ia'='' .\n\n"
        "HISTORIAS (efimeras 24h; dan conexion):\n"
        "  fecha, hora, dia_semana, idea, texto_en_pantalla (breve) e 'interaccion' "
        "(un sticker: 'encuesta','pregunta','cuestionario','cuenta_regresiva',"
        "'control_deslizante' o 'ninguno') y su directiva_imagen. Varia los stickers.\n\n"
        "NOTAS (texto que aparece arriba en mensajes):\n"
        "  fecha y 'texto' de MAXIMO 60 caracteres, con tono cercano o curioso.\n\n"
        "INSTANTANEAS (Instagram Instants; fotos EN VIVO, sin filtros ni edicion):\n"
        "  fecha, hora, dia_semana, idea y 'descripcion_foto' del momento real a "
        "capturar. Son siempre fotos tuyas del instante (nunca IA).\n\n"
        "Recuerda: contenido realista y SIN datos inventados."
    )
    return system, user


def _pedir_a_gemini(cliente, modelo: str, system: str, user: str):
    """Hace UNA llamada a Gemini pidiendo el plan en nuestra estructura."""
    return cliente.models.generate_content(
        model=modelo,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.9,                  # algo de creatividad en los captions
            response_mime_type="application/json",
            response_schema=PlanContenido,    # obliga a devolver justo nuestra estructura
        ),
    )


def generar_plan_con_gemini(config: dict, system: str, user: str) -> PlanContenido:
    """
    Llama a la API de Google Gemini y devuelve un PlanContenido validado.
    La clave se toma de la variable de entorno GEMINI_API_KEY.

    Es resistente: si el modelo principal esta saturado (error 503) reintenta
    un par de veces y, si sigue fallando, usa el modelo de respaldo estable.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        sys.exit(
            "[X] No encontre GEMINI_API_KEY.\n"
            "    1) Consigue una clave GRATIS en https://aistudio.google.com/apikey\n"
            "    2) Agrega esta linea a tu archivo .env:\n"
            "           GEMINI_API_KEY=tu_clave"
        )

    cliente = genai.Client(api_key=api_key)

    # Intentamos primero el modelo elegido y, si falla, el de respaldo (estable).
    modelo_principal = config.get("modelo", "gemini-2.5-flash")
    modelo_respaldo = config.get("modelo_respaldo", "gemini-2.5-flash")
    modelos = [modelo_principal]
    if modelo_respaldo and modelo_respaldo != modelo_principal:
        modelos.append(modelo_respaldo)

    respuesta = None
    ultimo_error = None
    for modelo in modelos:
        print(f"[..] Pidiendo el plan a Gemini (modelo: {modelo})...")
        for intento in range(1, 4):  # hasta 3 intentos por modelo
            try:
                respuesta = _pedir_a_gemini(cliente, modelo, system, user)
                break
            except errors.ServerError as e:
                # 503/500: el servidor esta saturado. Suele ser temporal -> reintentamos.
                ultimo_error = e
                espera = 5 * intento
                print(f"   [!] El modelo esta saturado (intento {intento}/3). "
                      f"Reintento en {espera}s...")
                time.sleep(espera)
            except errors.ClientError as e:
                # 4xx (p. ej. 429 cuota agotada o modelo no permitido): no insistimos,
                # pasamos directo al modelo de respaldo.
                ultimo_error = e
                print(f"   [!] No pude usar '{modelo}': {e}. Paso al modelo de respaldo...")
                break
        if respuesta is not None:
            print(f"[OK] Respondio el modelo: {modelo}")
            break

    if respuesta is None:
        sys.exit(f"[X] No pude generar el plan tras varios intentos.\n    Ultimo error: {ultimo_error}")

    # Con response_schema + Pydantic, el SDK ya nos da el objeto listo en .parsed.
    plan = respuesta.parsed
    if plan is None:
        # Respaldo: intentamos interpretar el texto JSON a mano.
        try:
            plan = PlanContenido.model_validate_json(respuesta.text)
        except Exception:
            sys.exit("[X] No pude interpretar la respuesta de Gemini como un plan valido.")

    total = (len(plan.publicaciones) + len(plan.historias)
             + len(plan.notas) + len(plan.instantaneas))
    print(f"[OK] Plan recibido: {total} piezas "
          f"({len(plan.publicaciones)} publicaciones, {len(plan.historias)} historias, "
          f"{len(plan.notas)} notas, {len(plan.instantaneas)} instantaneas).")
    return plan


def guardar_plan(plan: PlanContenido, config: dict, ruta: str = PLAN_PATH) -> None:
    """Guarda el plan en plan.json junto con algo de metadata util."""
    salida = {
        "enfoque": config.get("enfoque"),
        "zona_horaria": config.get("zona_horaria"),
        "modelo": config.get("modelo"),
        "cadencia": config.get("cadencia"),
        "generado_el": datetime.now().isoformat(timespec="seconds"),
        "publicaciones": [p.model_dump() for p in plan.publicaciones],
        "historias": [h.model_dump() for h in plan.historias],
        "notas": [n.model_dump() for n in plan.notas],
        "instantaneas": [i.model_dump() for i in plan.instantaneas],
    }
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)
    print(f"[OK] Plan guardado en '{ruta}'.")


def mostrar_plan(plan: PlanContenido, config: dict) -> None:
    """Imprime el plan de forma legible, por secciones, para que lo revises."""
    print("\n" + "=" * 66)
    print(f"  PLAN DE CONTENIDO  -  enfoque: {config.get('enfoque')}")
    print(f"  Zona horaria: {config.get('zona_horaria')}")
    print("=" * 66)

    # --- PUBLICACIONES ---
    print("\n----- PUBLICACIONES (feed -> alcance) -----")
    for i, p in enumerate(sorted(plan.publicaciones, key=lambda x: (x.fecha, x.hora)), 1):
        print(f"\n#{i}  {p.fecha} ({p.dia_semana})  {p.hora}   [{p.tipo.upper()}]")
        print(f"    Idea: {p.idea}")
        print(f"    Caption: {p.caption}")
        if p.hashtags:
            print(f"    Hashtags: {' '.join('#' + h.lstrip('#') for h in p.hashtags)}")
        d = p.directiva_imagen
        if d.tipo == "GENERAR_IA":
            print(f"    Imagen [GENERAR_IA]: {d.prompt_ia}")
        else:
            print(f"    Imagen [FOTO_PROPIA]: {d.descripcion_foto}")

    # --- HISTORIAS ---
    print("\n----- HISTORIAS (24h -> conexion) -----")
    for i, h in enumerate(sorted(plan.historias, key=lambda x: (x.fecha, x.hora)), 1):
        d = h.directiva_imagen
        origen = d.prompt_ia if d.tipo == "GENERAR_IA" else d.descripcion_foto
        print(f"\n#{i}  {h.fecha} ({h.dia_semana})  {h.hora}   sticker: {h.interaccion}")
        print(f"    Idea: {h.idea}")
        print(f"    En pantalla: {h.texto_en_pantalla}")
        print(f"    Imagen [{d.tipo}]: {origen}")

    # --- NOTAS ---
    print("\n----- NOTAS (texto <=60 car.) -----")
    for i, n in enumerate(sorted(plan.notas, key=lambda x: x.fecha), 1):
        print(f"  #{i}  {n.fecha}: \"{n.texto}\"  ({len(n.texto)} car.)")

    # --- INSTANTANEAS ---
    print("\n----- INSTANTANEAS (Instants en vivo -> intimidad) -----")
    for i, ins in enumerate(sorted(plan.instantaneas, key=lambda x: (x.fecha, x.hora)), 1):
        print(f"  #{i}  {ins.fecha} ({ins.dia_semana})  {ins.hora}")
        print(f"      Idea: {ins.idea}")
        print(f"      Captar: {ins.descripcion_foto}")

    print("\n" + "=" * 66)
    print("  Revisa el plan. Cuando lo apruebes, otro modulo lo publicara.")
    print("=" * 66 + "\n")


def main() -> None:
    """Flujo completo: configuracion -> fechas -> Gemini -> guardar -> mostrar."""
    # En Windows la consola suele usar otra codificacion y rompe las tildes/ñ al
    # imprimir. Forzamos UTF-8 en la salida para que se vea correctamente.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    load_dotenv()  # carga las variables del archivo .env (incluida GEMINI_API_KEY)

    config = cargar_configuracion()
    zona = obtener_zona(config.get("zona_horaria", "America/Lima"))
    ventana = calcular_ventana_fechas(zona)
    system, user = construir_prompt(config, ventana)
    plan = generar_plan_con_gemini(config, system, user)
    guardar_plan(plan, config)
    mostrar_plan(plan, config)


if __name__ == "__main__":
    main()
