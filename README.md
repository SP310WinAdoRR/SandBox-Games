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

### 2. Ejecutar el Juego de las Cajas (Modo Emulador en Casa):
```bash
./.venv/bin/python quadrant_game/main.py
```
* **Clic Izquierdo (mantener presionado):** Acumula / sube arena virtual en el cuadrante (+mm).
* **Clic Derecho (mantener presionado):** Excava / retira arena virtual (-mm).
* **Tecla [ESPACIO]:** Iniciar sesión o saltar fase de preparación.
* **Tecla [TAB]:** Alternar entre pestaña de Monitoreo Clínico y Configuración (`.env`).
* **Tecla [R]:** Aplanar la arena a nivel $0\text{ mm}$.
* **Tecla [ESC]:** Salir y exportar métricas de la sesión.

### 3. Ejecutar en Modo Producción (En el Laboratorio con Kinect):
```bash
./.venv/bin/python quadrant_game/main.py --live --patient PACIENTE_01
```
* Escuchará automáticamente los datos de elevación del sensor Kinect emitidos por Magic Sand en `127.0.0.1:7000` y enviará la proyección al puerto `127.0.0.1:7001`.

### 4. Prueba de Conexión / Simulador del Motor C++ (En la raíz):
```bash
./.venv/bin/python mock_engine_osc.py --self-test
```

---

## 📂 Estructura del Proyecto

```
SandBox-Games/
├── README.md                   # Documentación general de la suite
├── requirements.txt            # Dependencias (pygame-ce, python-osc)
├── mock_engine_osc.py          # Herramienta de testeo/simulación del motor C++ (UDP/OSC)
└── quadrant_game/              # Juego 1: Rehabilitación por Cuadrantes (Cajas)
    ├── main.py                 # Punto de entrada del juego (Emulador o Live)
    ├── configs/                # Perfiles de configuración (.env: default, baja/alta exigencia)
    ├── records/                # Reportes clínicos exportados de las sesiones (CSV/JSON)
    └── src/
        ├── data_provider.py    # Proveedor de datos (Emulador de ratón vs. Receptor OSC)
        ├── bridge_client.py    # Emisor UDP/OSC de comandos de proyección hacia C++
        ├── config_manager.py   # Gestor de archivos .env (Modo Fácil y Modo Avanzado)
        ├── metrics.py          # Registro y exportación de métricas clínicas
        └── quadrant_game.py    # Lógica, progresión de niveles y UI de Telemetría/Proyección
```
