"""
Adaptador de Transmisión de Información (UDP/OSC TX).
Implementa IProjectionOutputPort para ser inyectado en cualquier juego.
"""
from __future__ import annotations
from pythonosc.udp_client import SimpleUDPClient
from core.contracts import IProjectionOutputPort


class OSCProjectionOutputAdapter(IProjectionOutputPort):
    """
    Cliente UDP/OSC que transmite instrucciones de renderizado hacia el motor C++
    Magic-Sand-Unlimited (puerto 7001 por defecto).
    """
    def __init__(self, host: str = "127.0.0.1", port: int = 7001):
        self.host = host
        self.port = port
        self.client: SimpleUDPClient | None = None
        self.reconfigure_endpoint(host, port)

    def reconfigure_endpoint(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        try:
            self.client = SimpleUDPClient(host, port)
        except Exception as e:
            print(f"[OSCProjectionOutputAdapter] Advertencia al conectar hacia {host}:{port}: {e}")

    def send_grid_setup(self, cols: int, rows: int) -> None:
        if self.client:
            self.client.send_message("/render/grid/setup", [int(cols), int(rows)])

    def send_cell_state(
        self,
        index: int,
        r: int,
        g: int,
        b: int,
        alpha: float = 1.0,
        text: str = "",
    ) -> None:
        if self.client:
            self.client.send_message(
                "/render/grid/cell",
                [int(index), int(r), int(g), int(b), float(alpha), str(text)],
            )

    def send_cell_progress(
        self,
        index: int,
        base_col: tuple[int, int, int],
        inner_col: tuple[int, int, int],
        inner_scale: float,
    ) -> None:
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

    def send_hud_timer(
        self,
        progress: float,
        r: int = 255,
        g: int = 255,
        b: int = 255,
        alpha: int = 75,
    ) -> None:
        if self.client:
            self.client.send_message(
                "/render/hud/timer",
                [float(progress), int(r), int(g), int(b), int(alpha)],
            )

    def send_hud_stats(self, round_num: int, score: int) -> None:
        if self.client:
            self.client.send_message("/render/hud/stats", [int(round_num), int(score)])

    def send_hud_title(self, text: str) -> None:
        if self.client:
            self.client.send_message("/render/hud/title", [str(text)])

    def send_round_clear(self) -> None:
        if self.client:
            self.client.send_message("/render/clear", [])
