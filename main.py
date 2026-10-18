import argparse
import sys
import pygame

from src.data_provider import EmulatorDataProvider, OSCDataProvider
from src.bridge_client import MagicSandBridgeClient
from src.quadrant_game import QuadrantTherapyGame


def main():
    parser = argparse.ArgumentParser(description="SandBox Games - Motor Rehabilitation Suite")
    parser.add_argument("--live", action="store_true", help="Modo producción con Kinect físico y Magic Sand (OSC)")
    parser.add_argument("--patient", type=str, default="PACIENTE_01", help="ID del paciente para el registro clínico")
    parser.add_argument("--cols", type=int, default=2, help="Columnas de la cuadrícula")
    parser.add_argument("--rows", type=int, default=2, help="Filas de la cuadrícula")
    parser.add_argument("--width", type=int, default=1280, help="Ancho de la ventana")
    parser.add_argument("--height", type=int, default=720, help="Alto de la ventana")
    args = parser.parse_args()

    # 1. Configurar proveedor de datos
    is_emulator = not args.live
    if is_emulator:
        print("[SandBox Games] Iniciando en MODO EMULADOR (Casa / Desarrollo)")
        print("  - Clic Izquierdo sobre cuadrante: Acumular arena")
        print("  - Clic Derecho sobre cuadrante: Excavar arena")
        print("  - Tecla [R]: Aplanar arena a nivel 0 mm")
        provider = EmulatorDataProvider(cols=args.cols, rows=args.rows)
    else:
        print("[SandBox Games] Iniciando en MODO PRODUCCIÓN (Laboratorio)")
        print("  - Escuchando Kinect en UDP 127.0.0.1:7000")
        provider = OSCDataProvider(cols=args.cols, rows=args.rows)

    bridge = MagicSandBridgeClient()

    # 2. Inicializar Pygame
    pygame.init()
    pygame.font.init()
    screen = pygame.display.set_mode((args.width, args.height), pygame.RESIZABLE)
    pygame.display.set_caption("Magic Sandbox - Rehabilitación Motriz (Mecánica de Cuadrantes)")
    clock = pygame.time.Clock()

    game = QuadrantTherapyGame(data_provider=provider, bridge=bridge, patient_id=args.patient)
    game.cols = args.cols
    game.rows = args.rows

    running = True
    while running:
        dt = clock.tick(60) / 1000.0

        # Manejo de eventos
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                else:
                    game.handle_input(event)

        # Si estamos en modo emulador, soportar arrastre/mantenimiento del clic
        if is_emulator:
            mouse_buttons = pygame.mouse.get_pressed()
            if mouse_buttons[0] or mouse_buttons[2]:
                mx, my = pygame.mouse.get_pos()
                hud_h = int(screen.get_height() * 0.14)
                grid_top = hud_h + 15
                grid_margin = 25
                grid_w = screen.get_width() - (grid_margin * 2)
                grid_h = screen.get_height() - grid_top - 50

                cell_w = grid_w // game.cols
                cell_h = grid_h // game.rows

                if grid_margin <= mx < grid_margin + grid_w and grid_top <= my < grid_top + grid_h:
                    c = (mx - grid_margin) // cell_w
                    r = (my - grid_top) // cell_h
                    idx = int(r * game.cols + c)

                    # Tasa de modificación en mm
                    delta_rate = 55.0 * dt  # 55 mm/s
                    if mouse_buttons[0]:
                        provider.modify_cell(idx, +delta_rate)
                    elif mouse_buttons[2]:
                        provider.modify_cell(idx, -delta_rate)

        # Actualizar lógica y renderizar
        game.update()
        game.render(screen, is_emulator=is_emulator)
        pygame.display.flip()

    # Guardar métricas finales si hubo rondas
    if game.metrics.session.rounds:
        game.metrics.export_session()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
