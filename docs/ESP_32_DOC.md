# Proyecto ESP32 — Documentación del Circuito y Código


## Explicación del Código


---

### Variables y Librerías

#### Pines:
```
LED: Pin 5 (GPIO 5)
Sensor Ultrasónico:
  TRIG: D2 (GPIO 2)
  ECHO: D4 (GPIO 4)
Servo: Pin 15 (GPIO 15)
```



#### Configuración de pines y librerías:
```cpp
// Incluir librería del servo
#include <ESP32Servo.h>

// ========== CONFIGURACIÓN DE PINES ==========
#define LED_PIN 5       
#define TRIG_PIN 2     // D2 - Pin de trigger del sensor ultrasónico
#define ECHO_PIN 4     // D4 - Pin de echo del sensor ultrasónico

// Instancia del servo
Servo miServo;
int pinServo = 15;

// ========== VARIABLES PARA LED ==========
bool blinkActive = false;
unsigned long previousMillis = 0;
int blinkOnTime = 500;    // Tiempo encendido en ms
int blinkOffTime = 500;   // Tiempo apagado en ms
bool ledState = LOW;
bool manualMode = true;   // true = control manual ON/OFF, false = modo parpadeo

// ========== VARIABLES PARA SENSOR ULTRASÓNICO ==========
unsigned long lastDistanceRead = 0;
const unsigned long distanceReadInterval = 200;  // Leer distancia cada 200ms
float lastDistance = -1;  // Última distancia medida en cm
bool distanceValid = false;

// ========== VARIABLES PARA ACCIONES AUTOMÁTICAS ==========
bool autoMode = false;           // Modo automático basado en distancia
float distanceThreshold = 30.0;  // Umbral en cm para acciones automáticas
bool autoActionEnabled = false;  // Si se ha habilitado acción automática
```

---

### `setup()`

Inicializa el sistema. Configura la comunicación serial, define los pines del LED y del sensor ultrasónico, configura el servo y realiza una primera medición de distancia.

```cpp
void setup() {
  Serial.begin(115200);
  
  // Configurar LED
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  
  // Configurar sensor ultrasónico
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  // Asigna el timer y el canal PWM automáticamente
  miServo.attach(pinServo, 500, 2500);  // Min 500µs, Max 2500µs
  
  Serial.println("=== ESP32 Listo ===");
  Serial.println("Sistema con LED y Sensor Ultrasónico");
  Serial.println("Escribe HELP para ver comandos disponibles");
  Serial.println();
  
  // Medición inicial
  delay(100);
  medirDistancia();
}
```

---

### `loop()`

Se ejecuta continuamente. Lee comandos del usuario, mide la distancia periódicamente, ejecuta acciones automáticas si están activadas y controla el parpadeo del LED.

```cpp
void loop() {
  // 1. Procesar comandos serial
  if (Serial.available() > 0) {
    String comando = Serial.readStringUntil('\n');
    comando.trim();
    procesarComando(comando);
  }
  // 2. Medir distancia periódicamente
  if (millis() - lastDistanceRead >= distanceReadInterval) {
    lastDistanceRead = millis();
    medirDistancia();
    
    // 3. Acciones automáticas basadas en distancia
    if (autoActionEnabled && distanceValid) {
      manejarAccionAutomatica();
    }
  }
  // 4. Manejar parpadeo del LED (si está activo)
  if (blinkActive && !manualMode && !autoMode) {
    unsigned long currentMillis = millis();
    unsigned long interval = ledState ? blinkOnTime : blinkOffTime;
    if (currentMillis - previousMillis >= interval) {
      previousMillis = currentMillis;
      ledState = !ledState;
      digitalWrite(LED_PIN, ledState);
    }
  }
}
```

---

### `medirDistancia()`

Envía un pulso al sensor ultrasónico y mide el tiempo que tarda en regresar el eco para calcular la distancia en centímetros.

```cpp
void medirDistancia() {
  // Asegurar que el pin TRIG esté en LOW
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  
  // Enviar pulso de 10 microsegundos
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  
  // Medir duración del pulso en ECHO
  long duration = pulseIn(ECHO_PIN, HIGH, 30000);  // Timeout 30ms (máx ~5m)
  
  if (duration == 0) {
    // Timeout: no se recibió eco
    distanceValid = false;
    lastDistance = -1;
  } else {
    // Calcular distancia: duración * velocidad del sonido (343 m/s) / 2
    // distancia (cm) = duration (us) * 0.0343 / 2
    lastDistance = duration * 0.0343 / 2;
    distanceValid = true;
    
    // Limitar valores fuera de rango
    if (lastDistance > 400) {
      lastDistance = 400;
    }
  }
}
```

---

### `obtenerDistancia()`

Devuelve la última distancia medida. Si no hay datos válidos, regresa -1.

```cpp
float obtenerDistancia() {
  if (!distanceValid) {
    return -1;
  }
  return lastDistance;
}
```

---

### `encenderLED()`

Enciende el LED en modo manual y desactiva otros modos.

```cpp
void encenderLED() {
  // Desactivar modos automáticos
  autoMode = false;
  blinkActive = false;
  manualMode = true;
  digitalWrite(LED_PIN, HIGH);
  Serial.println("LED encendido manualmente");
}
```

---

### `apagarLED()`

Apaga el LED en modo manual y desactiva otros modos.

```cpp
void apagarLED() {
  // Desactivar modos automáticos
  autoMode = false;
  blinkActive = false;
  manualMode = true;
  digitalWrite(LED_PIN, LOW);
  Serial.println("LED apagado manualmente");
}
```

---

### `iniciarParpadeo()`

Activa el parpadeo del LED con tiempos definidos de encendido y apagado.

```cpp
void iniciarParpadeo(int onTime, int offTime) {
  blinkOnTime = onTime;
  blinkOffTime = offTime;
  blinkActive = true;
  manualMode = false;
  autoMode = false;
  ledState = LOW;
  digitalWrite(LED_PIN, LOW);
  previousMillis = millis();
  Serial.print("Modo parpadeo activado: ON=");
  Serial.print(blinkOnTime);
  Serial.print("ms, OFF=");
  Serial.print(blinkOffTime);
  Serial.println("ms");
}
```

---

### `detenerParpadeo()`

Detiene el parpadeo y regresa al modo manual.

```cpp
void detenerParpadeo() {
  blinkActive = false;
  if (!autoMode) {
    manualMode = true;
    digitalWrite(LED_PIN, LOW);
  }
  Serial.println("Parpadeo detenido");
}
```

---

### `habilitarAutoMode()`

Activa o desactiva el modo automático basado en distancia.

```cpp
void habilitarAutoMode(bool habilitar) {
  autoActionEnabled = habilitar;
  if (habilitar) {
    Serial.print("Modo automático ACTIVADO. LED se encenderá cuando distancia < ");
    Serial.print(distanceThreshold);
    Serial.println(" cm");
    
    // Realizar una acción inmediata basada en la distancia actual
    if (distanceValid) {
      manejarAccionAutomatica();
    }
  } else {
    autoMode = false;
    Serial.println("Modo automático DESACTIVADO");
    // Restaurar control manual
    manualMode = true;
    digitalWrite(LED_PIN, LOW);
  }
}
```

---

### `manejarAccionAutomatica()`

Enciende o apaga el LED dependiendo de si un objeto está dentro del rango definido.

```cpp
void manejarAccionAutomatica() {
  if (lastDistance < distanceThreshold) {
    // Objeto detectado dentro del umbral
    if (!autoMode) {
      autoMode = true;
      manualMode = false;
      blinkActive = false;
      digitalWrite(LED_PIN, HIGH);
      Serial.print("¡Objeto detectado! Distancia: ");
      Serial.print(lastDistance);
      Serial.println(" cm - LED encendido");
    }
  } else {
    // Objeto fuera del umbral
    if (autoMode) {
      autoMode = false;
      manualMode = true;
      blinkActive = false;
      digitalWrite(LED_PIN, LOW);
      Serial.print("Objeto fuera de rango. Distancia: ");
      Serial.print(lastDistance);
      Serial.println(" cm - LED apagado");
    }
  }
}
```

---

### `setDistanceThreshold()`

Permite cambiar el umbral de distancia para el modo automático.

```cpp
void setDistanceThreshold(float umbral) {
  if (umbral > 0 && umbral < 400) {
    distanceThreshold = umbral;
    Serial.print("Umbral de distancia cambiado a: ");
    Serial.print(distanceThreshold);
    Serial.println(" cm");
  } else {
    Serial.println("Umbral inválido. Usa un valor entre 1 y 400 cm");
  }
}
```

---

### `abrirPuerta()`

Mueve el servo a 90 grados simulando la apertura de una puerta.

```cpp
void abrirPuerta(){
  Serial.println("Moviendo a 90°");
  miServo.write(90);
  delay(1000);
}
```

---

### `cerrarPuerta()`

Mueve el servo a 0 grados simulando el cierre de una puerta.

```cpp
void cerrarPuerta(){
  Serial.println("Moviendo a 0°");
  miServo.write(0);
  delay(1000);
}
```

---

## Comandos Disponibles por Serial

### Control del LED
```
ON                          - Enciende el LED
OFF                         - Apaga el LED
BLINK ON                    - Inicia el parpadeo
BLINK OFF                   - Detiene el parpadeo
BLINK SPEED [ms]            - Establece velocidad de parpadeo
BLINK CUSTOM [on] [off]     - Parpadeo personalizado
```

### Sensor Ultrasónico
```
DISTANCIA o DIST            - Muestra la distancia actual
AUTO ON                     - Activa modo automático
AUTO OFF                    - Desactiva modo automático
UMBRAL [cm]                 - Configura umbral (1-400 cm)
```

### Control de Servo
```
ABRIR                       - Abre la puerta (servo a 90°)
CERRAR                      - Cierra la puerta (servo a 0°)
```

### Información
```
STATUS                      - Muestra el estado completo del sistema
HELP                        - Muestra esta lista de comandos
```


---

### `procesarComando()`

Interpreta y ejecuta los comandos recibidos por puerto serial.

```cpp
void procesarComando(String comando) {
  comando.toUpperCase();
  if (comando == "ON") {
    encenderLED();
  }
  else if (comando == "OFF") {
    apagarLED();
  }
  else if (comando == "STATUS") {
    mostrarEstado();
  }
  else if (comando.startsWith("BLINK")) {
    procesarComandoBlink(comando);
  }
  else if (comando == "DISTANCIA" || comando == "DIST") {
    mostrarDistancia();
  }
  else if (comando.startsWith("AUTO")) {
    procesarComandoAuto(comando);
  }
  else if (comando.startsWith("UMBRAL")) {
    procesarComandoUmbral(comando);
  }
  else if (comando == "HELP") {
    mostrarAyuda();
  }
  else if (comando == "CERRAR"){
    cerrarPuerta();
  }
  else if (comando == "ABRIR"){
    abrirPuerta();
  }
  else {
    Serial.println("Comando no reconocido. Escribe HELP para ayuda.");
  }
}
```

---

### `procesarComandoBlink()`

Procesa los subcomandos relacionados con el parpadeo del LED.

```cpp
void procesarComandoBlink(String comando) {
  String params = comando.substring(6);
  params.trim();
  
  if (params == "ON") {
    iniciarParpadeo(blinkOnTime, blinkOffTime);
  }
  else if (params == "OFF") {
    detenerParpadeo();
  }
  else if (params.startsWith("SPEED")) {
    int speed = params.substring(6).toInt();
    if (speed > 0 && speed <= 5000) {
      blinkOnTime = speed;
      blinkOffTime = speed;
      Serial.print("Velocidad cambiada a: ");
      Serial.print(speed);
      Serial.println(" ms");
      
      if (blinkActive && !manualMode && !autoMode) {
        previousMillis = millis();
      }
    } else {
      Serial.println("Velocidad inválida. Usa 1-5000 ms");
    }
  }
  else if (params.startsWith("CUSTOM")) {
    params = params.substring(7);
    params.trim();
    
    int espacio = params.indexOf(' ');
    if (espacio > 0) {
      int onTime = params.substring(0, espacio).toInt();
      int offTime = params.substring(espacio + 1).toInt();
      
      if (onTime > 0 && onTime <= 10000 && offTime > 0 && offTime <= 10000) {
        blinkOnTime = onTime;
        blinkOffTime = offTime;
        Serial.print("Parpadeo personalizado: ON=");
        Serial.print(blinkOnTime);
        Serial.print("ms, OFF=");
        Serial.print(blinkOffTime);
        Serial.println("ms");
        
        if (blinkActive && !manualMode && !autoMode) {
          previousMillis = millis();
        }
      } else {
        Serial.println("Tiempos inválidos. Usa 1-10000 ms");
      }
    } else {
      Serial.println("Formato: BLINK CUSTOM [on_ms] [off_ms]");
    }
  }
  else {
    Serial.println("Subcomandos BLINK: ON, OFF, SPEED, CUSTOM");
  }
}
```

---

### `procesarComandoAuto()`

Procesa los comandos para activar/desactivar el modo automático.

```cpp
void procesarComandoAuto(String comando) {
  String params = comando.substring(5);
  params.trim();
  
  if (params == "ON") {
    habilitarAutoMode(true);
  }
  else if (params == "OFF") {
    habilitarAutoMode(false);
  }
  else {
    Serial.println("Usa: AUTO ON o AUTO OFF");
  }
}
```

---

### `procesarComandoUmbral()`

Procesa los comandos para cambiar el umbral de distancia.

```cpp
void procesarComandoUmbral(String comando) {
  String params = comando.substring(7);
  params.trim();
  
  float umbral = params.toFloat();
  if (umbral > 0 && umbral < 400) {
    setDistanceThreshold(umbral);
  } else {
    Serial.println("Formato: UMBRAL [cm] (1-400)");
  }
}
```

---

### `mostrarEstado()`

Muestra el estado completo del sistema (LED, sensor, modo automático).

```cpp
void mostrarEstado() {
  Serial.println("=== ESTADO DEL SISTEMA ===");
  
  // Estado del LED
  if (autoMode) {
    Serial.println("Modo LED: AUTOMÁTICO (por distancia)");
    Serial.print("  LED actualmente: ");
    Serial.println(digitalRead(LED_PIN) ? "ENCENDIDO" : "APAGADO");
  } else if (blinkActive && !manualMode) {
    Serial.println("Modo LED: PARPADEO");
    Serial.print("  ON: ");
    Serial.print(blinkOnTime);
    Serial.print("ms, OFF: ");
    Serial.print(blinkOffTime);
    Serial.println("ms");
  } else if (manualMode) {
    Serial.print("Modo LED: MANUAL - ");
    Serial.println(digitalRead(LED_PIN) ? "ENCENDIDO" : "APAGADO");
  }
  
  // Estado del sensor
  Serial.println("\n=== SENSOR ULTRASÓNICO ===");
  if (distanceValid) {
    Serial.print("Distancia: ");
    Serial.print(lastDistance);
    Serial.println(" cm");
  } else {
    Serial.println("Distancia: No disponible (objeto fuera de rango o error)");
  }
  
  // Configuración automática
  Serial.println("\n=== CONFIGURACIÓN AUTO ===");
  Serial.print("Modo automático: ");
  Serial.println(autoActionEnabled ? "ACTIVADO" : "DESACTIVADO");
  if (autoActionEnabled) {
    Serial.print("Umbral: ");
    Serial.print(distanceThreshold);
    Serial.println(" cm");
  }
  
  Serial.println("=========================");
}
```

---

### `mostrarDistancia()`

Muestra la distancia actual medida por el sensor ultrasónico.

```cpp
void mostrarDistancia() {
  if (distanceValid) {
    Serial.print("Distancia medida: ");
    Serial.print(lastDistance);
    Serial.println(" cm");
  } else {
    Serial.println("Error: No se pudo medir distancia");
    Serial.println("Verifica conexiones del sensor ultrasónico");
  }
}
```

---

### `mostrarAyuda()`

Muestra el listado completo de comandos disponibles.

```cpp
void mostrarAyuda() {
  Serial.println("\n=== COMANDOS DISPONIBLES ===");
  Serial.println("\n--- Control LED ---");
  Serial.println("ON                    - Enciende LED");
  Serial.println("OFF                   - Apaga LED");
  Serial.println("BLINK ON              - Inicia parpadeo");
  Serial.println("BLINK OFF             - Detiene parpadeo");
  Serial.println("BLINK SPEED [ms]      - Velocidad de parpadeo");
  Serial.println("BLINK CUSTOM [on] [off] - Parpadeo personalizado");
  
  Serial.println("\n--- Sensor Ultrasónico ---");
  Serial.println("DISTANCIA o DIST      - Muestra distancia actual");
  Serial.println("AUTO ON               - Activa modo automático");
  Serial.println("AUTO OFF              - Desactiva modo automático");
  Serial.println("UMBRAL [cm]           - Configura umbral (1-400)");
  
  Serial.println("\n--- Control de Servo ---");
  Serial.println("ABRIR                 - Abre puerta (servo a 90°)");
  Serial.println("CERRAR                - Cierra puerta (servo a 0°)");
  
  Serial.println("\n--- Información ---");
  Serial.println("STATUS                - Muestra estado completo");
  Serial.println("HELP                  - Muestra esta ayuda");
  Serial.println("============================\n");
}
```

Interpreta los comandos escritos por el usuario en el monitor serial. Todos los comandos se convierten a mayúsculas y se procesan en funciones especializadas.

---

## Diagrama del Circuito (Wokwi)

> Simulación en Wokwi: [https://wokwi.com/projects/460879044104559617](https://wokwi.com/projects/460879044104559617)

### Diagrama de Conexiones

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            CIRCUITO COMPLETO                            │
└─────────────────────────────────────────────────────────────────────────┘

                              ╔════════════════╗
                              ║    SERVO MOTOR ║
                              ╠════════════════╣
                              ║ V+ (5V)  ─────┐│
                              ║ GND ─────────┐││
                              ║ PWM (GPIO15) ││
                              ║              ││
                              ╚════════════════╝
                                    ↓
                                   │││
                                   │││
                ┌──────────────────┴┴┴─────────┐
                │                              │
              5V ←────────────────────┐        │
             GND ←────────────────────┼────────┘


         ╔══════════════════════════════════════╗
         ║   PROTOBOARD CONEXIONES              ║
         ╠══════════════════════════════════════╣
         ║                                      ║
         ║  [+] ─────────────────────────────── 5V del ESP32
         ║  [-] ─────────────────────────────── GND del ESP32
         ║  [+] ─────────────────────────────── 5V del Sensor
         ║  [-] ─────────────────────────────── GND del Sensor
         ║                                      ║
         ║           ╔════════════════╗         ║
         ║           ║ HC-SR04 SENSOR ║         ║
         ║           ╠════════════════╣         ║
         └──────────→║ VCC (5V) ──────┘         ║
                     ║ GND ────────────────────┘
                     ║ TRIG (GPIO 2) ──────────┐
                     ║ ECHO (GPIO 4) ──────────┤
                     ║                         │
                     ╚════════════════╝        │
                                              │
                                              ▼
                                     ┌─────────────┐
                                     │   ESP32     │
                                     │   DevKit    │
                                     │             │
                                     │  ┌─────┐   │
                                     │  │ USB │   │
                                     │  └─────┘   │
                                     │             │
                    ╔════════════════════════════╝
                    ║
         ┌──────────┴──────────┐
         │                     │
        GPIO 2 (TRIG) ────────┐│
        GPIO 4 (ECHO) ────────┼┤
        GPIO 5 (LED) ─────────┼┤
        GPIO 15 (PWM) ────────┼┤
        5V ───────────────────┼┤
        GND ───────────────────┘│
         │                     │
         ▼                     └─────────→ [SENSOR ULTRASÓNICO]
         
         │
         ├─────→ GPIO 5 → ╔═════════════════╗
         │                ║  LED AZUL       ║
         │                ╠═════════════════╣
         │                ║ Ánodo (+) ──────┘
         │           GND←─╫─ Cátodo (−)
         │                ╚═════════════════╝
         │
         └─────→ GPIO 15 → [SERVO MOTOR PWM]


┌──────────────────────────────────────────────────────────────────────┐
│                     FLUJO DE DATOS Y SEÑALES                         │
└──────────────────────────────────────────────────────────────────────┘

┌─────────┐      Pulsos (10µs)    ┌──────────────┐
│ ESP32   │──────────GPIO 2────→   │   HC-SR04    │
│ GPIO 2  │  (TRIG)                │              │  
│ (TRIG)  │                        │   SENSOR     │
└─────────┘                        │              │
                                    └──────────────┘
                                            ↓
┌─────────┐      Eco (variable)    ┌──────────────┐
│ ESP32   │←──────────GPIO 4────    │   HC-SR04    │
│ GPIO 4  │  (ECHO)                 │              │
│ (ECHO)  │                         │   SENSOR     │
└─────────┘                         └──────────────┘


┌─────────┐      Encendido/       ┌──────────────┐
│ ESP32   │      Apagado           │              │
│ GPIO 5  │────────────────────→   │  LED AZUL    │
│ (LED)   │    (digitalWrite)      │              │
└─────────┘                        └──────────────┘
     ▲
     │
 Comandos Serial
 (ON/OFF/BLINK)


┌─────────┐      PWM Signal        ┌──────────────┐
│ ESP32   │──────────────────────→  │   SERVO      │
│GPIO 15  │      (mediante         │   MOTOR      │
│ (PWM)   │      ESP32Servo)        │              │
└─────────┘                        └──────────────┘
```

### Tabla Resumida de Conexiones

```
ESP32 PIN  │  Componente      │  Pin del Componente  │  Color
───────────┼──────────────────┼──────────────────────┼───────────
   5V      │  HC-SR04 Sensor  │  VCC                 │  Rojo
   5V      │  Servo Motor     │  V+                  │  Rojo
   GND.1   │  Servo Motor     │  GND                 │  Negro
   GND.2   │  HC-SR04 Sensor  │  GND                 │  Negro
  GPIO 2   │  HC-SR04 Sensor  │  TRIG                │  Café
  GPIO 4   │  HC-SR04 Sensor  │  ECHO                │  Naranja
  GPIO 5   │  LED Azul        │  Ánodo (+)           │  Rojo
   GND.3   │  LED Azul        │  Cátodo (−)          │  Negro
 GPIO 15   │  Servo Motor     │  PWM (Señal)         │  Naranja
```

---

## Componentes del Proyecto

| Componente | ID en Wokwi | Descripción |
|---|---|---|
| ESP32 DevKit C v4 | `esp` | Microcontrolador principal |
| Protoboard (Half) | `bb1` | Tablero de conexiones |
| LED Azul | `led1` | Indicador visual |
| Servo Motor | `servo1` | Simula apertura/cierre de puerta |
| Sensor Ultrasónico HC-SR04 | `ultrasonic1` | Medición de distancia |

---

## Conexiones del Circuito

### Servo Motor (`servo1`)

| Pin del Servo | Pin del ESP32 | Color de Cable |
|---|---|---|
| V+ (alimentación) | 5V | Rojo |
| GND (tierra) | GND.1 | Negro |
| PWM (señal) | GPIO 15 | Naranja |

### LED Azul (`led1`)

| Pin del LED | Pin del ESP32 | Color de Cable |
|---|---|---|
| Ánodo (+) | GPIO 5 | Rojo |
| Cátodo (−) | GND.3 | Negro |

### Sensor Ultrasónico HC-SR04 (`ultrasonic1`)

| Pin del Sensor | Pin del ESP32 | Color de Cable |
|---|---|---|
| VCC (alimentación) | Riel + de protoboard (bb1:tn.4) | Rojo |
| GND (tierra) | GND.2 | Negro |
| TRIG | GPIO 2 | Café (`#8f4814`) |
| ECHO | GPIO 4 | Naranja |

> **Nota:** La alimentación VCC del sensor viene del riel positivo de la protoboard, que está conectado al pin **5V** del ESP32.

---

## Resumen de Pines Usados del ESP32

| GPIO | Función |
|---|---|
| GPIO 2 | TRIG — Sensor ultrasónico |
| GPIO 4 | ECHO — Sensor ultrasónico |
| GPIO 5 | LED Azul (Ánodo) |
| GPIO 15 | Señal PWM del Servo |
| 5V | Alimentación Servo y Sensor |
| GND.1 | Tierra del Servo |
| GND.2 | Tierra del Sensor + Protoboard |
| GND.3 | Tierra del LED |

---

## Notas Importantes

### Conflicto de Pines
- El **GPIO 2 (TRIG)** puede coincidir con otros periféricos. Si hay conflicto, cambiar a **GPIO 13** o **GPIO 14**.
- Cada pin debe tener una única función.

###  Tiempos y Delays
- **Medición de distancia**: Se realiza cada **200ms** para no saturar el sistema.
- **Parpadeo máximo**: Hasta **5000ms** por ciclo.
- **Servo**: Tarda **1 segundo** en completar el movimiento.

###  Comunicación Serial
- **Velocidad**: 115200 baud
- **Formato**: Comandos en mayúsculas, separados por saltos de línea
- **Monitor Serial**: Usar Arduino IDE o similar para ver mensajes

###  Troubleshooting

| Problema | Causa | Solución |
|---|---|---|
| LED no enciende | Pin mal conectado o GPIO incorrecto | Verificar conexión y valor de `LED_PIN` |
| Sensor no mide | No hay alimentación o pines invertidos | Revisar 5V y GND, TRIG/ECHO correctos |
| Servo no se mueve | Pin no configurado o sin PWM | Verificar `pinServo` y función `attach()` |
| comandos no funcionan | Serial desconectado | Verificar conexión USB y baudrate |


---


---

## Referencias

- [Documentación oficial de ESP32](https://docs.espressif.com/)
- [Librería ESP32Servo](https://github.com/jkb-git/ESP32Servo)
- [Sensor HC-SR04](https://www.alldatasheet.com/datasheet-pdf/pdf/1132188/ELECTRONICSPICES/HC-SR04.html)
- [Arduino IDE](https://www.arduino.cc/en/software)
- [Simulador Wokwi](https://wokwi.com/)
