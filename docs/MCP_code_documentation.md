# Proyecto ESP32  documentación del código


## Visión general del servidor MCP

Este servidor MCP (Model Context Protocol) actúa como puente entre LM Studio y un sistema físico compuesto por una cámara USB y un ESP32. Expone herramientas que permiten capturar imágenes, analizarlas con un modelo de visión local y controlar actuadores (LED y puerta) conectados al ESP32.

### Tecnologías utilizadas:

- FastMCP: Framework para crear servidores MCP.

- OpenCV (cv2): Captura y procesamiento de imágenes.

- pyserial: Comunicación con el ESP32.

- requests: Comunicación con LM Studio.

### Librerías importadas

Inicializa el sistema. Configura la comunicación serial, define los pines del LED y del sensor ultrasónico, configura el servo y realiza una primera medición de distancia.

```python
from fastmcp import FastMCP                 # Framework MCP
import cv2                                  # Captura y procesamiento de imágenes
import base64                               # Codificación de imágenes a base64
import requests                             # Comunicación HTTP con LM Studio
import time                                 # Pausas y timeouts
from fastmcp.utilities.types import Image   # Tipo Imagen para MCP
import serial                               # Comunicación con ESP32
import json                                 # Procesamiento de respuestas JSON
import re                                   # Extracción de JSON con regex

```
### Variables globales y configuración
| Variable | Tipo | Valor | Propósito |
|----------|------|-------|------------|
| `app` | FastMCP | `FastMCP(name="Vision System with ESP32 Control")` | Instancia principal del servidor MCP |
| `LM_STUDIO_URL` | str | `"http://127.0.0.1:1234/v1/chat/completions"` | Endpoint del servidor local de LM Studio |
| `MODEL_NAME` | str | `"mistralai/ministral-3-3b"` | Modelo de visión utilizado para detectar personas |
| `requests_session` | Session | `requests.Session()` | Sesión HTTP persistente (mejora rendimiento) |
| `last_image_base64` | str/None | `None` | Almacena la última imagen capturada en base64 |
| `camera_index` | int/None | `None` | Índice de la cámara USB detectada |
| `ESP32_SERIAL_PORT` | str | `"COM4"` | Puerto serial del ESP32 (cambiar según sistema) |
| `ESP32_BAUD_RATE` | int | `115200` | Velocidad de comunicación con el ESP32 |
| `esp32_serial` | Serial/None | `None` | Objeto de conexión serial (se llena al conectar) |

```python
app = FastMCP(name="Vision System with ESP32 Control")

LM_STUDIO_URL = "http://127.0.0.1:1234/v1/chat/completions"
MODEL_NAME = "mistralai/ministral-3-3b"

requests_session = requests.Session()

last_image_base64 = None
camera_index = None
ESP32_SERIAL_PORT = "COM4"  
ESP32_BAUD_RATE = 115200
esp32_serial = None
```
### `conectar_esp32()`

Conecta al ESP32 por serial. Reutiliza la conexión si ya existe.

- **Si ya hay conexión abierta:**  retorna `True`
- **Si no hay conexión:**  intenta abrir el puerto
- **Si falla:** imprime error y retorna `False`

```python
def conectar_esp32():
    global esp32_serial
    
    if esp32_serial is not None and esp32_serial.is_open:
        return True
    
    try:
        esp32_serial = serial.Serial(ESP32_SERIAL_PORT, ESP32_BAUD_RATE, timeout=2)
        time.sleep(2)
        esp32_serial.reset_input_buffer()
        print("ESP32 conectado correctamente")
        return True
    except Exception as e:
        print(f"ESP32 no conectado: {e}")
        esp32_serial = None
        return False
```
### `enviar_comando_esp32(comando, esperar_respuesta=True)`

Envía un comando al ESP32 y devuelve la respuesta.

- **Paso 1:** Llama a `conectar_esp32()`. Si falla → retorna `{"ok": False, "error": "ESP32 no conectado"}`

- **Paso 2:** Limpia el buffer de entrada con `reset_input_buffer()`

- **Paso 3:** Envía el comando seguido de salto de línea (`\n`)

- **Paso 4:** Si `esperar_respuesta` es `False` : retorna `{"ok": True, "respuesta": "Comando enviado"}`

- **Paso 5:** Si espera respuesta el bucle `while` de 2 segundos leyendo datos
- Si hay datos (`in_waiting > 0`): lee línea y la guarda
- Si no hay: espera 0.05 segundos y sigue

- **Paso 6:** Retorna `{"ok": True, "respuesta": "lo que llegó"}` (o `"Sin respuesta"`)

- **Si hay excepción:** retorna `{"ok": False, "error": str(e)}`

```python
def enviar_comando_esp32(comando: str, esperar_respuesta: bool = True) -> dict:
    """
    Envía un comando al ESP32 y devuelve la respuesta
    """
    if not conectar_esp32():
        return {"ok": False, "error": "ESP32 no conectado"}
    
    try:
        esp32_serial.reset_input_buffer()
        
        esp32_serial.write(f"{comando}\n".encode("utf-8"))
        
        if not esperar_respuesta:
            return {"ok": True, "respuesta": "Comando enviado"}
        
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
```
### `find_external_camera(max_cameras=5)`

Detecta automáticamente las cámaras USB conectadas y selecciona la de mayor resolución.

- **Paso 1:** Crea una lista vacía `available_cameras` para guardar cámaras encontradas
- **Paso 2:** Bucle `for` desde índice 1 hasta `max_cameras-1`

    - Intenta abrir la cámara `i` con `cv2.VideoCapture(i, cv2.CAP_DSHOW)`  
    - Si se abre (`cap.isOpened()`): intenta leer un frame
    - Si la lectura funciona (`ret` es `True`):  obtiene alto y ancho, calcula resolución, imprime datos y guarda `(índice, resolución)` en la lista
    - Libera la cámara con `cap.release()`

- **Paso 3:** Si la lista está vacía: imprime error y retorna `None`
- **Paso 4:** Ordena la lista por resolución de mayor a menor (`reverse=True`)
- **Paso 5:** Selecciona el índice de la primera cámara (la de mayor resolución)
- **Paso 6:** Retorna el índice seleccionado

```python
def find_external_camera(max_cameras=5):
    available_cameras = []

    print(" Scanning cameras...")

    for i in range(1, max_cameras):
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
        print("No cameras found")
        return None

    available_cameras.sort(key=lambda x: x[1], reverse=True)

    selected_index = available_cameras[0][0]
    print(f" Selected camera index: {selected_index}")

    return selected_index
```
### `capture_image()`

Captura una imagen desde la cámara USB, la redimensiona, la codifica en base64 y la retorna como objeto imagen.

- **Paso 1:** Verifica `camera_index`. Si es `None` llama a `find_external_camera()`
- **Paso 2:** Si `camera_index` sigue siendo `None` retorna `None`
- **Paso 3:** Abre la cámara con `cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)`
- **Paso 4:** Si no se pudo abrir imprime error y retorna `None`
- **Paso 5:** Configura el ancho a 1280 y alto a 720 con `cap.set()`
- **Paso 6:** Lee un frame con `cap.read()`
- **Paso 7:** Libera la cámara con `cap.release()`
- **Paso 8:** Si no se pudo leer el frame imprime error y retorna `None`
- **Paso 9:** Escala la imagen al 50% usando `cv2.resize()` con interpolación `INTER_AREA`
- **Paso 10:** Codifica la imagen escalada como JPEG con calidad 70%
- **Paso 11:** Convierte el buffer a base64 con `base64.b64encode()` y lo guarda en `last_image_base64`
- **Paso 12:** Imprime el tamaño de la imagen en base64
- **Paso 13:** Crea un objeto `Image` con el buffer y formato `"jpeg"`, retorna `to_image_content()`

```python
def capture_image():
    global last_image_base64, camera_index

    if camera_index is None:
        camera_index = find_external_camera()

    if camera_index is None:
        return None

    cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)

    if not cap.isOpened():
        print("Failed to open camera")
        return None

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    ret, frame = cap.read()
    cap.release()

    if not ret:
        print("Failed to capture frame")
        return None

    escala = 0.5 
    imagen_escalada = cv2.resize(frame, None, fx=escala, fy=escala, interpolation=cv2.INTER_AREA)

    _, buffer = cv2.imencode(".jpg", imagen_escalada, [int(cv2.IMWRITE_JPEG_QUALITY), 70])

    last_image_base64 = base64.b64encode(buffer).decode("utf-8")

    print(f" Image captured (size: {len(last_image_base64)} base64 chars)")

    image_obj = Image(data=buffer, format="jpeg")
    return image_obj.to_image_content()
```
### `check_lmstudio()`

Verifica si el servidor local de LM Studio está disponible y respondiendo.

- **Paso 1:** Intenta hacer una petición GET a `http://127.0.0.1:1234/v1/models` con timeout de 3 segundos usando `requests_session`
- **Paso 2:** Si la petición es exitosa retorna `True` si el código de estado es 200
- **Paso 3:** Si ocurre cualquier excepción (conexión rechazada, timeout, error de red) retorna `False`

```python
def check_lmstudio():
    try:
        response = requests_session.get(
            "http://127.0.0.1:1234/v1/models",
            timeout=3
        )
        return response.status_code == 200
    except:
        return False
```
### `capture_webcam()`

Tool de MCP que captura una imagen de la webcam externa y la retorna.

- **Paso 1:** Imprime `"Ejecutando capture_webcam..."` para logging
- **Paso 2:** Llama a `capture_image()` para obtener el contenido de la imagen
- **Paso 3:** Si `image_content` es `None` retorna `{"error": "Camera not available"}`
- **Paso 4:** Si la captura fue exitosa retorna `image_content`

```python
@app.tool
def capture_webcam():
    """Captura imagen de la webcam externa"""
    print("Ejecutando capture_webcam...")

    image_content = capture_image()

    if image_content is None:
        return {"error": "Camera not available"}

    return image_content
```
### `analyze_scene()`

Analiza la escena con LM Studio y controla ESP32 según detección de personas.

**Parte 1 - Configuración y validación inicial:**

- **Paso 1:** Declara `global last_image_base64`
- **Paso 2:** Imprime `"Ejecutando analyze_scene..."` para logging
- **Paso 3:** Si `last_image_base64` es `None` retorna `{"error": "No image captured yet"}`
- **Paso 4:** Si `check_lmstudio()` es `False` retorna error indicando que LM Studio no está corriendo
- **Paso 5:** Construye el `payload` con:
  - `model`: `MODEL_NAME`
  - `messages`: prompt de usuario con instrucciones para detectar personas
  - `max_tokens`: 300
- **Paso 6:** Configura `retries = 3`

```python
@app.tool
def analyze_scene():
    """Analiza la escena con LM Studio y controla ESP32 según detección de personas"""
    global last_image_base64

    print("Ejecutando analyze_scene...")

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
```
**Parte 2 - Bucle de reintentos y procesamiento:**

- **Paso 1:** Bucle `for attempt in range(retries)` (3 intentos)

- **Paso 2:** En cada intento:
  - Imprime `"Attempt {attempt + 1}..."`
  - Envía petición POST a `LM_STUDIO_URL` con timeout 250 segundos
  - Si `status_code != 200` imprime error y continúa
  - Extrae `result = response.json()`
  - Si no hay `"choices"` retorna error
  - Obtiene `content` del mensaje
  - Imprime `"RAW MODEL OUTPUT:"` seguido del contenido
  - Extrae JSON limpio con regex: `re.search(r"\{.*\}", content, re.DOTALL)`
  - Si encuentra JSON parsea con `json.loads()`
  - Obtiene `people_detected = data.get("people_detected", False)`
  - Imprime `"People detected: {people_detected}"`
  - Controla ESP32: si `people_detected` es `True` envía `"ON"`, si no envía `"OFF"`
  - Imprime `"Analysis successful"`
  - Retorna `{"status": "success", "analysis": content, "people_detected": ...}`

- **Paso 3:** Manejo de excepciones:
  - `requests.exceptions.Timeout` imprime `"Timeout... retrying"`
  - `requests.exceptions.ConnectionError` imprime `"Connection error... retrying"`
  - `Exception` retorna error con detalles

- **Paso 4:** Espera 1 segundo entre intentos con `time.sleep(1)`

- **Paso 5:** Si todos los intentos fallan retorna `{"error": "Failed after multiple attempts", "solution": "Check LM Studio or model"}`

```python
    for attempt in range(retries):
        try:
            print(f"Attempt {attempt + 1}...")

            response = requests_session.post(
                LM_STUDIO_URL,
                json=payload,
                timeout=250
            )

            if response.status_code != 200:
                print("HTTP Error:", response.text)
                continue

            result = response.json()

            if "choices" not in result:
                return {
                    "error": "Invalid model response",
                    "raw": result
                }

            content = result["choices"][0]["message"]["content"]

            print("RAW MODEL OUTPUT:")
            print(content)

            try:
                match = re.search(r"\{.*\}", content, re.DOTALL)

                if match:
                    json_str = match.group(0)
                    data = json.loads(json_str)
                else:
                    data = {}

                people_detected = data.get("people_detected", False)

                print(f" People detected: {people_detected}")

                if people_detected:
                    print("Enviando comando ON al ESP32")
                    enviar_comando_esp32("ON")
                else:
                    print("Enviando comando OFF al ESP32")
                    enviar_comando_esp32("OFF")

            except Exception as e:
                print("Error procesando JSON:", e)

            print("Analysis successful")

            return {
                "status": "success",
                "analysis": content,
                "people_detected": people_detected if 'people_detected' in locals() else None
            }

        except requests.exceptions.Timeout:
            print("Timeout... retrying")

        except requests.exceptions.ConnectionError:
            print("Connection error... retrying")

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
```
### `encender_led_esp32()`

Enciende el LED del ESP32 manualmente.

- Envía comando `"ON"` al ESP32
- Si hay error: retorna `Error: {mensaje}`
- Si funciona: retorna ` LED encendido: {respuesta}`

```python
@app.tool
def encender_led_esp32() -> str:
    """Enciende el LED del ESP32 manualmente"""
    resultado = enviar_comando_esp32("ON")
    if not resultado["ok"]:
        return f"Error: {resultado['error']}"
    return f"LED encendido: {resultado['respuesta']}"
```
### `apagar_led_esp32()`

Apaga el LED del ESP32 manualmente.

- Envía comando `"OFF"` al ESP32
- Si hay error (`resultado["ok"]` es `False`) retorna `Error: {mensaje}`
- Si funciona entonces retorna `LED apagado: {respuesta}`

```python
@app.tool
def apagar_led_esp32() -> str:
    """Apaga el LED del ESP32 manualmente"""
    resultado = enviar_comando_esp32("OFF")
    if not resultado["ok"]:
        return f"Error: {resultado['error']}"
    return f"LED apagado: {resultado['respuesta']}"
```
### `leer_distancia_esp32()`

Lee la distancia del sensor ultrasónico del ESP32.

- Envía comando `"DISTANCIA"` al ESP32
- Si hay error (`resultado["ok"]` es `False`) retorna `Error: {mensaje}`
- Si funciona entonces retorna `Distancia: {respuesta}`

```python
@app.tool
def leer_distancia_esp32() -> str:
    """Lee la distancia del sensor ultrasónico del ESP32"""
    resultado = enviar_comando_esp32("DISTANCIA")
    if not resultado["ok"]:
        return f"Error: {resultado['error']}"
    return f"Distancia: {resultado['respuesta']}"
```
### `abrir_puerta_esp32()`

Abre la puerta controlada por el ESP32.

- Envía comando `"ABRIR"` al ESP32
- Si hay error (`resultado["ok"]` es `False`) retorna `Error: {mensaje}`
- Si funciona retorna `Puerta abierta: {respuesta}`

```python
@app.tool
def abrir_puerta_esp32() -> str:
    """Abre la puerta controlada por el ESP32"""
    resultado = enviar_comando_esp32("ABRIR")
    if not resultado["ok"]:
        return f"Error: {resultado['error']}"
    return f"Puerta abierta: {resultado['respuesta']}"
```
### `cerrar_puerta_esp32()`

Cierra la puerta controlada por el ESP32.

- Envía comando `"CERRAR"` al ESP32
- Si hay error (`resultado["ok"]` es `False`) retorna `Error: {mensaje}`
- Si funciona retorna `Puerta cerrada: {respuesta}`

```python
@app.tool
def cerrar_puerta_esp32() -> str:
    """Cierra la puerta controlada por el ESP32"""
    resultado = enviar_comando_esp32("CERRAR")
    if not resultado["ok"]:
        return f"Error: {resultado['error']}"
    return f"Puerta cerrada: {resultado['respuesta']}"
```
### `estado_esp32()`

Consulta el estado completo del ESP32 (LED, sensor, modo automático).

- Envía comando `"STATUS"` al ESP32
- Si hay error (`resultado["ok"]` es `False`) retorna `Error: {mensaje}`
- Si funciona retorna `Estado ESP32: {respuesta}`

```python
@app.tool
def estado_esp32() -> str:
    """Consulta el estado completo del ESP32 (LED, sensor, modo automático)"""
    resultado = enviar_comando_esp32("STATUS")
    if not resultado["ok"]:
        return f"Error: {resultado['error']}"
    return f"Estado ESP32: {resultado['respuesta']}"
```
### `modo_automatico_esp32(activar: bool, umbral_cm: float = 30.0)`

Activa o desactiva el modo automático del ESP32.

**Parámetros:**
- `activar` (bool): `True` para activar, `False` para desactivar
- `umbral_cm` (float): Distancia en cm para activar LED (solo si `activar=True`). Valor por defecto: `30.0`

**Comportamiento:**

**Si `activar = True`:**
- Envía comando `"UMBRAL {umbral_cm}"` al ESP32 para configurar la distancia umbral
- Si hay error configurando umbral retorna `Error configurando umbral: {error}`
- Envía comando `"AUTO ON"` al ESP32 para activar el modo automático
- Si hay error activando modo auto retorna `Error activando modo auto: {error}`
- Si todo funciona retorna `Modo automático ACTIVADO (LED se enciende si distancia < {umbral_cm}cm)`

**Si `activar = False`:**
- Envía comando `"AUTO OFF"` al ESP32
- Si hay error retorna `Error: {error}`
- Si funciona retorna `Modo automático DESACTIVADO`

```python
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
            return f"Error configurando umbral: {resultado_umbral['error']}"
        
        resultado_auto = enviar_comando_esp32("AUTO ON")
        if not resultado_auto["ok"]:
            return f"Error activando modo auto: {resultado_auto['error']}"
        
        return f"Modo automático ACTIVADO (LED se enciende si distancia < {umbral_cm}cm)"
    else:
        resultado = enviar_comando_esp32("AUTO OFF")
        if not resultado["ok"]:
            return f"Error: {resultado['error']}"
        return f"Modo automático DESACTIVADO"
```
### `robot_status()`

Estado general del sistema.

**Comportamiento:**

- Verifica si el ESP32 está conectado llamando a `conectar_esp32()`
- Verifica si la cámara está disponible (`camera_index is not None`)
- Verifica si LM Studio está disponible llamando a `check_lmstudio()`

**Retorna un diccionario con:**
- `"connection"`: `"ready"` (siempre presente)
- `"esp32_connected"`: `True`/`False` según estado del ESP32
- `"camera_available"`: `True`/`False` según disponibilidad de cámara
- `"lmstudio_available"`: `True`/`False` según disponibilidad de LM Studio
- `"camera_index"`: índice de la cámara o `None`
- `"esp32_port"`: puerto serial configurado para el ESP32

```python
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
```
### `main` - Punto de entrada del sistema

Bloque principal que inicializa y ejecuta el servidor MCP.

**Comportamiento:**

1. **Muestra información del puerto ESP32:**
   - `Puerto ESP32: {ESP32_SERIAL_PORT}`

2. **Lista todas las herramientas disponibles:**
   -  Cámara: `capture_webcam()`, `analyze_scene()`
   -  LED ESP32: `encender_led_esp32()`, `apagar_led_esp32()`
   -  Sensor: `leer_distancia_esp32()`
   -  Puerta: `abrir_puerta_esp32()`, `cerrar_puerta_esp32()`
   -  Modo automático: `modo_automatico_esp32()`
   -  Estado: `estado_esp32()`, `robot_status()`
3. **Ejecuta la aplicación:**
   - `app.run()`

```python
if __name__ == "__main__":
    print("=== SISTEMA DE VISIÓN CON CONTROL ESP32 ===")
    print(f" Puerto ESP32: {ESP32_SERIAL_PORT}")
    print("Herramientas disponibles:")
    print("Cámara: capture_webcam(), analyze_scene()")
    print("LED ESP32: encender_led_esp32(), apagar_led_esp32()")
    print("Sensor: leer_distancia_esp32()")
    print("Puerta: abrir_puerta_esp32(), cerrar_puerta_esp32()")
    print("Modo automático: modo_automatico_esp32()")
    print(" Estado: estado_esp32(), robot_status()")
    print("\nIniciando servidor MCP...")
    app.run()
```