import argparse
import sys
import pygame

from src.data_provider import EmulatorDataProvider, OSCDataProvider
from src.bridge_client import MagicSandBridgeClient
from src.quadrant_game import QuadrantTherapyGame

# Máscara oficial de SDL2 para posicionar una ventana centrada en el monitor N (0 = Principal, 1 = Secundario/Proyector)
SDL_WINDOWPOS_CENTERED_MASK = 0x2FFF0000


def windowpos_centered_display(display_index: int) -> tuple[int, int]:
    pos = SDL_WINDOWPOS_CENTERED_MASK | int(display_index)
    return (pos, pos)


def main():
    parser = argparse.ArgumentParser(description="SandBox Games - Motor Rehabilitation Suite (Dual Window)")
    parser.add_argument("--live", action="store_true", help="Modo producción con Kinect físico y Magic Sand (OSC)")
    parser.add_argument("--patient", type=str, default="PACIENTE_01", help="ID del paciente para el registro clínico")
    parser.add_argument("--cols", type=int, default=2, help="Columnas de la cuadrícula")
    parser.add_argument("--rows", type=int, default=2, help="Filas de la cuadrícula")
    parser.add_argument("--insp-width", type=int, default=720, help="Ancho de la ventana de telemetría (Monitor Principal)")
    parser.add_argument("--insp-height", type=int, default=720, help="Alto de la ventana de telemetría (Monitor Principal)")
    parser.add_argument("--proj-width", type=int, default=960, help="Ancho de la ventana de proyección (si hay 1 solo monitor)")
    parser.add_argument("--proj-height", type=int, default=720, help="Alto de la ventana de proyección (si hay 1 solo monitor)")
    args = parser.parse_args()

    is_emulator = not args.live
    if is_emulator:
        print("[SandBox Games] Iniciando en MODO EMULADOR con 2 ventanas independientes:")
        print("  - Ventana 1 (Monitor Principal): Monitor de Inspección y Telemetría Clínica")
        print("  - Ventana 2 (Segundo Monitor / Proyector): Proyección sobre la Caja de Arena")
        print("  - Clic Izquierdo sobre cuadrante: Poner / acumular arena (Rojo)")
        print("  - Clic Derecho sobre cuadrante: Sacar / excavar arena (Verde)")
        print("  - Tecla [R]: Aplanar arena a nivel 0 mm  |  [ESPACIO]: Iniciar / Saltar preparación")
        provider = EmulatorDataProvider(cols=args.cols, rows=args.rows)
    else:
        print("[SandBox Games] Iniciando en MODO PRODUCCIÓN con 2 ventanas independientes:")
        print("  - Escuchando Kinect en UDP 127.0.0.1:7000 | Enviando proyección a 127.0.0.1:7001")
        provider = OSCDataProvider(cols=args.cols, rows=args.rows)

    bridge = MagicSandBridgeClient()

    pygame.init()
    pygame.font.init()

    desktop_sizes = pygame.display.get_desktop_sizes()
    num_monitors = len(desktop_sizes)
    print(f"[SandBox Games] Monitores detectados: {num_monitors} -> {desktop_sizes}")

    if num_monitors >= 2:
        # Configuración Multi-Monitor (Laboratorio / Proyector conectado):
        # 1. Telemetría se abre centrada en el Monitor Principal (Display 0)
        insp_window = pygame.Window(
            "Magic Sandbox — Monitor de Inspección y Telemetría",
            size=(args.insp_width, args.insp_height),
            position=windowpos_centered_display(0),
            resizable=True,
        )
        # 2. Proyección se abre automáticamente a pantalla completa sin bordes en el Segundo Monitor (Display 1)
        proj_w, proj_h = desktop_sizes[1]
        proj_window = pygame.Window(
            "Magic Sandbox — Proyección (Caja de Arena)",
            size=(proj_w, proj_h),
            position=windowpos_centered_display(1),
            borderless=True,
        )
    else:
        # Configuración de 1 solo monitor (Pruebas en casa sin proyector conectado):
        # Ambas ventanas independientes se abren lado a lado en el monitor principal
        insp_window = pygame.Window(
            "Magic Sandbox — Monitor de Inspección y Telemetría",
            size=(args.insp_width, args.insp_height),
            position=(30, 60),
            resizable=True,
        )
        proj_window = pygame.Window(
            "Magic Sandbox — Proyección (Caja de Arena)",
            size=(args.proj_width, args.proj_height),
            position=(30 + args.insp_width + 20, 60),
            resizable=True,
        )

    clock = pygame.time.Clock()
    game = QuadrantTherapyGame(data_provider=provider, bridge=bridge, patient_id=args.patient)
    game.cols = args.cols
    game.rows = args.rows

    left_down = False
    right_down = False
    mouse_pos = (0, 0)
    active_window = proj_window

    running = True
    while running:
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT or event.type == pygame.WINDOWCLOSE:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                else:
                    game.handle_input(event)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if getattr(event, "window", None) is not None:
                    active_window = event.window
                mouse_pos = event.pos
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

        # En modo emulador se puede interactuar haciendo clic tanto en la ventana de Proyección
        # como en los cuadrantes de la ventana de Telemetría
        if is_emulator and (left_down or right_down) and game.cols > 0 and game.rows > 0:
            mx, my = mouse_pos
            target_idx = None

            if active_window == proj_window:
                pw, ph = proj_window.size
                if 0 <= mx < pw and 0 <= my < ph:
                    c = min(game.cols - 1, int(mx * game.cols / pw))
                    r = min(game.rows - 1, int(my * game.rows / ph))
                    target_idx = int(r * game.cols + c)
            elif active_window == insp_window:
                iw, ih = insp_window.size
                grid_top = 88
                grid_h = int(ih * 0.30)
                grid_x = 14
                grid_w = iw - 28
                if grid_x <= mx < grid_x + grid_w and grid_top <= my < grid_top + grid_h:
                    c = min(game.cols - 1, int((mx - grid_x) * game.cols / grid_w))
                    r = min(game.rows - 1, int((my - grid_top) * game.rows / grid_h))
                    target_idx = int(r * game.cols + c)

            if target_idx is not None:
                delta_rate = 55.0 * dt
                if left_down:
                    provider.modify_cell(target_idx, +delta_rate)
                elif right_down:
                    provider.modify_cell(target_idx, -delta_rate)

        game.update()

        # Renderizar Ventana 1 (Monitor Principal): Inspección y Telemetría Clínica
        insp_surf = insp_window.get_surface()
        game.render_inspector(insp_surf, is_emulator=is_emulator)
        insp_window.flip()

        # Renderizar Ventana 2 (Segundo Monitor / Proyector): Proyección sobre la Caja de Arena
        proj_surf = proj_window.get_surface()
        game.render(proj_surf, is_emulator=is_emulator)
        proj_window.flip()

    if game.metrics.session.rounds:
        game.metrics.export_session()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
