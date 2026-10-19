from pythonosc.udp_client import SimpleUDPClient


class MagicSandBridgeClient:
    """
    Cliente UDP/OSC que envía instrucciones de renderizado hacia Magic Sand C++ (puerto 7001).
    Permite que el motor C++ dibuje directamente sobre el proyector de la caja de arena
    y muestre telemetría en la ventana de monitoreo del operador.
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
            self.client.send_message("/render/grid/setup", [int(cols), int(rows)])

    def send_cell_state(self, index: int, r: int, g: int, b: int, alpha: float = 1.0, text: str = ""):
        """Pinta un cuadrante sólido en la proyección."""
        if self.client:
            self.client.send_message("/render/grid/cell", [int(index), int(r), int(g), int(b), float(alpha), str(text)])

    def send_cell_progress(
        self,
        index: int,
        base_col: tuple[int, int, int],
        inner_col: tuple[int, int, int],
        inner_scale: float,
    ):
        """
        Envía el estado de progreso concéntrico de una celda (base Cian + interior Rojo/Verde
        que se reduce conforme se alcanza el umbral de altura).
        """
        if self.client:
            self.client.send_message(
                "/render/grid/cell_progress",
                [
                    int(index),
                    int(base_col[0]), int(base_col[1]), int(base_col[2]),
                    int(inner_col[0]), int(inner_col[1]), int(inner_col[2]),
                    float(inner_scale),
                ],
            )

    def send_hud_timer(self, progress: float, r: int = 255, g: int = 255, b: int = 255, alpha: int = 75):
        """Actualiza la torta de tiempo central proyectada (valor entre 0.0 y 1.0) y su opacidad."""
        if self.client:
            self.client.send_message("/render/hud/timer", [float(progress), int(r), int(g), int(b), int(alpha)])

    def send_hud_stats(self, round_num: int, score: int):
        """Actualiza el nivel y puntaje superpuestos sobre el mapa."""
        if self.client:
            self.client.send_message("/render/hud/stats", [int(round_num), int(score)])

    def send_hud_title(self, text: str):
        """Muestra u oculta el aviso central translúcido sobre la arena."""
        if self.client:
            self.client.send_message("/render/hud/title", [str(text)])

    def send_round_clear(self):
        """Limpia los overlays proyectados."""
        if self.client:
            self.client.send_message("/render/clear", [])
