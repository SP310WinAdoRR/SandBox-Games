"""
Módulo de ejecución y gestión de ventanas en Pygame.

Desacopla la inicialización de SDL2/Pygame, el bucle de eventos y
las ventanas del sistema operativo respecto de la lógica interna de cada juego.
"""
from __future__ import annotations
import importlib
import os
import pygame
from core.contracts import ISandInputPort, IProjectionOutputPort, ISandboxGame

SDL_WINDOWPOS_CENTERED_MASK = 0x2FFF0000


def windowpos_centered_display(display_index: int) -> tuple[int, int]:
    pos = SDL_WINDOWPOS_CENTERED_MASK | int(display_index)
    return (pos, pos)


def list_available_games(games_root: str) -> list[str]:
    if not os.path.isdir(games_root):
        return []
    result = []
    for entry in sorted(os.listdir(games_root)):
        full = os.path.join(games_root, entry)
        if os.path.isdir(full) and os.path.isfile(os.path.join(full, "__init__.py")):
            result.append(entry)
    return result


def load_game_plugin(
    game_name: str,
    input_port: ISandInputPort,
    output_port: IProjectionOutputPort,
    patient_id: str = "PACIENTE_01",
    env_file: str = "default.env",
) -> ISandboxGame:
    """
    Importa dinámicamente 'games.<game_name>' e invoca su fábrica 'create_game(...)'
    inyectándole los puertos de entrada y salida.
    """
    module = importlib.import_module(f"games.{game_name}")
    if not hasattr(module, "create_game"):
        raise RuntimeError(
            f"El paquete 'games.{game_name}' debe definir una función fábrica "
            f"'create_game(input_port, output_port, patient_id, env_file) -> ISandboxGame'."
        )
    return module.create_game(
        input_port=input_port,
        output_port=output_port,
        patient_id=patient_id,
        env_file=env_file,
    )


class PygameApplicationRunner:
    """
    Orquesta el ciclo de vida de la aplicación en Pygame, administrando eventos
    y superficies de renderizado para instancias de 'ISandboxGame'.
    """
    def __init__(
        self,
        game: ISandboxGame,
        insp_width: int = 760,
        insp_height: int = 720,
        fps: int = 60,
    ):
        self.game = game
        self.insp_width = insp_width
        self.insp_height = insp_height
        self.fps = fps

    def run(self) -> None:
        pygame.init()
        pygame.font.init()

        window = pygame.Window(
            f"Magic Sandbox — {self.game.title}",
            size=(self.insp_width, self.insp_height),
            position=windowpos_centered_display(0),
            resizable=True,
        )

        clock = pygame.time.Clock()
        running = True

        try:
            while running:
                dt = clock.tick(self.fps) / 1000.0

                for event in pygame.event.get():
                    if event.type in (pygame.QUIT, pygame.WINDOWCLOSE):
                        running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE and self.game.can_exit_on_escape():
                            running = False
                        else:
                            self.game.handle_key_event(event)
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        self.game.handle_inspector_click(event.pos[0], event.pos[1])

                # Actualizar el estado lógico del juego
                self.game.update(dt)

                # Renderizar la interfaz sobre la superficie activa
                surf = window.get_surface()
                self.game.render_inspector(surf, is_emulator=False)
                window.flip()
        finally:
            self.game.shutdown()
            pygame.quit()
