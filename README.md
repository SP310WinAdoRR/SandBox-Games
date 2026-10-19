# SandBox Games - Suite de Videojuegos para Rehabilitación Motriz en AR

Suite de videojuegos terapéuticos diseñados para operar sobre una **Caja de Arena de Realidad Aumentada (AR Sandbox)** equipada con un sensor de profundidad (Kinect) y un proyector colocalizado.

Proyecto desarrollado para el **Grupo de Investigación Multimedia** de la **Universidad Distrital Francisco José de Caldas (2026)**.

---

## Objetivo del Proyecto

Proporcionar un entorno interactivo y cuantitativo para la rehabilitación motriz, enfocado en la estimulación de:
* **Coordinación visomotora.**
* **Control y graduación de fuerza** mediante la manipulación, acumulación y excavación de arena.
* **Coordinación bimanual** y movilidad articular (muñeca, codo y hombro).

El sistema registra métricas objetivas de desempeño durante cada sesión para facilitar el seguimiento terapéutico por parte de profesionales de la salud.

---

## Características Principales

1. **Mecánica por Cuadrantes:** El área de trabajo se divide en cuadrantes configurables ($2 \times 2$ hasta $8 \times 8$). El usuario debe modificar la elevación de la arena en cuadrantes específicos hasta alcanzar una diferencia de altura objetivo ($\Delta h$).
2. **Evaluación Continua en Tiempo Real:** El sistema monitorea continuamente las alturas enviadas por el sensor y valida el cumplimiento de las metas de cada ronda de forma inmediata.
3. **Fase de Nivelación:** Entre rondas, el sistema puede solicitar la nivelación del terreno, incentivando movimientos de barrido y extensión articular.
4. **Telemetría Clínica:** Registro automático de tiempos de reacción, tiempos de resolución, tasas de acierto y curvas de fatiga, con exportación a formatos `.csv` y `.json`.
5. **Modo de Emulación:** Permite ejecutar y validar los juegos en cualquier equipo mediante interacción con ratón, sin requerir hardware especializado (caja de arena, sensor de profundidad o proyector).

---

## Requisitos e Instalación

### Requisitos:
* Python 3.10 o superior
* Entorno virtual de Python (recomendado)

### Instalación de dependencias:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Modos de Ejecución

### 1. Ejecución con Hardware / Conexión OSC (`main.py`)
Inicia el sistema conectándose al motor de captura y proyección mediante el protocolo OSC/UDP (puerto 7000 para recepción de alturas y puerto 7001 para comandos de proyección):

```bash
./.venv/bin/python main.py --game quadrant_game --patient PACIENTE_01
```

Parámetros principales:
* `--game`: Nombre del módulo del juego a ejecutar (por defecto: `quadrant_game`).
* `--patient`: Identificador del paciente para el reporte clínico.
* `--env`: Perfil de configuración inicial dentro de `configs/` (por defecto: `default.env`).
* `--host`: Dirección IP del motor de captura (por defecto: `127.0.0.1`).
* `--rx-port`: Puerto UDP de recepción de datos de altura (por defecto: `7000`).
* `--tx-port`: Puerto UDP de transmisión de comandos gráficos (por defecto: `7001`).

### 2. Ejecución en Modo Emulador (`test_emulator.py`)
Permite probar los juegos de forma interactiva utilizando el ratón para simular variaciones de elevación en la arena, sin necesidad de conexión OSC ni sensores físicos:

```bash
./.venv/bin/python test_emulator.py --game quadrant_game
```

Interacción en el emulador:
* **Clic izquierdo sostenido:** Aumenta la altura de la arena en la celda seleccionada.
* **Clic derecho sostenido:** Reduce la altura de la arena en la celda seleccionada.
* **Ventana de Inspector:** Presenta la telemetría, estado de la ronda y controles de depuración.

### 3. Simulación de Tráfico OSC (`mock_engine_osc.py`)
Herramienta de prueba para simular el flujo de datos del motor de captura y proyección (Magic Sand C++), útil para pruebas de integración de red:

* **Prueba de integración (handshake UDP/OSC):**
  ```bash
  ./.venv/bin/python mock_engine_osc.py --self-test
  ```
* **Simulación interactiva con agente automático:**
  ```bash
  ./.venv/bin/python mock_engine_osc.py --autopilot
  ```

---

## Arquitectura del Software

El sistema implementa un diseño modular desacoplado mediante inversión de dependencias:

* **Juegos (`games/`):** Cada juego implementa la interfaz `ISandboxGame` y opera de forma independiente de los detalles de red o de la biblioteca gráfica.
* **Puertos de Entrada y Salida (`core/contracts.py`):** Los juegos interactúan exclusivamente a través de contratos abstractos (`ISandInputPort` e `IProjectionOutputPort`).
* **Adaptadores (`core/network/` y `test_emulator.py`):** Proveen la implementación concreta de los puertos de entrada/salida para el entorno físico (OSC sobre UDP) o el entorno de pruebas (simulación por ratón).
* **Gestor de Ciclo de Vida (`core/runtime/`):** Administra el bucle principal de la aplicación, el despacho de eventos y la renderización de ventanas en Pygame.

```
SandBox-Games/
├── main.py                         # Punto de entrada principal con conexión de red OSC
├── test_emulator.py                # Ejecutor en modo emulador con interacción por ratón
├── mock_engine_osc.py              # Simulador del motor de captura y proyección (OSC/UDP)
├── core/                           # Módulos base de infraestructura
│   ├── contracts.py                # Interfaces base (ISandInputPort, IProjectionOutputPort, ISandboxGame)
│   ├── network/                    # Adaptadores de comunicación OSC sobre UDP
│   │   ├── osc_receiver.py         # Recepción de datos de profundidad (RX :7000)
│   │   └── osc_transmitter.py      # Transmisión de comandos visuales (TX :7001)
│   └── runtime/                    # Gestión del bucle de aplicación y ventanas Pygame
│       └── pygame_runner.py        # Orquestador del ciclo de vida y carga dinámica de juegos
└── games/                          # Catálogo de juegos terapéuticos
    └── quadrant_game/              # Juego de estimulación motriz por cuadrantes
        ├── __init__.py             # Inicialización y fábrica del juego
        ├── game.py                 # Lógica principal del juego (QuadrantTherapyGame)
        ├── config_manager.py       # Carga y validación de parámetros de configuración
        ├── metrics.py              # Registro y exportación de métricas clínicas
        ├── configs/                # Perfiles de dificultad (.env)
        └── records/                # Directorio de reportes generados
```
