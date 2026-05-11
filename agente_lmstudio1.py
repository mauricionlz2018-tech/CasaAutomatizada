"""
agente_lmstudio.py v4.0
========================
Cambios respecto a v3.0:

  [FIX 5] Se elimina el SDK de lmstudio (lms.llm / model.act) que causaba:
           "dictionary update sequence element #0 has length 1; 2 is required"
           El SDK usa WebSocket internamente y es sensible al formato exacto
           del nombre del modelo. Se reemplaza por un bucle agentico manual
           usando HTTP directo a LM Studio (puerto 1234), igual que server2.py.

  [MEJORA] El agente ahora maneja el ciclo tool-use completo:
           LM Studio devuelve tool_calls → agente ejecuta → devuelve resultados
           → LM Studio razona y continúa hasta terminar el ciclo.

Requisitos:
  - LM Studio corriendo con el modelo cargado y servidor activo (puerto 1234)
  - server2.py corriendo con transport="http" (puerto 8000)
  - pip install httpx

Uso:
  1. python server2.py           (MCP en puerto 8000)
  2. LM Studio → Start Server   (LLM en puerto 1234)
  3. python agente_lmstudio1.py
"""

import time
import json
import httpx

# ── Configuración ──────────────────────────────────────────────────────────────
# 
# Nombre del modelo TAL COMO aparece en LM Studio (pestaña My Models o el
# identificador que muestra el servidor en GET http://localhost:1234/v1/models)
MODEL_NAME    = "ministral-3-3b-instruct-2512"

LM_STUDIO_URL = "http://127.0.0.1:1234"      # LM Studio local server
MCP_URL       = "http://127.0.0.1:8000/mcp"  # FastMCP (transport=http)
LOOP_INTERVAL = 10                            # Segundos entre ciclos
MAX_TOOL_TURNS = 10                           # Máximo de rondas tool-use por ciclo

# API Key de LM Studio (si tienes autenticación activada en el servidor local).
# Encuéntrala en LM Studio → Local Server → pestaña API → campo "API Key".
# Si no tienes autenticación, deja vacío "".
LMS_API_KEY   = "sk-lm-0AKvlNRV:2SueRl32BR3WNx3Wd4lS"   # <- ej: "lm-studio-xxxxxxxxxxxx"

# API Key del servidor MCP (si tu maestro la configuró en FastMCP).
MCP_API_KEY   = ""   # <- ej: "mi-clave-secreta"

# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
Eres un agente de monitoreo autónomo con acceso a sensores, cámara y control de hardware.

Tu tarea en cada ciclo es:
1. Lee la distancia del sensor ultrasónico con leer_distancia_esp32.
2. Si la distancia es menor a 50 cm, captura una imagen con capture_webcam.
3. Analiza la imagen capturada con analyze_scene:
   - Si hay una persona → abre la puerta con abrir_puerta_esp32 y enciende la led con encender_led_esp32,
     espera 4 segundos con esperar_segundos, ciérra la puerta con cerrar_puerta_esp32 y apaga la led con apagar_led_esp32.
   - Si NO hay persona  → no hagas nada con la puerta y tampoco enciendas la led.
4. Reporta brevemente lo que hiciste y por qué.

Reglas:
- Siempre empieza leyendo el sensor.
- Usa las herramientas en orden lógico.
- Si el sensor devuelve error, intenta UNA vez más. Si falla dos veces, termina el ciclo.
- NO pidas confirmación, actúa directamente.
"""

# Definición de herramientas en formato OpenAI/LM Studio tool_calls
TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "leer_distancia_esp32",
            "description": "Lee la distancia del sensor ultrasónico del ESP32 en centímetros.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "capture_webcam",
            "description": "Captura una imagen de la webcam externa y la guarda en memoria para análisis.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_scene",
            "description": "Analiza la última imagen capturada para detectar si hay personas presentes.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_puerta_esp32",
            "description": "Abre la puerta controlada por el ESP32.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cerrar_puerta_esp32",
            "description": "Cierra la puerta controlada por el ESP32.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "encender_led_esp32",
            "description": "Enciende el LED del ESP32.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apagar_led_esp32",
            "description": "Apaga el LED del ESP32.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "esperar_segundos",
            "description": "Espera la cantidad de segundos indicada antes de continuar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "segundos": {
                        "type": "integer",
                        "description": "Número de segundos a esperar.",
                    }
                },
                "required": ["segundos"],
            },
        },
    },
]


# ── Clientes HTTP ──────────────────────────────────────────────────────────────

_http = httpx.Client(timeout=120.0)


def _lms_headers() -> dict:
    h = {"Content-Type": "application/json"}
    if LMS_API_KEY:
        h["Authorization"] = f"Bearer {LMS_API_KEY}"
    return h


def _mcp_headers() -> dict:
    h = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if MCP_API_KEY:
        h["Authorization"] = f"Bearer {MCP_API_KEY}"
    if _mcp_session_id:
        h["mcp-session-id"] = _mcp_session_id
    return h


# ── MCP ───────────────────────────────────────────────────────────────────────

_mcp_session_id  = None
_mcp_initialized = False


def _parse_sse(text: str) -> dict:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            json_str = line[len("data:"):].strip()
            if json_str:
                return json.loads(json_str)
    stripped = text.strip()
    if stripped:
        return json.loads(stripped)
    return {}


def _mcp_request(method: str, params=None, is_notification: bool = False) -> dict:
    global _mcp_session_id

    payload: dict = {
        "jsonrpc": "2.0",
        "method":  method,
        "params":  params if params is not None else {},
    }
    if not is_notification:
        payload["id"] = 1

    resp = _http.post(MCP_URL, json=payload, headers=_mcp_headers())

    sid = resp.headers.get("mcp-session-id")
    if sid:
        _mcp_session_id = sid

    if is_notification or not resp.content.strip():
        return {}

    data = _parse_sse(resp.text)
    if "error" in data:
        code = data["error"].get("code", "?")
        msg  = data["error"].get("message", str(data["error"]))
        raise RuntimeError(f"MCP [{method}] error {code}: {msg}")

    return data.get("result", {})


def _mcp_init():
    global _mcp_initialized
    if _mcp_initialized:
        return
    _mcp_request("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities":    {},
        "clientInfo":      {"name": "agente_lmstudio", "version": "4.0"},
    })
    _mcp_request("notifications/initialized", is_notification=True)
    _mcp_initialized = True
    print(f"✅ Sesión MCP lista  (session: {_mcp_session_id})")


def _call_mcp_tool(name: str, arguments: dict = None) -> str:
    _mcp_init()
    result  = _mcp_request("tools/call", {"name": name, "arguments": arguments or {}})
    content = result.get("content", [])
    parts   = []
    for block in content:
        btype = block.get("type", "")
        if btype == "text":
            parts.append(block["text"])
        elif btype == "image":
            parts.append("[IMAGEN_CAPTURADA]")
        else:
            parts.append(str(block))
    return "\n".join(parts) if parts else "(sin respuesta)"


# ── Dispatcher de herramientas locales ────────────────────────────────────────

def _dispatch_tool(name: str, arguments: dict) -> str:
    """Ejecuta la herramienta solicitada por el modelo y retorna el resultado."""
    if name == "esperar_segundos":
        segundos = int(arguments.get("segundos", 1))
        print(f"   ⏳ Esperando {segundos}s...")
        time.sleep(segundos)
        return f"Espera de {segundos} segundos completada."

    # Todas las demás herramientas van al MCP
    emoji_map = {
        "leer_distancia_esp32": "📏",
        "capture_webcam":       "📸",
        "analyze_scene":        "🧠",
        "abrir_puerta_esp32":   "🚪",
        "cerrar_puerta_esp32":  "🚪",
        "encender_led_esp32":   "💡",
        "apagar_led_esp32":     "💡",
    }
    emoji = emoji_map.get(name, "🔧")
    result = _call_mcp_tool(name, arguments)
    print(f"   {emoji} [{name}]: {result[:100]}")
    return result


# ── Verificar modelo disponible en LM Studio ──────────────────────────────────

def _get_available_model() -> str:
    """
    Consulta GET /v1/models para obtener el identificador exacto del modelo
    cargado en LM Studio. Si MODEL_NAME coincide (parcialmente), lo usa.
    Si no, usa el primero disponible.
    """
    try:
        resp = _http.get(f"{LM_STUDIO_URL}/v1/models", headers=_lms_headers())
        models = resp.json().get("data", [])
        if not models:
            raise RuntimeError("LM Studio no tiene modelos cargados.")

        ids = [m["id"] for m in models]
        print(f"   Modelos disponibles en LM Studio: {ids}")

        # Buscar coincidencia con MODEL_NAME configurado
        for mid in ids:
            if MODEL_NAME.lower() in mid.lower() or mid.lower() in MODEL_NAME.lower():
                print(f"   ✅ Usando modelo: {mid}")
                return mid

        # Si no hay coincidencia, usar el primero disponible
        print(f"   ⚠️  '{MODEL_NAME}' no encontrado. Usando el primero: {ids[0]}")
        return ids[0]

    except Exception as e:
        print(f"   ⚠️  No se pudo consultar modelos: {e}. Usando MODEL_NAME tal cual.")
        return MODEL_NAME


# ── Ciclo agentico ────────────────────────────────────────────────────────────

def run_agent_cycle(model_id: str):
    """
    Bucle agentico manual con tool_calls OpenAI-compatible:
      1. Envía mensaje al modelo con las herramientas disponibles.
      2. Si el modelo responde con tool_calls → ejecuta cada herramienta.
      3. Devuelve los resultados al modelo como mensajes 'tool'.
      4. Repite hasta que el modelo responda sin tool_calls (respuesta final).
    """
    messages = [
        {"role": "system",  "content": SYSTEM_PROMPT},
        {"role": "user",    "content": "Ejecuta tu ciclo de monitoreo ahora."},
    ]

    for turno in range(MAX_TOOL_TURNS):
        payload = {
            "model":        model_id,
            "messages":     messages,
            "tools":        TOOLS_SCHEMA,
            "tool_choice":  "auto",
            "max_tokens":   1024,
            "temperature":  0.1,
        }

        resp = _http.post(
            f"{LM_STUDIO_URL}/v1/chat/completions",
            json=payload,
            headers=_lms_headers(),
        )

        if resp.status_code != 200:
            print(f"   ❌ LM Studio HTTP {resp.status_code}: {resp.text[:200]}")
            break

        data    = resp.json()
        choice  = data["choices"][0]
        message = choice["message"]

        # Añadir respuesta del asistente al historial
        messages.append(message)

        # Mostrar texto del modelo si lo hay
        text = (message.get("content") or "").strip()
        if text:
            print(f"\n🤖 Agente: {text}")

        # ¿El modelo terminó sin tool_calls?
        finish = choice.get("finish_reason", "")
        if finish == "stop" or not message.get("tool_calls"):
            print("\n✅ Ciclo completado")
            break

        # Ejecutar cada tool_call solicitada
        for tc in message.get("tool_calls", []):
            fn_name = tc["function"]["name"]
            try:
                fn_args = json.loads(tc["function"].get("arguments", "{}"))
            except json.JSONDecodeError:
                fn_args = {}

            print(f"\n🔧 Herramienta solicitada: {fn_name}({fn_args})")
            result_str = _dispatch_tool(fn_name, fn_args)

            # Devolver resultado al modelo
            messages.append({
                "role":         "tool",
                "tool_call_id": tc["id"],
                "content":      result_str,
            })
    else:
        print(f"\n⚠️  Se alcanzó el límite de {MAX_TOOL_TURNS} turnos de herramientas.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 52)
    print("   AGENTE AUTÓNOMO - HTTP directo + MCP  v4.0")
    print("=" * 52)
    print(f"📡 MCP:         {MCP_URL}")
    print(f"🧠 LM Studio:   {LM_STUDIO_URL}")
    print(f"🔁 Intervalo:   {LOOP_INTERVAL}s")
    print(f"🔑 LMS API Key: {'configurada' if LMS_API_KEY else 'no configurada'}")
    print(f"🔑 MCP API Key: {'configurada' if MCP_API_KEY else 'no configurada'}\n")

    # Conectar MCP
    try:
        _mcp_init()
    except Exception as e:
        print(f"❌ No se pudo conectar al MCP: {e}")
        return

    # Verificar LM Studio y obtener nombre exacto del modelo
    print("\n🔍 Verificando LM Studio...")
    try:
        model_id = _get_available_model()
    except Exception as e:
        print(f"❌ Error conectando a LM Studio: {e}")
        return

    print(f"\n🚀 Agente iniciado. Ctrl+C para detener.\n")

    ciclo = 1
    while True:
        print(f"\n{'─'*52}\n🔄 Ciclo {ciclo}\n{'─'*52}")
        try:
            run_agent_cycle(model_id)
        except KeyboardInterrupt:
            print("\n🛑 Detenido")
            break
        except Exception as e:
            print(f"⚠️  Error en ciclo {ciclo}: {e}")

        ciclo += 1
        print(f"\n⏳ Próximo ciclo en {LOOP_INTERVAL}s...")
        try:
            time.sleep(LOOP_INTERVAL)
        except KeyboardInterrupt:
            print("\n🛑 Detenido")
            break

    _http.close()


if __name__ == "__main__":
    main()