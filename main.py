#!/usr/bin/env python3
"""
Punto de Entrada Principal (Composition Root).

Responsabilidades:
  1. Instanciar los adaptadores de transmisión y recepción de red ('core.network').
  2. Cargar el juego seleccionado desde 'games/<game_name>' inyectando los puertos
     'ISandInputPort' e 'IProjectionOutputPort'.
  3. Iniciar el ciclo de vida de la aplicación mediante 'PygameApplicationRunner' ('core.runtime').
"""
from __future__ import annotations
import argparse
import os
import sys

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.network import OSCSandInputAdapter, OSCProjectionOutputAdapter
from core.runtime.pygame_runner import (
    PygameApplicationRunner,
    list_available_games,
    load_game_plugin,
)


def main() -> None:
    games_root = os.path.join(ROOT_DIR, "games")
    available = list_available_games(games_root)

    parser = argparse.ArgumentParser(description="SandBox Games — Lanzador modular con inyección de dependencias")
    parser.add_argument(
        "--game",
        type=str,
        default="quadrant_game",
        choices=available if available else ["quadrant_game"],
        help="Nombre del paquete de juego dentro de la carpeta games/",
    )
    parser.add_argument("--patient", type=str, default="PACIENTE_01", help="Identificador del paciente para el registro clínico")
    parser.add_argument("--env", type=str, default="default.env", help="Archivo .env inicial del juego")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Dirección IP del motor Magic Sand (C++)")
    parser.add_argument("--rx-port", type=int, default=7000, help="Puerto UDP de recepción de datos de altura (por defecto: 7000)")
    parser.add_argument("--tx-port", type=int, default=7001, help="Puerto UDP de transmisión de comandos gráficos (por defecto: 7001)")
    parser.add_argument("--width", type=int, default=760, help="Ancho de la ventana de consola/telemetría")
    parser.add_argument("--height", type=int, default=720, help="Alto de la ventana de consola/telemetría")
    args = parser.parse_args()

    # 1. Crear puertos de recepción (RX) y transmisión (TX)
    input_port = OSCSandInputAdapter(ip=args.host, port=args.rx_port)
    output_port = OSCProjectionOutputAdapter(host=args.host, port=args.tx_port)

    try:
        # 2. Cargar e instanciar el juego seleccionado
        game = load_game_plugin(
            game_name=args.game,
            input_port=input_port,
            output_port=output_port,
            patient_id=args.patient,
            env_file=args.env,
        )

        # 3. Iniciar el runner de la aplicación
        runner = PygameApplicationRunner(
            game=game,
            insp_width=args.width,
            insp_height=args.height,
        )
        runner.run()
    finally:
        input_port.close()


if __name__ == "__main__":
    main()
