# Proyecto ESP32 — Documentación del Circuito y Código


## Explicación del Código


---

### Variables y Librerías


---

### `setup()`

Inicializa el sistema. Configura la comunicación serial, define los pines del LED y del sensor ultrasónico, configura el servo y realiza una primera medición de distancia.


---

### `loop()`

Se ejecuta continuamente. Lee comandos del usuario, mide la distancia periódicamente, ejecuta acciones automáticas si están activadas y controla el parpadeo del LED.

---

### `medirDistancia()`

Envía un pulso al sensor ultrasónico y mide el tiempo que tarda en regresar el eco para calcular la distancia en centímetros.


---

### `obtenerDistancia()`

Devuelve la última distancia medida. Si no hay datos válidos, regresa -1.


---

### `encenderLED()`

Enciende el LED en modo manual y desactiva otros modos.


---

### `apagarLED()`

Apaga el LED en modo manual y desactiva otros modos.


---

### `iniciarParpadeo()`

Activa el parpadeo del LED con tiempos definidos de encendido y apagado.


---

### `detenerParpadeo()`

Detiene el parpadeo y regresa al modo manual.


---

### `habilitarAutoMode()`

Activa o desactiva el modo automático basado en distancia.


---

### `manejarAccionAutomatica()`

Enciende o apaga el LED dependiendo de si un objeto está dentro del rango definido.


---

### `setDistanceThreshold()`

Permite cambiar el umbral de distancia para el modo automático.


---

### `abrirPuerta()`

Mueve el servo a 90 grados simulando la apertura de una puerta.


---

### `cerrarPuerta()`

Mueve el servo a 0 grados simulando el cierre de una puerta.


---

### `procesarComando()`

Interpreta los comandos escritos por el usuario en el monitor serial.


---

### `procesarComandoBlink()`

Gestiona los comandos relacionados con el parpadeo del LED.


---

### `procesarComandoAuto()`

Activa o desactiva el modo automático.


---

### `procesarComandoUmbral()`

Permite modificar el umbral de distancia.


---

### `mostrarEstado()`

Muestra información completa del estado del sistema.

---

### `mostrarDistancia()`

Muestra la distancia actual medida por el sensor.


---

### `mostrarAyuda()`

Muestra la lista de comandos disponibles.

---

## Diagrama del Circuito (Wokwi)

> Simulación en Wokwi: [https://wokwi.com/projects/460879044104559617](https://wokwi.com/projects/460879044104559617)

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