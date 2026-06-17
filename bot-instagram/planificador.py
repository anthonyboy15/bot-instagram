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

NOVEDAD: antes de planificar, INVESTIGA TENDENCIAS reales con la busqueda de
Google de Gemini (grounding) y las usa como base. Funciona en dos pasos porque
Gemini no permite mezclar busqueda web + salida estructurada en una sola llamada:
  1) Llamada CON busqueda de Google -> resumen de tendencias (texto + fuentes).
  2) Llamada CON salida estructurada -> el plan, alimentado por esas tendencias.

Este modulo SOLO planifica. No publica nada. Guarda el plan en 'plan.json' y lo
muestra en consola para que tu lo revises y apruebes.

REGLA DE ORO: contenido REALISTA y HONESTO. Prohibido inventar estadisticas,
cifras o testimonios.

------------------------------------------------------------------
ANTES DE CORRERLO (solo la primera vez):

1. Instala las librerias:
       pip install google-genai python-dotenv tzdata
2. Clave GRATIS de Gemini en https://aistudio.google.com/apikey -> .env:
       GEMINI_API_KEY=tu_clave
3. Revisa 'config.json' (enfoque, zona horaria, temas, 'cadencia' y
   'usar_tendencias').

NOTA sobre tendencias: la busqueda de Google (grounding) tiene su propia cuota
gratuita. Para uso semanal alcanza de sobra. Si quieres apagarla, pon
"usar_tendencias": false en config.json.
------------------------------------------------------------------
ROADMAP: escritura premium opcional con Claude Opus 4.8; horas reales de la
cuenta; modulo publicador que lea plan.json.
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
# Mas adelante las reemplazaremos con datos reales de actividad de tu cuenta.
HORAS_RECOMENDADAS = ["07:30", "12:30", "18:30", "20:30"]


# ==================================================================
# 1) MODELOS DE DATOS  (la "forma" exacta del plan; Gemini debe respetarla)
#    OJO: sin valores por defecto, porque Gemini los rechaza en el schema.
# ==================================================================
class DirectivaImagen(BaseModel):
    """Indica de donde sale la imagen de una publicacion o historia."""
    tipo: Literal["GENERAR_IA", "FOTO_PROPIA"]
    prompt_ia: str         # prompt de imagen (vacio "" si es FOTO_PROPIA)
    descripcion_foto: str  # que foto tomar (vacio "" si es GENERAR_IA)


class Musica(BaseModel):
    """Sugerencia de musica. OJO: se agrega en la app de IG; el API no la pone."""
    titulo: str       # nombre de la cancion sugerida ("" si ninguna)
    artista: str      # interprete ("" si ninguna)
    momento: str      # que parte usar (ej: "el coro, ~seg 30")
    por_que: str      # por que encaja con el contenido / la tendencia


class Sticker(BaseModel):
    """Sticker interactivo de historia. OJO: se agrega en la app de IG; el API no lo pone."""
    tipo: Literal["encuesta", "pregunta", "cuestionario",
                  "cuenta_regresiva", "control_deslizante", "ninguno"]
    texto: str            # la pregunta o encabezado ("" si tipo es 'ninguno')
    opciones: list[str]   # opciones para encuesta/cuestionario (vacio si no aplica)
    emoji: str            # emoji para 'control_deslizante' (vacio si no aplica)


class Publicacion(BaseModel):
    """Una publicacion del feed (la que da mas ALCANCE a nuevos seguidores)."""
    fecha: str
    hora: str
    dia_semana: str
    tipo: Literal["foto", "carrusel", "idea_reel"]
    idea: str
    caption: str
    hashtags: list[str]
    ubicacion: str                # lugar sugerido y editable ("" si ninguno)
    musica: Musica                # sugerencia de musica
    directiva_imagen: DirectivaImagen


class Historia(BaseModel):
    """Una historia (Story) efimera de 24h: sirve para CONEXION e interaccion."""
    fecha: str
    hora: str
    dia_semana: str
    idea: str
    texto_en_pantalla: str
    sticker: Sticker              # sticker interactivo sugerido
    musica: Musica                # sugerencia de musica
    directiva_imagen: DirectivaImagen


class Nota(BaseModel):
    """Una nota: texto MUY corto (<=60 caracteres) que aparece arriba en mensajes."""
    fecha: str
    texto: str


class Instantanea(BaseModel):
    """Instagram Instants: foto espontanea EN VIVO, sin filtros ni edicion (siempre tuya)."""
    fecha: str
    hora: str
    dia_semana: str
    idea: str
    descripcion_foto: str


class PlanContenido(BaseModel):
    """El plan completo de la semana, separado por formato."""
    publicaciones: list[Publicacion]
    historias: list[Historia]
    notas: list[Nota]
    instantaneas: list[Instantanea]


# ==================================================================
# 2) UTILIDADES DE CONFIGURACION Y FECHAS
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
    """Devuelve la zona horaria pedida; si no esta disponible, usa la del sistema."""
    if ZoneInfo is None:
        return None
    try:
        return ZoneInfo(nombre_zona)
    except Exception:
        print(f"[!] No pude cargar la zona '{nombre_zona}'. "
              f"Instala 'tzdata' (pip install tzdata). Usare la hora del sistema.")
        return None


def calcular_ventana_fechas(zona) -> list[dict]:
    """Lista de los proximos 7 dias (desde hoy) con fecha y nombre de dia."""
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


# ==================================================================
# 3) LLAMADAS A GEMINI  (con reintentos y modelo de respaldo)
# ==================================================================
def crear_cliente() -> genai.Client:
    """Crea el cliente de Gemini leyendo GEMINI_API_KEY del entorno (.env)."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        sys.exit(
            "[X] No encontre GEMINI_API_KEY.\n"
            "    1) Consigue una clave GRATIS en https://aistudio.google.com/apikey\n"
            "    2) Agrega esta linea a tu archivo .env:\n"
            "           GEMINI_API_KEY=tu_clave"
        )
    return genai.Client(api_key=api_key)


def _modelos_a_intentar(config: dict) -> list[str]:
    """Lista [modelo principal, modelo de respaldo] sin duplicados."""
    principal = config.get("modelo", "gemini-2.5-flash")
    respaldo = config.get("modelo_respaldo", "gemini-2.5-flash")
    modelos = [principal]
    if respaldo and respaldo != principal:
        modelos.append(respaldo)
    return modelos


def _llamar_con_resiliencia(modelos, hacer_llamada, descripcion="la respuesta",
                            obligatorio=True):
    """
    Intenta cada modelo con reintentos ante saturacion (503) y pasa al
    siguiente ante errores de cliente (4xx). 'hacer_llamada(modelo)' hace la
    llamada concreta. Si 'obligatorio' es False, devuelve None en vez de abortar.
    """
    respuesta = None
    ultimo_error = None
    for modelo in modelos:
        print(f"[..] Pidiendo {descripcion} a Gemini (modelo: {modelo})...")
        for intento in range(1, 4):  # hasta 3 intentos por modelo
            try:
                respuesta = hacer_llamada(modelo)
                break
            except errors.ServerError as e:
                ultimo_error = e
                espera = 5 * intento
                print(f"   [!] El modelo esta saturado (intento {intento}/3). "
                      f"Reintento en {espera}s...")
                time.sleep(espera)
            except errors.ClientError as e:
                ultimo_error = e
                print(f"   [!] No pude usar '{modelo}': {e}. Paso al modelo de respaldo...")
                break
        if respuesta is not None:
            print(f"[OK] Respondio el modelo: {modelo}")
            return respuesta

    if obligatorio:
        sys.exit(f"[X] No pude obtener {descripcion} tras varios intentos.\n    Ultimo error: {ultimo_error}")
    print(f"[!] No pude obtener {descripcion}. Continuo sin eso. (Ultimo error: {ultimo_error})")
    return None


def investigar_tendencias(cliente: genai.Client, config: dict) -> tuple[str, list[str]]:
    """
    PASO 1: usa la busqueda de Google (grounding) para resumir tendencias
    ACTUALES de Instagram relevantes al enfoque. Devuelve (resumen, fuentes).
    Si falla, devuelve ("", []) para que el plan se genere igual.
    """
    enfoque = config.get("enfoque", "crecimiento general")
    zona = config.get("zona_horaria", "America/Lima")
    temas = ", ".join(config.get("temas_semilla", [])) or "(generales)"

    prompt = (
        f"Investiga en internet las TENDENCIAS ACTUALES de Instagram (de las ultimas "
        f"2-3 semanas) utiles para una cuenta con enfoque '{enfoque}', dirigida a "
        f"audiencia de habla hispana (zona horaria {zona}). Resume de forma concreta "
        f"y accionable:\n"
        f"- Formatos que estan funcionando ahora (estilos de Reels, carruseles, etc.).\n"
        f"- Temas o angulos en alza relacionados con: {temas}.\n"
        f"- Audios, retos o formatos de Reel populares en este momento (si aplica).\n"
        f"- Hashtags relevantes y vigentes.\n"
        f"- Cambios recientes del algoritmo que afecten el alcance.\n\n"
        f"Se honesto: si algo no esta claro o no lo encuentras, dilo. No inventes datos."
    )

    grounding = types.Tool(google_search=types.GoogleSearch())
    respuesta = _llamar_con_resiliencia(
        _modelos_a_intentar(config),
        lambda m: cliente.models.generate_content(
            model=m,
            contents=prompt,
            config=types.GenerateContentConfig(tools=[grounding], temperature=0.4),
        ),
        descripcion="las tendencias",
        obligatorio=False,
    )
    if respuesta is None:
        return "", []

    # Capturamos las fuentes web que uso, para transparencia.
    fuentes = []
    try:
        meta = respuesta.candidates[0].grounding_metadata
        if meta and meta.grounding_chunks:
            for ch in meta.grounding_chunks:
                if ch.web and ch.web.uri:
                    fuentes.append(ch.web.title or ch.web.uri)
    except Exception:
        pass

    return (respuesta.text or "").strip(), fuentes


def construir_prompt(config: dict, ventana: list[dict], tendencias: str = "") -> tuple[str, str]:
    """Arma (system, user) para la generacion estructurada del plan."""
    enfoque = config.get("enfoque", "crecimiento general")
    zona_horaria = config.get("zona_horaria", "America/Lima")
    temas = config.get("temas_semilla", [])

    cad = config.get("cadencia", {})
    feed_n = cad.get("publicaciones_feed_por_semana", 4)
    hist_dia = cad.get("historias_por_dia", 2)
    hist_n = hist_dia * 7
    notas_n = cad.get("notas_por_semana", 3)
    inst_n = cad.get("instantaneas_por_semana", 3)

    system = (
        "Eres un estratega experto en crecimiento ORGANICO de Instagram y en "
        "psicologia de redes sociales. Planificas contenido realista, accionable y "
        "honesto, en espanol y con tono natural y cercano.\n\n"
        "REGLAS DE HONESTIDAD (obligatorias):\n"
        "- NUNCA inventes estadisticas, cifras, cantidades de personas, resultados "
        "medibles ni testimonios (nada de '+500 personas lo usaron').\n"
        "- Si usas prueba social, que sea cualitativa y honesta, o evitala.\n"
        "- Habla en primera persona, autentico, sin promesas exageradas.\n\n"
        "Si te entregan TENDENCIAS ACTUALES, usalas como base real para las ideas "
        "(adaptalas al enfoque; no las copies literalmente).\n\n"
        "Aplica de forma natural marcos probados: gancho/scroll-stopper, brecha de "
        "curiosidad, AIDA, principios de Cialdini, vinculo parasocial y CTA de baja "
        "friccion.\n\n"
        "ESTRATEGIA: el feed (sobre todo Reels) da ALCANCE a gente nueva; historias, "
        "notas e instantaneas construyen CONEXION y constancia. Equilibra ambos."
    )

    ventana_texto = "\n".join(f"  - {d['fecha']} ({d['dia_semana']})" for d in ventana)
    temas_texto = ", ".join(temas) if temas else "(sin temas semilla; tu propones)"

    # Bloque de tendencias (solo si las investigamos con exito).
    if tendencias.strip():
        bloque_tendencias = (
            "\nTENDENCIAS ACTUALES (investigadas hoy en internet; usalas como base):\n"
            f"\"\"\"\n{tendencias.strip()}\n\"\"\"\n"
        )
    else:
        bloque_tendencias = "\n(No hay tendencias frescas disponibles; usa tu mejor criterio.)\n"

    user = (
        f"Crea un plan de contenido de Instagram para los proximos 7 dias.\n\n"
        f"ENFOQUE de la cuenta: {enfoque}\n"
        f"ZONA HORARIA: {zona_horaria}\n"
        f"TEMAS o intereses semilla: {temas_texto}\n"
        f"{bloque_tendencias}\n"
        f"DIAS disponibles (reparte el contenido entre ellos):\n{ventana_texto}\n\n"
        f"HORAS recomendadas para el feed: {', '.join(HORAS_RECOMENDADAS)}. "
        f"Historias e instantaneas pueden ir en otros momentos.\n\n"
        f"CANTIDADES EXACTAS para la semana:\n"
        f"  - publicaciones (feed): {feed_n}  (incluye al menos 2 'idea_reel').\n"
        f"  - historias: {hist_n} (aprox. {hist_dia} por dia, repartidas).\n"
        f"  - notas: {notas_n}.\n"
        f"  - instantaneas: {inst_n}.\n\n"
        "QUE ENTREGAR EN CADA FORMATO:\n\n"
        "PUBLICACIONES (feed; dan alcance): fecha, hora, dia_semana, tipo "
        "('foto'|'carrusel'|'idea_reel'), idea, caption (1a linea que detenga el "
        "scroll), hashtags (5-12, sin #), 'ubicacion' (lugar plausible y editable, "
        "p.ej. una zona/ciudad), 'musica' {titulo, artista, momento (que parte usar, "
        "ej. 'el coro ~seg 30'), por_que (encaje con contenido/tendencia)} y "
        "directiva_imagen:\n"
        "    * 'GENERAR_IA': 'prompt_ia' detallado y 'descripcion_foto'='' .\n"
        "    * 'FOTO_PROPIA': 'descripcion_foto' de que foto tomar y 'prompt_ia'='' .\n\n"
        "HISTORIAS (24h; dan conexion): fecha, hora, dia_semana, idea, "
        "texto_en_pantalla (breve), 'musica' (igual que arriba) y 'sticker' "
        "{tipo: 'encuesta'|'pregunta'|'cuestionario'|'cuenta_regresiva'|"
        "'control_deslizante'|'ninguno'; texto: la pregunta o encabezado; opciones: "
        "lista (2 para encuesta, 2-4 para cuestionario, vacia en los demas); emoji: "
        "solo para 'control_deslizante' (vacio en los demas)} y su directiva_imagen. "
        "Varia los stickers entre historias.\n\n"
        "NOTAS: fecha y 'texto' de MAXIMO 60 caracteres, cercano o curioso.\n\n"
        "INSTANTANEAS (Instagram Instants; fotos EN VIVO, sin filtros ni edicion): "
        "fecha, hora, dia_semana, idea y 'descripcion_foto' del momento real a "
        "capturar. Siempre fotos tuyas del instante (nunca IA).\n\n"
        "Recuerda: contenido realista y SIN datos inventados. La musica y la ubicacion "
        "son SUGERENCIAS editables; no afirmes que una cancion es 'la #1' si no lo sabes."
    )
    return system, user


def _pedir_plan(cliente, modelo: str, system: str, user: str):
    """Una llamada con salida estructurada (sin herramientas) para obtener el plan."""
    return cliente.models.generate_content(
        model=modelo,
        contents=user,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.9,
            response_mime_type="application/json",
            response_schema=PlanContenido,
        ),
    )


def generar_plan_con_gemini(cliente: genai.Client, config: dict,
                            system: str, user: str) -> PlanContenido:
    """PASO 2: genera el plan estructurado (con reintentos y respaldo)."""
    respuesta = _llamar_con_resiliencia(
        _modelos_a_intentar(config),
        lambda m: _pedir_plan(cliente, m, system, user),
        descripcion="el plan",
        obligatorio=True,
    )

    plan = respuesta.parsed
    if plan is None:
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


# ==================================================================
# 4) GUARDAR Y MOSTRAR
# ==================================================================
def guardar_plan(plan: PlanContenido, config: dict, tendencias: str = "",
                 fuentes: list[str] | None = None, ruta: str = PLAN_PATH) -> None:
    """Guarda el plan en plan.json con metadata (incluidas las tendencias usadas)."""
    salida = {
        "enfoque": config.get("enfoque"),
        "zona_horaria": config.get("zona_horaria"),
        "modelo": config.get("modelo"),
        "cadencia": config.get("cadencia"),
        "generado_el": datetime.now().isoformat(timespec="seconds"),
        "tendencias_usadas": tendencias,
        "fuentes_tendencias": fuentes or [],
        "publicaciones": [p.model_dump() for p in plan.publicaciones],
        "historias": [h.model_dump() for h in plan.historias],
        "notas": [n.model_dump() for n in plan.notas],
        "instantaneas": [i.model_dump() for i in plan.instantaneas],
    }
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)
    print(f"[OK] Plan guardado en '{ruta}'.")


def mostrar_plan(plan: PlanContenido, config: dict,
                 tendencias: str = "", fuentes: list[str] | None = None) -> None:
    """Imprime el plan de forma legible, por secciones."""
    print("\n" + "=" * 66)
    print(f"  PLAN DE CONTENIDO  -  enfoque: {config.get('enfoque')}")
    print(f"  Zona horaria: {config.get('zona_horaria')}")
    print("=" * 66)

    if tendencias.strip():
        print("\n----- TENDENCIAS USADAS (resumen) -----")
        resumen = tendencias.strip()
        if len(resumen) > 900:
            resumen = resumen[:900] + " [...]"
        print(resumen)
        if fuentes:
            print(f"\n  Fuentes ({len(fuentes)}): " + "; ".join(fuentes[:6]))

    print("\n----- PUBLICACIONES (feed -> alcance) -----")
    for i, p in enumerate(sorted(plan.publicaciones, key=lambda x: (x.fecha, x.hora)), 1):
        print(f"\n#{i}  {p.fecha} ({p.dia_semana})  {p.hora}   [{p.tipo.upper()}]")
        print(f"    Idea: {p.idea}")
        print(f"    Caption: {p.caption}")
        if p.hashtags:
            print(f"    Hashtags: {' '.join('#' + h.lstrip('#') for h in p.hashtags)}")
        if p.ubicacion:
            print(f"    Ubicacion [auto]: {p.ubicacion}")
        if p.musica.titulo:
            print(f"    Musica [en IG]: {p.musica.titulo} - {p.musica.artista} ({p.musica.momento})")
        d = p.directiva_imagen
        origen = d.prompt_ia if d.tipo == "GENERAR_IA" else d.descripcion_foto
        print(f"    Imagen [{d.tipo}]: {origen}")

    print("\n----- HISTORIAS (24h -> conexion) -----")
    for i, h in enumerate(sorted(plan.historias, key=lambda x: (x.fecha, x.hora)), 1):
        d = h.directiva_imagen
        origen = d.prompt_ia if d.tipo == "GENERAR_IA" else d.descripcion_foto
        print(f"\n#{i}  {h.fecha} ({h.dia_semana})  {h.hora}   sticker: {h.sticker.tipo}")
        print(f"    Idea: {h.idea}")
        print(f"    En pantalla: {h.texto_en_pantalla}")
        if h.sticker.tipo != "ninguno":
            extra = " ".join(filter(None, [h.sticker.texto, " / ".join(h.sticker.opciones), h.sticker.emoji]))
            print(f"    Sticker [en IG]: {h.sticker.tipo} -> {extra}")
        if h.musica.titulo:
            print(f"    Musica [en IG]: {h.musica.titulo} - {h.musica.artista} ({h.musica.momento})")
        print(f"    Imagen [{d.tipo}]: {origen}")

    print("\n----- NOTAS (texto <=60 car.) -----")
    for i, n in enumerate(sorted(plan.notas, key=lambda x: x.fecha), 1):
        print(f"  #{i}  {n.fecha}: \"{n.texto}\"  ({len(n.texto)} car.)")

    print("\n----- INSTANTANEAS (Instants en vivo -> intimidad) -----")
    for i, ins in enumerate(sorted(plan.instantaneas, key=lambda x: (x.fecha, x.hora)), 1):
        print(f"  #{i}  {ins.fecha} ({ins.dia_semana})  {ins.hora}")
        print(f"      Idea: {ins.idea}")
        print(f"      Captar: {ins.descripcion_foto}")

    print("\n" + "=" * 66)
    print("  Revisa el plan. Cuando lo apruebes, otro modulo lo publicara.")
    print("=" * 66 + "\n")


# ==================================================================
# 5) FLUJO PRINCIPAL
# ==================================================================
def main() -> None:
    # En Windows la consola suele romper tildes/ñ al imprimir -> forzamos UTF-8.
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    load_dotenv()  # carga el .env (incluida GEMINI_API_KEY)

    config = cargar_configuracion()
    cliente = crear_cliente()
    zona = obtener_zona(config.get("zona_horaria", "America/Lima"))
    ventana = calcular_ventana_fechas(zona)

    # PASO 1: tendencias reales (opcional, segun config).
    tendencias, fuentes = "", []
    if config.get("usar_tendencias", True):
        print("[..] Investigando tendencias actuales con la busqueda de Google...")
        tendencias, fuentes = investigar_tendencias(cliente, config)
        if tendencias:
            print(f"[OK] Tendencias incorporadas ({len(fuentes)} fuentes).")

    # PASO 2: generar el plan estructurado, alimentado por las tendencias.
    system, user = construir_prompt(config, ventana, tendencias)
    plan = generar_plan_con_gemini(cliente, config, system, user)

    guardar_plan(plan, config, tendencias, fuentes)
    mostrar_plan(plan, config, tendencias, fuentes)


if __name__ == "__main__":
    main()
