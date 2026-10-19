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

    is_emulator = not args.live
    if is_emulator:
        print("[SandBox Games] Iniciando en MODO EMULADOR (Casa / Desarrollo)")
        print("  - Clic Izquierdo sobre cuadrante: Acumular arena")
        print("  - Clic Derecho sobre cuadrante: Excavar arena")
        print("  - Tecla [R]: Aplanar arena a nivel 0 mm")
        print("  - Tecla [ESPACIO]: Iniciar / Saltar preparación")
        provider = EmulatorDataProvider(cols=args.cols, rows=args.rows)
    else:
        print("[SandBox Games] Iniciando en MODO PRODUCCIÓN (Laboratorio)")
        print("  - Escuchando Kinect en UDP 127.0.0.1:7000")
        provider = OSCDataProvider(cols=args.cols, rows=args.rows)

    bridge = MagicSandBridgeClient()

    pygame.init()
    pygame.font.init()
    screen = pygame.display.set_mode((args.width, args.height), pygame.RESIZABLE)
    pygame.display.set_caption("Magic Sandbox - Rehabilitación Motriz")
    clock = pygame.time.Clock()

    game = QuadrantTherapyGame(data_provider=provider, bridge=bridge, patient_id=args.patient)
    game.cols = args.cols
    game.rows = args.rows

    running = True
    while running:
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                else:
                    game.handle_input(event)

        # Interacción de ratón sobre el 100% de la pantalla (cuadrícula sin márgenes)
        if is_emulator:
            mouse_buttons = pygame.mouse.get_pressed()
            if mouse_buttons[0] or mouse_buttons[2]:
                mx, my = pygame.mouse.get_pos()
                w, h = screen.get_size()
                if 0 <= mx < w and 0 <= my < h and game.cols > 0 and game.rows > 0:
                    c = min(game.cols - 1, int(mx * game.cols / w))
                    r = min(game.rows - 1, int(my * game.rows / h))
                    idx = int(r * game.cols + c)

                    delta_rate = 55.0 * dt  # 55 mm/s
                    if mouse_buttons[0]:
                        provider.modify_cell(idx, +delta_rate)
                    elif mouse_buttons[2]:
                        provider.modify_cell(idx, -delta_rate)

        game.update()
        game.render(screen, is_emulator=is_emulator)
        pygame.display.flip()

    if game.metrics.session.rounds:
        game.metrics.export_session()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
