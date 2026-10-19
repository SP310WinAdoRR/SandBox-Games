#!/usr/bin/env python3
"""
Arnés de Testeo y Emulación con Ratón (Fuera de la carpeta del juego).

Permite probar 'quadrant_game' en casa sin Kinect ni motor C++, abriendo:
  - Ventana 1 (Monitor Principal): Telemetría y Configuración (.env)
  - Ventana 2 (Segundo Monitor): Vista simulada del proyector interactiva con ratón
    (Clic Izquierdo = Poner arena +mm | Clic Derecho = Sacar arena -mm)
"""
from __future__ import annotations
import argparse
import os
import sys
import pygame

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
GAME_DIR = os.path.join(ROOT_DIR, "quadrant_game")
if GAME_DIR not in sys.path:
    sys.path.insert(0, GAME_DIR)

from src.data_provider import BaseDataProvider
from src.bridge_client import MagicSandBridgeClient
from src.config_manager import ConfigManager
from src.quadrant_game import QuadrantTherapyGame

SDL_WINDOWPOS_CENTERED_MASK = 0x2FFF0000


def windowpos_centered_display(display_index: int) -> tuple[int, int]:
    pos = SDL_WINDOWPOS_CENTERED_MASK | int(display_index)
    return (pos, pos)


class EmulatorDataProvider(BaseDataProvider):
    """
    Emulador interactivo de arena para testeo con ratón.
    """
    def __init__(self, cols: int = 2, rows: int = 2):
        self.cols = cols
        self.rows = rows
        self.heights = [0.0] * (cols * rows)

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


def main():
    parser = argparse.ArgumentParser(description="Emulador de Testeo con Ratón para Quadrant Game")
    parser.add_argument("--patient", type=str, default="TEST_EMULADOR", help="ID de sesión de prueba")
    parser.add_argument("--env", type=str, default="default.env", help="Archivo .env inicial")
    parser.add_argument("--insp-width", type=int, default=760)
    parser.add_argument("--insp-height", type=int, default=720)
    parser.add_argument("--proj-width", type=int, default=960)
    parser.add_argument("--proj-height", type=int, default=720)
    args = parser.parse_args()

    config_mgr = ConfigManager(configs_dir=os.path.join(GAME_DIR, "configs"))
    config_mgr.load_env(args.env)
    cfg = config_mgr.config

    provider = EmulatorDataProvider(cols=cfg.INITIAL_COLS, rows=cfg.INITIAL_ROWS)
    bridge = MagicSandBridgeClient(host=cfg.OSC_HOST, port=cfg.OSC_TX_PORT)

    pygame.init()
    pygame.font.init()

    desktop_sizes = pygame.display.get_desktop_sizes()
    if len(desktop_sizes) >= 2:
        insp_window = pygame.Window(
            "Magic Sandbox [EMULADOR] — Telemetría y Configuración",
            size=(args.insp_width, args.insp_height),
            position=windowpos_centered_display(0),
            resizable=True,
        )
        proj_w, proj_h = desktop_sizes[1]
        proj_window = pygame.Window(
            "Magic Sandbox [EMULADOR] — Proyección Simulada",
            size=(proj_w, proj_h),
            position=windowpos_centered_display(1),
            borderless=True,
        )
    else:
        insp_window = pygame.Window(
            "Magic Sandbox [EMULADOR] — Telemetría y Configuración",
            size=(args.insp_width, args.insp_height),
            position=(20, 50),
            resizable=True,
        )
        proj_window = pygame.Window(
            "Magic Sandbox [EMULADOR] — Proyección Simulada",
            size=(args.proj_width, args.proj_height),
            position=(20 + args.insp_width + 20, 50),
            resizable=True,
        )

    clock = pygame.time.Clock()
    game = QuadrantTherapyGame(
        data_provider=provider,
        bridge=bridge,
        config_mgr=config_mgr,
        patient_id=args.patient,
    )

    left_down = False
    right_down = False
    mouse_pos = (0, 0)
    active_window = proj_window

    running = True
    while running:
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type in (pygame.QUIT, pygame.WINDOWCLOSE):
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE and not game.saving_new_env and game.editing_field is None:
                    running = False
                else:
                    game.handle_input(event)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if getattr(event, "window", None) is not None:
                    active_window = event.window
                mouse_pos = event.pos

                if active_window == insp_window and event.button == 1:
                    if game.handle_inspector_click(event.pos[0], event.pos[1]):
                        continue

                if event.button == 1:
                    left_down = True
                elif event.button == 3:
                    right_down = True
            elif event.type == pygame.MOUSEBUTTONUP:
                mouse_pos = event.pos
                if event.button == 1:
                    left_down = False
                elif event.button == 3:
                    right_down = False
            elif event.type == pygame.MOUSEMOTION:
                if getattr(event, "window", None) is not None:
                    active_window = event.window
                mouse_pos = event.pos

        if (left_down or right_down) and game.cols > 0 and game.rows > 0:
            mx, my = mouse_pos
            target_idx = None

            if active_window == proj_window:
                pw, ph = proj_window.size
                if 0 <= mx < pw and 0 <= my < ph:
                    c = min(game.cols - 1, int(mx * game.cols / pw))
                    r = min(game.rows - 1, int(my * game.rows / ph))
                    target_idx = int(r * game.cols + c)
            elif active_window == insp_window and game.inspector_tab == game.TAB_MONITOR:
                iw, ih = insp_window.size
                grid_top = 76
                grid_h = int(ih * 0.30)
                grid_x = 14
                grid_w = iw - 28
                if grid_x <= mx < grid_x + grid_w and grid_top <= my < grid_top + grid_h:
                    c = min(game.cols - 1, int((mx - grid_x) * game.cols / grid_w))
                    r = min(game.rows - 1, int((my - grid_top) * game.rows / grid_h))
                    target_idx = int(r * game.cols + c)

            if target_idx is not None:
                delta_rate = game.config_mgr.config.EMULATOR_RATE_MM_S * dt
                if left_down:
                    provider.modify_cell(target_idx, +delta_rate)
                elif right_down:
                    provider.modify_cell(target_idx, -delta_rate)

        game.update()

        insp_surf = insp_window.get_surface()
        game.render_inspector(insp_surf, is_emulator=True)
        insp_window.flip()

        proj_surf = proj_window.get_surface()
        game.render(proj_surf, is_emulator=True)
        proj_window.flip()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
