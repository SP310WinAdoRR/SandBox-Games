from __future__ import annotations
import threading
from abc import ABC, abstractmethod
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer


class BaseDataProvider(ABC):
    """
    Interfaz abstracta de proveedor de alturas de la arena.
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
        """Nivela o aplana la arena a 0 mm."""
        pass


class OSCDataProvider(BaseDataProvider):
    """
    Receptor OSC de producción.
    Escucha paquetes UDP emitidos por Magic Sand en C++ (puerto 7000).
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
        pass
