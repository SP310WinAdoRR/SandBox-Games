#!/usr/bin/env python3
"""
Módulo de pruebas y emulación interactiva mediante ratón.

Permite ejecutar los juegos desacoplados del hardware físico mediante la inyección
de 'EmulatorSandInputAdapter' en lugar de la conexión OSC.
"""
from __future__ import annotations
import argparse
import os
import sys
import pygame

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.contracts import ISandInputPort
from core.network import OSCProjectionOutputAdapter
from core.runtime.pygame_runner import (
    list_available_games,
    load_game_plugin,
    windowpos_centered_display,
)


class EmulatorSandInputAdapter(ISandInputPort):
    """
    Implementación de 'ISandInputPort' controlada por el ratón para pruebas locales y desarrollo.
    """
    def __init__(self, cols: int = 2, rows: int = 2):
        self.cols = cols
        self.rows = rows
        self.heights = [0.0] * (cols * rows)

    def set_grid_size(self, cols: int, rows: int) -> None:
        self.cols = cols
        self.rows = rows
        self.heights = [0.0] * (cols * rows)

    def get_heights(self) -> list[float]:
        return list(self.heights)

    def modify_cell(self, index: int, delta_mm: float) -> None:
        if 0 <= index < len(self.heights):
            self.heights[index] = max(-80.0, min(120.0, self.heights[index] + delta_mm))

    def reset(self) -> None:
        self.heights = [0.0] * len(self.heights)


def main() -> None:
    games_root = os.path.join(ROOT_DIR, "games")
    available = list_available_games(games_root)

    parser = argparse.ArgumentParser(description="Emulador interactivo de pruebas mediante ratón")
    parser.add_argument("--game", type=str, default="quadrant_game", choices=available if available else ["quadrant_game"])
    parser.add_argument("--patient", type=str, default="TEST_EMULADOR")
    parser.add_argument("--env", type=str, default="default.env")
    parser.add_argument("--insp-width", type=int, default=760)
    parser.add_argument("--insp-height", type=int, default=720)
    parser.add_argument("--proj-width", type=int, default=960)
    parser.add_argument("--proj-height", type=int, default=720)
    args = parser.parse_args()

    # Inyección de dependencias para emulación local
    input_port = EmulatorSandInputAdapter()
    output_port = OSCProjectionOutputAdapter()

    game = load_game_plugin(
        game_name=args.game,
        input_port=input_port,
        output_port=output_port,
        patient_id=args.patient,
        env_file=args.env,
    )

    pygame.init()
    pygame.font.init()

    desktop_sizes = pygame.display.get_desktop_sizes()
    if len(desktop_sizes) >= 2:
        insp_window = pygame.Window(
            f"[EMULADOR] {game.title}",
            size=(args.insp_width, args.insp_height),
            position=windowpos_centered_display(0),
            resizable=True,
        )
        proj_w, proj_h = desktop_sizes[1]
        proj_window = pygame.Window(
            f"[EMULADOR] Proyección Simulada — {args.game}",
            size=(proj_w, proj_h),
            position=windowpos_centered_display(1),
            borderless=True,
        )
    else:
        insp_window = pygame.Window(
            f"[EMULADOR] {game.title}",
            size=(args.insp_width, args.insp_height),
            position=(20, 50),
            resizable=True,
        )
        proj_window = pygame.Window(
            f"[EMULADOR] Proyección Simulada — {args.game}",
            size=(args.proj_width, args.proj_height),
            position=(20 + args.insp_width + 20, 50),
            resizable=True,
        )

    clock = pygame.time.Clock()
    left_down = False
    right_down = False
    mouse_pos = (0, 0)
    active_window = proj_window

    running = True
    try:
        while running:
            dt = clock.tick(60) / 1000.0

            for event in pygame.event.get():
                if event.type in (pygame.QUIT, pygame.WINDOWCLOSE):
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE and game.can_exit_on_escape():
                        running = False
                    else:
                        game.handle_key_event(event)
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

            cols, rows = game.grid_shape
            if (left_down or right_down) and cols > 0 and rows > 0:
                mx, my = mouse_pos
                target_idx = None

                if active_window == proj_window:
                    pw, ph = proj_window.size
                    if 0 <= mx < pw and 0 <= my < ph:
                        c = min(cols - 1, int(mx * cols / pw))
                        r = min(rows - 1, int(my * rows / ph))
                        target_idx = int(r * cols + c)

                if target_idx is not None:
                    delta_mm = 55.0 * dt
                    if left_down:
                        input_port.modify_cell(target_idx, +delta_mm)
                    elif right_down:
                        input_port.modify_cell(target_idx, -delta_mm)

            game.update(dt)

            insp_surf = insp_window.get_surface()
            game.render_inspector(insp_surf, is_emulator=True)
            insp_window.flip()

            proj_surf = proj_window.get_surface()
            game.render_projection(proj_surf)
            proj_window.flip()
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
