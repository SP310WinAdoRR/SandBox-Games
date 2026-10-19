import argparse
import sys
import pygame

from src.data_provider import EmulatorDataProvider, OSCDataProvider
from src.bridge_client import MagicSandBridgeClient
from src.config_manager import ConfigManager
from src.quadrant_game import QuadrantTherapyGame

# Máscara oficial de SDL2 para posicionar una ventana centrada en el monitor N (0 = Principal, 1 = Secundario/Proyector)
SDL_WINDOWPOS_CENTERED_MASK = 0x2FFF0000


def windowpos_centered_display(display_index: int) -> tuple[int, int]:
    pos = SDL_WINDOWPOS_CENTERED_MASK | int(display_index)
    return (pos, pos)


def main():
    parser = argparse.ArgumentParser(description="SandBox Games - Motor Rehabilitation Suite (Dual Window)")
    parser.add_argument("--live", action="store_true", help="Modo producción con Kinect físico y Magic Sand (OSC)")
    parser.add_argument(
        "--show-proj",
        action="store_true",
        help="En modo --live, abrir también la ventana de proyección de Pygame (útil con mock_engine_osc.py)",
    )
    parser.add_argument("--patient", type=str, default="PACIENTE_01", help="ID del paciente para el registro clínico")
    parser.add_argument("--env", type=str, default="default.env", help="Archivo .env inicial desde la carpeta configs/")
    parser.add_argument("--insp-width", type=int, default=760, help="Ancho de la ventana de telemetría (Monitor Principal)")
    parser.add_argument("--insp-height", type=int, default=720, help="Alto de la ventana de telemetría (Monitor Principal)")
    parser.add_argument("--proj-width", type=int, default=960, help="Ancho de la ventana de proyección (si hay 1 solo monitor)")
    parser.add_argument("--proj-height", type=int, default=720, help="Alto de la ventana de proyección (si hay 1 solo monitor)")
    args = parser.parse_args()

    config_mgr = ConfigManager(configs_dir="configs")
    config_mgr.load_env(args.env)
    cfg = config_mgr.config

    is_emulator = not args.live
    open_proj_window = is_emulator or args.show_proj

    if is_emulator:
        print(f"[SandBox Games] Iniciando en MODO EMULADOR (Perfil: configs/{config_mgr.active_file})")
        print("  - Ventana 1 (Monitor Principal): Monitor de Inspección, Telemetría y Configuración (.env)")
        print("  - Ventana 2 (Segundo Monitor / Proyector): Proyección sobre la Caja de Arena")
        provider = EmulatorDataProvider(cols=cfg.INITIAL_COLS, rows=cfg.INITIAL_ROWS)
    else:
        print(f"[SandBox Games] Iniciando en MODO PRODUCCIÓN (Perfil: configs/{config_mgr.active_file})")
        print("  - Ventana 1 (Monitor Principal): Monitor de Inspección, Telemetría y Configuración (.env)")
        if open_proj_window:
            print("  - Ventana 2: Abierta manualmente (--show-proj)")
        else:
            print("  - Proyección delegada al Motor C++ (Magic-Sand-Unlimited encuadra dentro de su ROI calibrado vía :7001)")
        provider = OSCDataProvider(
            ip=cfg.OSC_HOST,
            port=cfg.OSC_RX_PORT,
            cols=cfg.INITIAL_COLS,
            rows=cfg.INITIAL_ROWS,
        )

    bridge = MagicSandBridgeClient(host=cfg.OSC_HOST, port=cfg.OSC_TX_PORT)

    pygame.init()
    pygame.font.init()

    desktop_sizes = pygame.display.get_desktop_sizes()
    num_monitors = len(desktop_sizes)
    print(f"[SandBox Games] Monitores detectados: {num_monitors} -> {desktop_sizes}")

    proj_window = None
    if num_monitors >= 2:
        # 1. Telemetría y Configuración en Monitor Principal (Display 0)
        insp_window = pygame.Window(
            "Magic Sandbox — Monitor de Inspección, Telemetría y Configuración",
            size=(args.insp_width, args.insp_height),
            position=windowpos_centered_display(0),
            resizable=True,
        )
        # 2. Proyección en Segundo Monitor / Proyector (Display 1) solo en Emulador o con --show-proj
        if open_proj_window:
            proj_w, proj_h = desktop_sizes[1]
            proj_window = pygame.Window(
                "Magic Sandbox — Proyección (Caja de Arena)",
                size=(proj_w, proj_h),
                position=windowpos_centered_display(1),
                borderless=True,
            )
    else:
        insp_window = pygame.Window(
            "Magic Sandbox — Monitor de Inspección, Telemetría y Configuración",
            size=(args.insp_width, args.insp_height),
            position=(20, 50),
            resizable=True,
        )
        if open_proj_window:
            proj_window = pygame.Window(
                "Magic Sandbox — Proyección (Caja de Arena)",
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
    active_window = proj_window if proj_window is not None else insp_window

    running = True
    while running:
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT or event.type == pygame.WINDOWCLOSE:
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

                # Si el clic ocurrió en la ventana de Telemetría/Configuración, verificar botones primero
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

        # Modificación de arena en modo emulador
        if is_emulator and (left_down or right_down) and game.cols > 0 and game.rows > 0:
            mx, my = mouse_pos
            target_idx = None

            if proj_window is not None and active_window == proj_window:
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

        # Renderizar Ventana 1 (Monitor Principal): Inspección, Telemetría y Configuración (.env)
        insp_surf = insp_window.get_surface()
        game.render_inspector(insp_surf, is_emulator=is_emulator)
        insp_window.flip()

        # Renderizar Ventana 2 (Segundo Monitor / Proyector) solo si está habilitada localmente
        if proj_window is not None:
            proj_surf = proj_window.get_surface()
            game.render(proj_surf, is_emulator=is_emulator)
            proj_window.flip()

    if game.metrics.session.rounds:
        game.metrics.export_session()

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
