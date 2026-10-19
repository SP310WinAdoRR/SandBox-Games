import argparse
import os
import sys
import pygame

GAME_DIR = os.path.dirname(os.path.abspath(__file__))
if GAME_DIR not in sys.path:
    sys.path.insert(0, GAME_DIR)

from src.data_provider import OSCDataProvider
from src.bridge_client import MagicSandBridgeClient
from src.config_manager import ConfigManager
from src.quadrant_game import QuadrantTherapyGame

SDL_WINDOWPOS_CENTERED_MASK = 0x2FFF0000


def windowpos_centered_display(display_index: int) -> tuple[int, int]:
    pos = SDL_WINDOWPOS_CENTERED_MASK | int(display_index)
    return (pos, pos)


def main():
    parser = argparse.ArgumentParser(description="Juego de Rehabilitación por Cuadrantes (Producción)")
    parser.add_argument("--patient", type=str, default="PACIENTE_01", help="ID del paciente para el registro clínico")
    parser.add_argument("--env", type=str, default="default.env", help="Archivo .env inicial desde la carpeta configs/")
    parser.add_argument("--width", type=int, default=760, help="Ancho de la ventana de telemetría (Monitor Principal)")
    parser.add_argument("--height", type=int, default=720, help="Alto de la ventana de telemetría (Monitor Principal)")
    args = parser.parse_args()

    config_mgr = ConfigManager(configs_dir=os.path.join(GAME_DIR, "configs"))
    config_mgr.load_env(args.env)
    cfg = config_mgr.config

    provider = OSCDataProvider(
        ip=cfg.OSC_HOST,
        port=cfg.OSC_RX_PORT,
        cols=cfg.INITIAL_COLS,
        rows=cfg.INITIAL_ROWS,
    )
    bridge = MagicSandBridgeClient(host=cfg.OSC_HOST, port=cfg.OSC_TX_PORT)

    pygame.init()
    pygame.font.init()

    window = pygame.Window(
        "Magic Sandbox — Consola Clínica, Telemetría y Configuración",
        size=(args.width, args.height),
        position=windowpos_centered_display(0),
        resizable=True,
    )

    clock = pygame.time.Clock()
    game = QuadrantTherapyGame(
        data_provider=provider,
        bridge=bridge,
        config_mgr=config_mgr,
        patient_id=args.patient,
    )

    running = True
    while running:
        clock.tick(60)

        for event in pygame.event.get():
            if event.type in (pygame.QUIT, pygame.WINDOWCLOSE):
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE and not game.saving_new_env and game.editing_field is None:
                    running = False
                else:
                    game.handle_input(event)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                game.handle_inspector_click(event.pos[0], event.pos[1])

        game.update()

        surf = window.get_surface()
        game.render_inspector(surf, is_emulator=False)
        window.flip()

    if game.metrics.session.rounds:
        game.metrics.export_session()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
