from pythonosc.udp_client import SimpleUDPClient

class MagicSandBridgeClient:
    """
    Cliente UDP que envía instrucciones de renderizado hacia Magic Sand (puerto 7001).
    Permite que el motor C++ dibuje directamente sobre la arena la interfaz del juego.
    """
    def __init__(self, host: str = "127.0.0.1", port: int = 7001):
        self.host = host
        self.port = port
        self.client = None
        try:
            self.client = SimpleUDPClient(host, port)
        except Exception as e:
            print(f"[BridgeClient] Advertencia: No se pudo conectar a {host}:{port}: {e}")

    def send_grid_setup(self, cols: int, rows: int):
        """Indica a Magic Sand las dimensiones de la cuadrícula a proyectar."""
        if self.client:
            self.client.send_message("/render/grid/setup", [cols, rows])

    def send_cell_state(self, index: int, r: int, g: int, b: int, alpha: float, text: str = ""):
        """Pinta un cuadrante en la proyección con color, opacidad y texto opcional."""
        if self.client:
            self.client.send_message("/render/grid/cell", [index, r, g, b, float(alpha), str(text)])

    def send_hud_timer(self, progress: float, r: int = 255, g: int = 255, b: int = 255):
        """Actualiza la barra de tiempo proyectada (valor entre 0.0 y 1.0)."""
        if self.client:
            self.client.send_message("/render/hud/timer", [float(progress), r, g, b])

    def send_hud_title(self, text: str):
        """Muestra un título principal proyectado sobre la arena."""
        if self.client:
            self.client.send_message("/render/hud/title", [str(text)])

    def send_round_clear(self):
        """Limpia los overlays proyectados."""
        if self.client:
            self.client.send_message("/render/clear", [])
