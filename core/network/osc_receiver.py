"""
Adaptador de Recepción de Información (UDP/OSC RX).
Implementa ISandInputPort para proveer datos de altura de la arena.
"""
from __future__ import annotations
import threading
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
from core.contracts import ISandInputPort


class OSCSandInputAdapter(ISandInputPort):
    """
    Receptor OSC que procesa los paquetes '/sandbox/grid' emitidos
    por el motor Magic Sand C++ (puerto 7000 por defecto).
    """
    def __init__(self, ip: str = "127.0.0.1", port: int = 7000, cols: int = 2, rows: int = 2):
        self.cols = cols
        self.rows = rows
        self.heights = [0.0] * (cols * rows)
        self.lock = threading.Lock()
        self.ip = ip
        self.port = port
        self.server: BlockingOSCUDPServer | None = None
        self.thread: threading.Thread | None = None
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
            print(f"[OSCSandInputAdapter] Receptor OSC iniciado en {self.ip}:{self.port}")
        except Exception as e:
            print(f"[OSCSandInputAdapter] Error al iniciar receptor OSC en {self.ip}:{self.port}: {e}")

    def set_grid_size(self, cols: int, rows: int) -> None:
        with self.lock:
            self.cols = cols
            self.rows = rows

    def get_heights(self) -> list[float]:
        with self.lock:
            return list(self.heights)

    def reset(self) -> None:
        pass

    def close(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
