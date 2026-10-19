from __future__ import annotations
import threading
from abc import ABC, abstractmethod
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer

class BaseDataProvider(ABC):
    """
    Interfaz abstracta de proveedor de alturas de la arena.
    Desacopla la lógica del juego de la fuente física (Kinect real o Simulador).
    """
    @abstractmethod
    def get_heights(self) -> list[float]:
        """Retorna una lista con la elevación media (en milímetros) de cada celda."""
        pass

    @abstractmethod
    def set_grid_size(self, cols: int, rows: int):
        """Reconfigura las dimensiones de la cuadrícula."""
        pass

    @abstractmethod
    def reset(self):
        """Nivela o aplanada la arena a 0 mm."""
        pass


class EmulatorDataProvider(BaseDataProvider):
    """
    Emulador interactivo de arena para desarrollo en casa.
    Permite modificar la altura usando el ratón o atajos.
    """
    def __init__(self, cols: int = 2, rows: int = 2):
        self.cols = cols
        self.rows = rows
        self.heights = [0.0] * (cols * rows)
        self.rate_per_second = 35.0  # mm por segundo al presionar

    def set_grid_size(self, cols: int, rows: int):
        self.cols = cols
        self.rows = rows
        self.heights = [0.0] * (cols * rows)

    def get_heights(self) -> list[float]:
        return list(self.heights)

    def modify_cell(self, index: int, delta_mm: float):
        if 0 <= index < len(self.heights):
            self.heights[index] = max(-80.0, min(120.0, self.heights[index] + delta_mm))

    def reset(self):
        self.heights = [0.0] * len(self.heights)


class OSCDataProvider(BaseDataProvider):
    """
    Receptor OSC de producción para el laboratorio.
    Escucha paquetes UDP emitidos por Magic Sand en C++.
    """
    def __init__(self, ip: str = "127.0.0.1", port: int = 7000, cols: int = 2, rows: int = 2):
        self.cols = cols
        self.rows = rows
        self.heights = [0.0] * (cols * rows)
        self.lock = threading.Lock()
        self.ip = ip
        self.port = port
        self.server = None
        self.thread = None
        self._start_server()

    def _on_grid_message(self, address: str, *args):
        with self.lock:
            # Los argumentos son las alturas en mm enviadas por Magic Sand
            self.heights = [float(h) for h in args]

    def _start_server(self):
        dispatcher = Dispatcher()
        dispatcher.map("/sandbox/grid", self._on_grid_message)
        try:
            self.server = BlockingOSCUDPServer((self.ip, self.port), dispatcher)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            print(f"[OSCDataProvider] Escuchando datos de Magic Sand en {self.ip}:{self.port}")
        except Exception as e:
            print(f"[OSCDataProvider] Error al iniciar servidor OSC: {e}")

    def set_grid_size(self, cols: int, rows: int):
        with self.lock:
            self.cols = cols
            self.rows = rows

    def get_heights(self) -> list[float]:
        with self.lock:
            return list(self.heights)

    def reset(self):
        # En hardware real, la arena se resetea físicamente aplanándola
        pass
