#server1.py
from fastmcp import FastMCP
import cv2
import base64
import requests
import time
from fastmcp.utilities.types import Image

# Comunicación ESP32
import serial
import json
import re

app = FastMCP(name="Vision System with ESP32 Control")

LM_STUDIO_URL = "http://127.0.0.1:1234/v1/chat/completions"
MODEL_NAME = "ministral-3-3b-instruct-2512"  # Nombre exacto para LM Studio 

# API Key de LM Studio — encuéntrala en:
# LM Studio → Developer → Local Server → Server Settings → API Key
# Si no tienes autenticación activada, deja vacío ""
LM_STUDIO_API_KEY = "sk-lm-0AKvlNRV:2SueRl32BR3WNx3Wd4lS"  # <- ej: "lm-studio-xxxxxxxxxxxx"

# sesión persistente con Authorization header en TODAS las peticiones
requests_session = requests.Session()
if LM_STUDIO_API_KEY:
    requests_session.headers.update({"Authorization": f"Bearer {LM_STUDIO_API_KEY}"})

# memoria temporal
last_image_base64 = None
camera_index = None

# Configuración ESP32 (reemplazando Arduino)
ESP32_SERIAL_PORT = "COM3"  #  Usa tú puerto del ESP32
ESP32_BAUD_RATE = 115200
esp32_serial = None

def conectar_esp32():
    """Conecta al ESP32 por serial si no está conectado"""
    global esp32_serial
    
    if esp32_serial is not None and esp32_serial.is_open:
        return True
    
    try:
        esp32_serial = serial.Serial(ESP32_SERIAL_PORT, ESP32_BAUD_RATE, timeout=5)
        time.sleep(2)  # Esperar a que el ESP32 se estabilice
        esp32_serial.reset_input_buffer()
        print("✅ ESP32 conectado correctamente")
        return True
    except Exception as e:
        print(f"⚠️ ESP32 no conectado: {e}")
        esp32_serial = None
        return False

def enviar_comando_esp32(comando: str, esperar_respuesta: bool = True) -> dict:
    """
    Envía un comando al ESP32 y devuelve la respuesta
    """
    if not conectar_esp32():
        return {"ok": False, "error": "ESP32 no conectado"}
    
    try:
        # Limpiar buffer antes de enviar
        esp32_serial.reset_input_buffer()
        
        # Enviar comando
        esp32_serial.write(f"{comando}\n".encode("utf-8"))
        
        if not esperar_respuesta:
            return {"ok": True, "respuesta": "Comando enviado"}
        
        # Esperar respuesta (timeout 2 segundos)
        respuesta = ""
        start_time = time.time()
        while time.time() - start_time < 2:
            if esp32_serial.in_waiting > 0:
                line = esp32_serial.readline().decode("utf-8", errors="replace").strip()
                if line:
                    respuesta = line
                    break
            time.sleep(0.05)
        
        return {"ok": True, "respuesta": respuesta if respuesta else "Sin respuesta"}
    
    except Exception as e:
        return {"ok": False, "error": str(e)}

def find_external_camera(max_cameras=0):
    available_cameras = []

    print("🔍 Scanning cameras...")

    for i in range(0, max_cameras):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)

        if cap.isOpened():
            ret, frame = cap.read()

            if ret:
                h, w = frame.shape[:2]
                resolution = w * h
                print(f"Camera {i} detected - Resolution: {w}x{h}")
                available_cameras.append((i, resolution))

            cap.release()

    if not available_cameras:
        print("❌ No cameras found")
        return None

    available_cameras.sort(key=lambda x: x[1], reverse=True)

    selected_index = available_cameras[0][0]
    print(f"✅ Selected camera index: {selected_index}")

    return selected_index

def capture_image():
    global last_image_base64, camera_index

    # Intentar índices 0, 1, 2 si falla
    indices_a_probar = [camera_index] if camera_index is not None else [0, 1, 2]

    for idx in indices_a_probar:
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            continue

        # Calentar la cámara con varios frames (evita frame negro)
        for _ in range(5):
            cap.read()

        ret, frame = cap.read()
        cap.release()

        if ret and frame is not None:
            camera_index = idx
            escala = 0.5
            imagen_escalada = cv2.resize(frame, None, fx=escala, fy=escala,
                                         interpolation=cv2.INTER_AREA)
            _, buffer = cv2.imencode(".jpg", imagen_escalada,
                                     [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            last_image_base64 = base64.b64encode(buffer).decode("utf-8")
            print(f"📸 Imagen capturada desde cámara {idx} ({len(last_image_base64)} chars)")
            image_obj = Image(data=buffer, format="jpeg")
            return image_obj.to_image_content()

    print("❌ No se pudo capturar imagen de ninguna cámara")
    return None

def check_lmstudio():
    try:
        response = requests_session.get(
            "http://127.0.0.1:1234/v1/models",
            timeout=3
        )
        return response.status_code == 200
    except:
        return False

# ============ HERRAMIENTAS DE CÁMARA Y VISIÓN ============

@app.tool
def capture_webcam():
    """Captura imagen de la webcam externa"""
    print("📷 Ejecutando capture_webcam...")

    image_content = capture_image()

    if image_content is None:
        return {"error": "Camera not available"}

    return image_content

@app.tool
def analyze_scene():
    """Analiza la escena con LM Studio y controla ESP32 según detección de personas"""
    global last_image_base64

    print("🧠 Ejecutando analyze_scene...")

    if last_image_base64 is None:
        return {"error": "No image captured yet"}

    if not check_lmstudio():
        return {
            "error": "LM Studio server is not running",
            "solution": "Start Local Server in LM Studio"
        }

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": """
                        Detect if there are people in this image.

                        Rules:
                        - Only count real humans
                        - Do not count images/screens/reflections
                        - Be conservative

                        Return STRICT JSON:
                        {
                          "people_detected": true/false,
                          "people_count": number,
                          "objects": [],
                          "description": ""
                        }
                        """
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{last_image_base64}"
                        }
                    }
                ]
            }
        ],
        "max_tokens": 300
    }

    retries = 3

    for attempt in range(retries):
        try:
            print(f"🔁 Attempt {attempt + 1}...")

            response = requests_session.post(
                LM_STUDIO_URL,
                json=payload,
                timeout=250
            )

            if response.status_code != 200:
                print("❌ HTTP Error:", response.text)
                continue

            result = response.json()

            if "choices" not in result:
                return {
                    "error": "Invalid model response",
                    "raw": result
                }

            content = result["choices"][0]["message"]["content"]

            print("🧾 RAW MODEL OUTPUT:")
            print(content)

            # 🔥 EXTRAER JSON LIMPIO
            try:
                match = re.search(r"\{.*\}", content, re.DOTALL)

                if match:
                    json_str = match.group(0)
                    data = json.loads(json_str)
                else:
                    data = {}

                people_detected = data.get("people_detected", False)

                print(f"👥 People detected: {people_detected}")

                # 🔥 Controlar ESP32 según detección
                if people_detected:
                    print("🔦 Enviando comando ON al ESP32")
                    enviar_comando_esp32("ON")
                else:
                    print("🔦 Enviando comando OFF al ESP32")
                    enviar_comando_esp32("OFF")

            except Exception as e:
                print("⚠️ Error procesando JSON:", e)

            print("✅ Analysis successful")

            return {
                "status": "success",
                "analysis": content,
                "people_detected": people_detected if 'people_detected' in locals() else None
            }

        except requests.exceptions.Timeout:
            print("⏱ Timeout... retrying")

        except requests.exceptions.ConnectionError:
            print("🔌 Connection error... retrying")

        except Exception as e:
            return {
                "error": "Unexpected error",
                "details": str(e)
            }

        time.sleep(1)

    return {
        "error": "Failed after multiple attempts",
        "solution": "Check LM Studio or model"
    }

# ============ NUEVAS HERRAMIENTAS PARA ESP32 ============

@app.tool
def encender_led_esp32() -> str:
    """Enciende el LED del ESP32 manualmente"""
    resultado = enviar_comando_esp32("ON")
    if not resultado["ok"]:
        return f"❌ Error: {resultado['error']}"
    return f"✅ LED encendido: {resultado['respuesta']}"

@app.tool
def apagar_led_esp32() -> str:
    """Apaga el LED del ESP32 manualmente"""
    resultado = enviar_comando_esp32("OFF")
    if not resultado["ok"]:
        return f"❌ Error: {resultado['error']}"
    return f"✅ LED apagado: {resultado['respuesta']}"

@app.tool
def leer_distancia_esp32() -> str:
    """Lee la distancia del sensor ultrasónico del ESP32"""
    resultado = enviar_comando_esp32("DISTANCIA")
    if not resultado["ok"]:
        return f"❌ Error: {resultado['error']}"
    return f"📏 Distancia: {resultado['respuesta']}"

@app.tool
def abrir_puerta_esp32() -> str:
    """Abre la puerta controlada por el ESP32"""
    resultado = enviar_comando_esp32("ABRIR")
    if not resultado["ok"]:
        return f"❌ Error: {resultado['error']}"
    return f"🚪 Puerta abierta: {resultado['respuesta']}"

@app.tool
def cerrar_puerta_esp32() -> str:
    """Cierra la puerta controlada por el ESP32"""
    resultado = enviar_comando_esp32("CERRAR")
    if not resultado["ok"]:
        return f"❌ Error: {resultado['error']}"
    return f"🚪 Puerta cerrada: {resultado['respuesta']}"

@app.tool
def estado_esp32() -> str:
    """Consulta el estado completo del ESP32 (LED, sensor, modo automático)"""
    resultado = enviar_comando_esp32("STATUS")
    if not resultado["ok"]:
        return f"❌ Error: {resultado['error']}"
    return f"📊 Estado ESP32: {resultado['respuesta']}"

@app.tool
def modo_automatico_esp32(activar: bool, umbral_cm: float = 30.0) -> str:
    """
    Activa o desactiva el modo automático del ESP32
    
    Args:
        activar: True para activar, False para desactivar
        umbral_cm: Distancia en cm para activar LED (solo si activar=True)
    """
    if activar:
        resultado_umbral = enviar_comando_esp32(f"UMBRAL {umbral_cm}")
        if not resultado_umbral["ok"]:
            return f"❌ Error configurando umbral: {resultado_umbral['error']}"
        
        resultado_auto = enviar_comando_esp32("AUTO ON")
        if not resultado_auto["ok"]:
            return f"❌ Error activando modo auto: {resultado_auto['error']}"
        
        return f"🤖 Modo automático ACTIVADO (LED se enciende si distancia < {umbral_cm}cm)"
    else:
        resultado = enviar_comando_esp32("AUTO OFF")
        if not resultado["ok"]:
            return f"❌ Error: {resultado['error']}"
        return f"🤖 Modo automático DESACTIVADO"

@app.tool
def robot_status():
    """Estado general del sistema"""
    esp32_conectado = conectar_esp32()
    camara_disponible = camera_index is not None
    lmstudio_disponible = check_lmstudio()
    
    return {
        "connection": "ready",
        "esp32_connected": esp32_conectado,
        "camera_available": camara_disponible,
        "lmstudio_available": lmstudio_disponible,
        "camera_index": camera_index,
        "esp32_port": ESP32_SERIAL_PORT
    }

if __name__ == "__main__":
    print("=== SISTEMA DE VISIÓN CON CONTROL ESP32 ===")
    print(f"📡 Puerto ESP32: {ESP32_SERIAL_PORT}")
    print("🔧 Herramientas disponibles:")
    print("   📸 Cámara: capture_webcam(), analyze_scene()")
    print("   💡 LED ESP32: encender_led_esp32(), apagar_led_esp32()")
    print("   📏 Sensor: leer_distancia_esp32()")
    print("   🚪 Puerta: abrir_puerta_esp32(), cerrar_puerta_esp32()")
    print("   🤖 Modo automático: modo_automatico_esp32()")
    print("   📊 Estado: estado_esp32(), robot_status()")
    print("\n🚀 Iniciando servidor MCP...")
    app.run(transport="http", port=8000)  # http → endpoint /mcp compatible con el agente
