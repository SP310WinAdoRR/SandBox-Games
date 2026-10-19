#!/usr/bin/env python3
"""
Simulador de Producción del Motor C++ (Magic-Sand-Unlimited / CRemoteGameController).

Emula exactamente los dos sockets UDP/OSC del motor C++:
  - TX -> 127.0.0.1:7000 : Envía alturas de la arena a 30 Hz en '/sandbox/grid' (,ffff)
  - RX <- 127.0.0.1:7001 : Escucha comandos de proyección desde SandBox-Games ('/render/...')

Modos de uso:
  1. Simulación en vivo con Autopiloto (juega solo respondiendo a los colores proyectados):
     Terminal 1: ./venv/bin/python main.py --live
     Terminal 2: ./venv/bin/python mock_engine_osc.py --autopilot

  2. Prueba automática de integración (Handshake bidireccional sin abrir ventanas):
     ./venv/bin/python mock_engine_osc.py --self-test
"""
from __future__ import annotations
import argparse
import random
import threading
import time
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import BlockingOSCUDPServer
from pythonosc.udp_client import SimpleUDPClient


class MockCppEngine:
    def __init__(self, host: str = "127.0.0.1", tx_port: int = 7000, rx_port: int = 7001):
        self.host = host
        self.tx_port = tx_port
        self.rx_port = rx_port

        self.cols = 2
        self.rows = 2
        self.heights = [0.0, 0.0, 0.0, 0.0]
        self.cell_inner_color: dict[int, tuple[int, int, int]] = {}
        self.cell_inner_scale: dict[int, float] = {}
        self.current_title = ""
        self.current_round = 0
        self.current_score = 0
        self.timer_ratio = 0.0

        self.rx_packet_count = 0
        self.tx_packet_count = 0
        self.last_rx_time = 0.0
        self.lock = threading.Lock()

        self.tx_client = SimpleUDPClient(self.host, self.tx_port)
        self.server: BlockingOSCUDPServer | None = None
        self.server_thread: threading.Thread | None = None

    def start_rx_server(self):
        dispatcher = Dispatcher()
        dispatcher.map("/render/grid/setup", self._on_grid_setup)
        dispatcher.map("/render/grid/cell", self._on_grid_cell)
        dispatcher.map("/render/grid/cell_progress", self._on_grid_cell_progress)
        dispatcher.map("/render/hud/timer", self._on_hud_timer)
        dispatcher.map("/render/hud/stats", self._on_hud_stats)
        dispatcher.map("/render/hud/title", self._on_hud_title)
        dispatcher.map("/render/clear", self._on_clear)

        self.server = BlockingOSCUDPServer((self.host, self.rx_port), dispatcher)
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()

    def _mark_rx(self):
        self.rx_packet_count += 1
        self.last_rx_time = time.time()

    def _on_grid_setup(self, address: str, *args):
        with self.lock:
            self._mark_rx()
            if len(args) >= 2:
                new_cols, new_rows = max(1, int(args[0])), max(1, int(args[1]))
                if new_cols * new_rows != len(self.heights):
                    self.cols = new_cols
                    self.rows = new_rows
                    self.heights = [0.0] * (self.cols * self.rows)

    def _on_grid_cell(self, address: str, *args):
        with self.lock:
            self._mark_rx()
            if len(args) >= 5:
                idx = int(args[0])
                self.cell_inner_scale[idx] = 0.0

    def _on_grid_cell_progress(self, address: str, *args):
        with self.lock:
            self._mark_rx()
            if len(args) >= 8:
                idx = int(args[0])
                ir, ig, ib = int(args[4]), int(args[5]), int(args[6])
                scale = float(args[7])
                self.cell_inner_color[idx] = (ir, ig, ib)
                self.cell_inner_scale[idx] = scale

    def _on_hud_timer(self, address: str, *args):
        with self.lock:
            self._mark_rx()
            if len(args) >= 1:
                self.timer_ratio = float(args[0])

    def _on_hud_stats(self, address: str, *args):
        with self.lock:
            self._mark_rx()
            if len(args) >= 2:
                self.current_round = int(args[0])
                self.current_score = int(args[1])

    def _on_hud_title(self, address: str, *args):
        with self.lock:
            self._mark_rx()
            self.current_title = str(args[0]) if args else ""

    def _on_clear(self, address: str, *args):
        with self.lock:
            self._mark_rx()
            self.current_title = ""
            self.cell_inner_scale.clear()

    def step_autopilot(self, dt: float):
        """
        Simula un paciente/operador moviendo la arena física en respuesta
        a lo que el juego proyecta por el puerto 7001:
          - Si el título pide "Aplane la arena" o "Mueva la arena": ajusta las alturas.
          - Si un cuadrante tiene interior ROJO (ir > 200, ig < 100): acumula arena (+mm).
          - Si un cuadrante tiene interior VERDE (ig > 160, ir < 100): excava arena (-mm).
        """
        with self.lock:
            title_lower = self.current_title.lower()

            if "mueva la arena" in title_lower:
                # Provocar variación > 5 mm para iniciar la partida automáticamente
                self.heights[0] = 12.0
                return

            if "aplane la arena" in title_lower:
                # Nivelar suavemente todos los cuadrantes hacia 0.0 mm
                for i in range(len(self.heights)):
                    if abs(self.heights[i]) < 1.5:
                        self.heights[i] = 0.0
                    else:
                        self.heights[i] *= 0.82
                return

            # Durante PLAYING: leer el color proyectado en cada celda
            rate_mm_s = 18.0
            for i in range(len(self.heights)):
                scale = self.cell_inner_scale.get(i, 0.0)
                ir, ig, ib = self.cell_inner_color.get(i, (0, 184, 220))

                if scale > 0.08:
                    # Rojo (Acumular / Poner arena) -> subir mm
                    if ir > 200 and ig < 100:
                        self.heights[i] += rate_mm_s * dt
                    # Verde (Excavar / Sacar arena) -> bajar mm
                    elif ig > 160 and ir < 100:
                        self.heights[i] -= rate_mm_s * dt

    def send_grid_frame(self):
        with self.lock:
            payload = [float(round(h, 2)) for h in self.heights]
        self.tx_client.send_message("/sandbox/grid", payload)
        self.tx_packet_count += 1


def encode_cpp_osc_grid(heights: list[float]) -> bytes:
    """
    Replica byte por byte la función C++ CRemoteGameController::sendGridElevationsOSC()
    de Magic-Sand-Unlimited (alineación a 4 bytes y float32 Big-Endian).
    """
    import struct

    def osc_str(s: str) -> bytes:
        b = s.encode("ascii") + b"\x00"
        while len(b) % 4 != 0:
            b += b"\x00"
        return b

    pkt = bytearray()
    pkt.extend(osc_str("/sandbox/grid"))
    pkt.extend(osc_str("," + ("f" * len(heights))))
    for h in heights:
        pkt.extend(struct.pack(">f", float(h)))
    return bytes(pkt)


def run_self_test() -> int:
    """
    Ejecuta una prueba de integración completa en local verificando:
      1. Paquete binario crudo idéntico al C++ (sendGridElevationsOSC) -> OSCDataProvider
      2. MagicSandBridgeClient -> Servidor receptor del Motor (:17001)
    (Usa puertos 17000/17001 para no colisionar si ya tienes main.py abierto).
    """
    import socket
    from src.data_provider import OSCDataProvider
    from src.bridge_client import MagicSandBridgeClient

    tx_test_port = 17000
    rx_test_port = 17001

    print("=== INICIANDO PRUEBA DE INTEGRACIÓN UDP/OSC (MOTOR C++ <-> VIDEOJUEGO PYTHON) ===")
    engine = MockCppEngine(host="127.0.0.1", tx_port=tx_test_port, rx_port=rx_test_port)
    engine.start_rx_server()

    provider = OSCDataProvider(ip="127.0.0.1", port=tx_test_port, cols=2, rows=2)
    bridge = MagicSandBridgeClient(host="127.0.0.1", port=rx_test_port)

    try:
        # 1. Simular envío binario exacto de C++ (CRemoteGameController::sendGridElevationsOSC)
        test_heights = [21.5, -18.0, 4.25, 0.0]
        raw_cpp_packet = encode_cpp_osc_grid(test_heights)
        raw_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for _ in range(3):
            raw_sock.sendto(raw_cpp_packet, ("127.0.0.1", tx_test_port))
            time.sleep(0.03)
        raw_sock.close()

        received_heights = provider.get_heights()
        print(f"  [1/2] TX Binario C++ (:{tx_test_port}) -> RX Juego: Enviado={test_heights} | Recibido={received_heights}")
        ok_tx = all(abs(a - b) < 0.01 for a, b in zip(test_heights, received_heights))

        # 2. Simular envío de proyección desde el Juego hacia el Motor C++ (:17001)
        bridge.send_grid_setup(2, 2)
        bridge.send_cell_progress(0, (0, 184, 220), (255, 30, 39), 0.65)
        bridge.send_hud_timer(0.75, 255, 255, 255)
        bridge.send_hud_stats(3, 250)
        bridge.send_hud_title("PRUEBA OK")
        time.sleep(0.1)

        print(
            f"  [2/2] TX Juego (:{rx_test_port}) -> RX Motor C++: Paquetes recibidos={engine.rx_packet_count} | "
            f"Nivel={engine.current_round} | Puntaje={engine.current_score} | "
            f"Escala Q1={engine.cell_inner_scale.get(0, 0.0):.2f}"
        )
        ok_rx = (
            engine.rx_packet_count >= 5
            and engine.current_round == 3
            and engine.current_score == 250
            and abs(engine.cell_inner_scale.get(0, 0.0) - 0.65) < 0.01
        )

        if ok_tx and ok_rx:
            print("=== RESULTADO: CONEXIÓN BIDIRECCIONAL VERIFICADA EXITOSAMENTE (OK) ===")
            return 0
        else:
            print("=== RESULTADO: FALLO EN LA VERIFICACIÓN DE PAQUETES ===")
            return 1
    finally:
        if provider.server:
            provider.server.shutdown()
            provider.server.server_close()
        engine.stop()


def main():
    parser = argparse.ArgumentParser(description="Simulador del Motor C++ Magic-Sand-Unlimited (UDP/OSC)")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="IP destino/escucha (default: 127.0.0.1)")
    parser.add_argument("--tx-port", type=int, default=7000, help="Puerto hacia donde envía alturas (default: 7000)")
    parser.add_argument("--rx-port", type=int, default=7001, help="Puerto donde recibe comandos de render (default: 7001)")
    parser.add_argument("--autopilot", action="store_true", help="Mueve la arena automáticamente según los objetivos recibidos en :7001")
    parser.add_argument("--self-test", action="store_true", help="Ejecuta prueba automática de handshake bidireccional y termina")
    args = parser.parse_args()

    if args.self_test:
        raise SystemExit(run_self_test())

    engine = MockCppEngine(host=args.host, tx_port=args.tx_port, rx_port=args.rx_port)
    engine.start_rx_server()

    print("==========================================================================")
    print("  SIMULADOR DE MOTOR C++ (CRemoteGameController) ACTIVO")
    print(f"  - Enviando '/sandbox/grid' (30 Hz) -> {args.host}:{args.tx_port}")
    print(f"  - Escuchando '/render/...'         <- {args.host}:{args.rx_port}")
    print(f"  - Modo Autopiloto de Arena         : {'ACTIVADO' if args.autopilot else 'DESACTIVADO (Onda senoidal suave)'}")
    print("  Ejecuta en otra terminal: ./.venv/bin/python main.py --live")
    print("==========================================================================")

    dt = 1.0 / 30.0
    last_log = time.time()
    t0 = time.time()

    try:
        while True:
            now = time.time()
            if args.autopilot:
                engine.step_autopilot(dt)
            else:
                # Movimiento suave de prueba si no está en autopiloto
                import math
                elapsed = now - t0
                engine.heights = [
                    round(20.0 * math.sin(elapsed * 0.8), 1),
                    round(-20.0 * math.cos(elapsed * 0.6), 1),
                    round(15.0 * math.sin(elapsed * 0.5 + 1.0), 1),
                    round(-15.0 * math.cos(elapsed * 0.7 + 2.0), 1),
                ]

            engine.send_grid_frame()

            if now - last_log >= 1.0:
                connected = (now - engine.last_rx_time) < 2.5
                status = "CONECTADO" if connected else "ESPERANDO JUEGO (--live)"
                h_str = ", ".join(f"Q{i+1}:{h:+.1f}mm" for i, h in enumerate(engine.heights))
                print(
                    f"[{status}] TX:{engine.tx_packet_count} RX:{engine.rx_packet_count} | "
                    f"Niv:{engine.current_round} Pts:{engine.current_score} | "
                    f"Arena=[{h_str}] | Aviso='{engine.current_title}'"
                )
                last_log = now

            time.sleep(dt)
    except KeyboardInterrupt:
        print("\n[MockCppEngine] Cerrando simulador...")
    finally:
        engine.stop()


if __name__ == "__main__":
    main()
