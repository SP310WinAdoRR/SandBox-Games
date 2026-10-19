# SandBox Games - Suite de Videojuegos para Rehabilitación Motriz en AR

Suite de videojuegos terapéuticos diseñados para operar sobre una **Caja de Arena de Realidad Aumentada (AR Sandbox)** con sensor Kinect y proyector colocalizado. 

Desarrollado para el **Grupo de Investigación Multimedia** de la **Universidad Distrital Francisco José de Caldas (2026)**.

---

## 🎯 Objetivo Clínico y Terapéutico

Estimular la **coordinación visomotora**, la **fuerza graduada de prensión/excavación** y la **coordinación bimanual** en pacientes con secuelas neurológicas (ACV, traumatismos) o afecciones musculoesqueléticas.

### Características del Sistema:
1. **Mecánica Nuclear de Cuadrantes (estilo *Balatro*):** El terreno de arena se discretiza en zonas de interacción ($2 \times 2$ hasta $8 \times 8$). El paciente debe acumular o retirar arena hasta alcanzar un umbral de elevación ($\Delta h$).
2. **Validación Continua en Tiempo Real:** La ronda se supera inmediatamente en el milisegundo exacto en que la arena alcanza el umbral de altura objetivo leída por el Kinect.
3. **Fase de Aplanado / Nivelación:** Entre rondas, el paciente debe alisar la arena, ejercitando la extensión y flexión de la articulación de la muñeca y hombro.
4. **Telemetría Clínica Automática:** Registro de tiempo de reacción, precisión, curvas de fatiga y exportación a formatos `.csv` y `.json` para el fisioterapeuta.
5. **Modo Emulador para Desarrollo en Casa:** Permite probar y ajustar el juego sin necesidad de tener el sensor Kinect ni el proyector físico conectados.

---

## 🚀 Instalación y Puesta en Marcha

### Requisitos:
* Python 3.10+
* Entorno virtual de Python

### 1. Activar entorno virtual e instalar dependencias:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Ejecutar un Juego en Producción (`main.py`):
```bash
./.venv/bin/python main.py --game quadrant_game --patient PACIENTE_01
```
* `main.py` actúa como **Composition Root (Inyector de Dependencias)**: instancia los adaptadores de red (`OSCSandInputAdapter` y `OSCProjectionOutputAdapter`), los inyecta en el juego seleccionado dentro de `games/` y delega las ventanas a `PygameApplicationRunner`.

### 3. Herramientas de Testeo y Emulación:
* **Emulador con Ratón y Doble Ventana (`test_emulator.py`):**
  Inyecta `EmulatorSandInputAdapter` (en lugar de OSC) a cualquier juego de `games/` sin tocar el código del juego:
  ```bash
  ./.venv/bin/python test_emulator.py --game quadrant_game
  ```
* **Simulador del Motor C++ por Red (`mock_engine_osc.py`):**
  ```bash
  ./.venv/bin/python mock_engine_osc.py --self-test
  ```

---

## 📂 Arquitectura Modular por Inyección de Dependencias

Los juegos dentro de `games/` son tratados como **cajas negras (`ISandboxGame`)** que no conocen `pythonosc`, ni sockets UDP, ni crean ventanas `pygame.Window`. Toda la infraestructura de conexión y renderizado se inyecta desde `core/`:

```
SandBox-Games/
├── main.py                         # Composition Root (Inyector de Dependencias de Producción)
├── test_emulator.py                # Runner de testeo (inyecta emulador de ratón + 2da ventana)
├── mock_engine_osc.py              # Simulador externo del motor C++ (UDP/OSC)
├── core/                           # Infraestructura de Build, Red y Contratos DI
│   ├── contracts.py                # Interfaces: ISandInputPort, IProjectionOutputPort, ISandboxGame
│   ├── network/                    # Transmisión y Recepción UDP/OSC
│   │   ├── osc_receiver.py         # OSCSandInputAdapter (RX :7000)
│   │   └── osc_transmitter.py      # OSCProjectionOutputAdapter (TX :7001)
│   └── runtime/                    # Ciclo de vida de ventanas y superficies Pygame
│       └── pygame_runner.py        # PygameApplicationRunner y cargador dinámico de plugins
└── games/                          # Catálogo de Juegos (Cajas Negras independientes)
    └── quadrant_game/              # Juego 1: Rehabilitación por Cuadrantes
        ├── __init__.py             # Fábrica create_game(input_port, output_port, ...)
        ├── game.py                 # QuadrantTherapyGame(ISandboxGame)
        ├── config_manager.py       # Gestor de archivos .env del juego
        ├── metrics.py              # Exportación de métricas clínicas (CSV/JSON)
        ├── configs/                # Perfiles .env (default, baja_exigencia, alta_exigencia)
        └── records/                # Reportes clínicos exportados
```
