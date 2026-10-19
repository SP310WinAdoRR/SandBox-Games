import math
import random
import time
import pygame

from .data_provider import BaseDataProvider
from .bridge_client import MagicSandBridgeClient
from .metrics import RoundMetric, TherapyMetricsManager
from .config_manager import (
    ConfigManager,
    EASY_CATEGORIES_META,
    ADVANCED_FIELDS_META,
)


def _lerp_color(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


class QuadrantTherapyGame:
    """
    Videojuego de modulación de alturas por cuadrantes para rehabilitación motriz.
    Integra gestor de configuraciones (.env) con Modo Fácil (categorías) y
    Modo Avanzado (edición numérica completa) desde la ventana de Telemetría.
    """

    STATE_WELCOME = "WELCOME"
    STATE_PREPARE_FLAT = "PREPARE_FLAT"
    STATE_ROUND_ACTIVE = "ROUND_ACTIVE"
    STATE_ROUND_WON = "ROUND_WON"
    STATE_GAME_OVER = "GAME_OVER"

    # Pestañas de la ventana de Telemetría / Inspección
    TAB_MONITOR = "MONITOR"
    TAB_CONFIG = "CONFIG"

    # Sub-modos dentro de la pestaña de Configuración
    CFG_MODE_EASY = "EASY"
    CFG_MODE_ADVANCED = "ADVANCED"

    def __init__(
        self,
        data_provider: BaseDataProvider,
        bridge: MagicSandBridgeClient = None,
        config_mgr: ConfigManager = None,
        patient_id: str = "PACIENTE_01",
    ):
        self.provider = data_provider
        self.bridge = bridge or MagicSandBridgeClient()
        self.config_mgr = config_mgr or ConfigManager()
        self.metrics = TherapyMetricsManager(patient_id=patient_id)

        self.cols = self.config_mgr.config.INITIAL_COLS
        self.rows = self.config_mgr.config.INITIAL_ROWS
        self.provider.set_grid_size(self.cols, self.rows)

        self.state = self.STATE_WELCOME
        self.round_number = 0
        self.score = 0
        self.target_quadrant = 0
        self.target_action = "ELEVATE"   # "ELEVATE" (Rojo: poner arena) o "DIG" (Verde: sacar arena)
        self.target_threshold = 32.0     # mm
        self.time_limit = 15.0           # segundos
        self.time_left = 15.0
        self.round_start_time = 0.0
        self.round_win_time = 0.0
        self.last_update_time = time.time()

        self.palette = {
            "cyan_base": (0, 184, 220),       # Azul cian para cuadrantes neutros
            "target_elevate": (255, 30, 39),  # Rojo vivo -> Poner arena
            "target_dig": (0, 205, 85),       # Verde vivo -> Sacar arena
            "target_success": (255, 230, 90), # Destello dorado/blanco al cumplir la meta
            "grid_line": (0, 0, 0),           # Líneas divisorias negras sólidas
        }

        # Estado interactivo de la interfaz del Monitor / Configuración
        self.inspector_tab = self.TAB_MONITOR
        self.config_mode = self.CFG_MODE_EASY
        self.ui_hitboxes: list[tuple[pygame.Rect, str, object]] = []
        self.editing_field: str | None = None
        self.editing_buffer: str = ""
        self.saving_new_env: bool = False
        self.new_env_buffer: str = "perfil_personalizado"
        self.status_toast_msg: str = ""
        self.status_toast_until: float = 0.0

    def show_toast(self, msg: str, duration: float = 3.0):
        self.status_toast_msg = msg
        self.status_toast_until = time.time() + duration

    def apply_live_config(self):
        """Aplica inmediatamente los cambios de configuración al estado actual."""
        cfg = self.config_mgr.config
        if self.state == self.STATE_WELCOME:
            if (cfg.INITIAL_COLS, cfg.INITIAL_ROWS) != (self.cols, self.rows):
                self.cols = cfg.INITIAL_COLS
                self.rows = cfg.INITIAL_ROWS
                self.provider.set_grid_size(self.cols, self.rows)
                self.bridge.send_grid_setup(self.cols, self.rows)

    def start_new_game(self):
        cfg = self.config_mgr.config
        self.round_number = 0
        self.score = 0
        self.cols = cfg.INITIAL_COLS
        self.rows = cfg.INITIAL_ROWS
        self.provider.set_grid_size(self.cols, self.rows)
        self.next_round()

    def next_round(self):
        cfg = self.config_mgr.config
        self.round_number += 1

        # Escalado de cuadrícula según MAX_GRID_STAGE e INITIAL_COLS/ROWS
        if cfg.MAX_GRID_STAGE <= 1 or self.round_number <= 4:
            new_cols, new_rows = cfg.INITIAL_COLS, cfg.INITIAL_ROWS
        elif cfg.MAX_GRID_STAGE == 2 or self.round_number <= 8:
            new_cols, new_rows = max(cfg.INITIAL_COLS, 4), max(cfg.INITIAL_ROWS, 2)
        else:
            new_cols, new_rows = max(cfg.INITIAL_COLS, 4), max(cfg.INITIAL_ROWS, 4)

        if (new_cols, new_rows) != (self.cols, self.rows):
            self.cols, self.rows = new_cols, new_rows
            self.provider.set_grid_size(self.cols, self.rows)

        num_cells = self.cols * self.rows

        # Selección de acción según ACTION_CATEGORY
        if cfg.ACTION_CATEGORY == "PONER":
            self.target_action = "ELEVATE"
        elif cfg.ACTION_CATEGORY == "SACAR":
            self.target_action = "DIG"
        else:
            if self.round_number <= 2:
                self.target_action = "ELEVATE"
            else:
                self.target_action = random.choice(["ELEVATE", "DIG"])

        # Umbral de altura y tiempo límite gobernados por la configuración (.env)
        extra_mm = (self.round_number - 1) * cfg.THRESHOLD_STEP_PER_ROUND_MM
        if self.target_action == "ELEVATE":
            self.target_threshold = cfg.ELEVATE_THRESHOLD_MM + extra_mm
        else:
            self.target_threshold = cfg.DIG_THRESHOLD_MM - extra_mm

        self.time_limit = max(
            cfg.MIN_TIME_LIMIT_SEC,
            cfg.BASE_TIME_LIMIT_SEC - ((self.round_number - 1) * cfg.TIME_DECAY_PER_ROUND),
        )

        self.target_quadrant = random.randint(0, num_cells - 1)
        self.state = self.STATE_PREPARE_FLAT

        self.bridge.send_grid_setup(self.cols, self.rows)
        self.bridge.send_hud_stats(self.round_number, self.score)
        self.bridge.send_hud_title("NIVELA LA ARENA")

    def _start_active_phase(self):
        self.state = self.STATE_ROUND_ACTIVE
        self.time_left = self.time_limit
        self.round_start_time = time.time()
        self.bridge.send_hud_title("")
        self.bridge.send_hud_stats(self.round_number, self.score)

    def _get_target_progress(self, current_h: float) -> float:
        if abs(self.target_threshold) < 1e-5:
            return 1.0
        return max(0.0, min(1.0, current_h / self.target_threshold))

    def update(self):
        now = time.time()
        dt = now - self.last_update_time
        self.last_update_time = now
        cfg = self.config_mgr.config

        heights = self.provider.get_heights()
        if not heights or self.target_quadrant >= len(heights):
            return

        current_h = heights[self.target_quadrant]

        if self.state == self.STATE_PREPARE_FLAT:
            is_flat = all(abs(h) < cfg.FLAT_TOLERANCE_MM for h in heights)
            if is_flat:
                self._start_active_phase()

        elif self.state == self.STATE_ROUND_ACTIVE:
            self.time_left -= dt
            timer_ratio = max(0.0, self.time_left / self.time_limit)
            self.bridge.send_hud_timer(timer_ratio, alpha=cfg.PIE_TIMER_ALPHA)

            progress = self._get_target_progress(current_h)
            if progress >= 1.0:
                time_taken = self.time_limit - self.time_left
                points = int(100 + (self.time_left * 20))
                self.score += points
                self.round_win_time = now
                self.state = self.STATE_ROUND_WON

                self.metrics.record_round(RoundMetric(
                    round_number=self.round_number,
                    target_quadrant=self.target_quadrant,
                    target_action=self.target_action,
                    target_threshold_mm=self.target_threshold,
                    final_height_mm=current_h,
                    time_limit_sec=self.time_limit,
                    time_taken_sec=time_taken,
                    success=True,
                    score_awarded=points
                ))
                self.bridge.send_hud_stats(self.round_number, self.score)
                return

            if self.time_left <= 0:
                self.state = self.STATE_GAME_OVER
                self.metrics.record_round(RoundMetric(
                    round_number=self.round_number,
                    target_quadrant=self.target_quadrant,
                    target_action=self.target_action,
                    target_threshold_mm=self.target_threshold,
                    final_height_mm=current_h,
                    time_limit_sec=self.time_limit,
                    time_taken_sec=self.time_limit,
                    success=False,
                    score_awarded=0
                ))
                self.metrics.export_session()
                self.bridge.send_hud_timer(0.0)
                self.bridge.send_hud_title(f"FIN DEL JUEGO - {self.score} PTS")

        elif self.state == self.STATE_ROUND_WON:
            if now - self.round_win_time > cfg.WIN_PAUSE_SEC:
                self.next_round()

        self._sync_cells_to_bridge(heights, now)

    def _sync_cells_to_bridge(self, heights: list[float], now: float):
        cfg = self.config_mgr.config
        num_cells = self.cols * self.rows
        for idx in range(num_cells):
            curr_h = heights[idx] if idx < len(heights) else 0.0
            is_target = (self.state in (self.STATE_ROUND_ACTIVE, self.STATE_ROUND_WON)) and (idx == self.target_quadrant)

            if self.state == self.STATE_ROUND_WON and is_target:
                elapsed_win = min(1.0, (now - self.round_win_time) / max(0.2, cfg.WIN_PAUSE_SEC))
                flash_col = _lerp_color(self.palette["target_success"], self.palette["cyan_base"], elapsed_win)
                self.bridge.send_cell_state(idx, flash_col[0], flash_col[1], flash_col[2], 1.0)
            elif self.state == self.STATE_ROUND_ACTIVE and is_target:
                action_col = (
                    self.palette["target_elevate"]
                    if self.target_action == "ELEVATE"
                    else self.palette["target_dig"]
                )
                progress = self._get_target_progress(curr_h)
                remaining = 1.0 - progress
                active_color = _lerp_color(action_col, self.palette["target_success"], progress * 0.55)
                self.bridge.send_cell_progress(
                    idx,
                    self.palette["cyan_base"],
                    active_color,
                    math.sqrt(remaining)
                )
            elif self.state == self.STATE_PREPARE_FLAT:
                tol = cfg.FLAT_TOLERANCE_MM
                if curr_h > tol:
                    t = min(0.55, (curr_h - tol) / 50.0)
                    col = _lerp_color(self.palette["cyan_base"], self.palette["target_dig"], t)
                elif curr_h < -tol:
                    t = min(0.55, (abs(curr_h) - tol) / 50.0)
                    col = _lerp_color(self.palette["cyan_base"], self.palette["target_elevate"], t)
                else:
                    col = self.palette["cyan_base"]
                self.bridge.send_cell_state(idx, col[0], col[1], col[2], 1.0)
            else:
                c = self.palette["cyan_base"]
                self.bridge.send_cell_state(idx, c[0], c[1], c[2], 1.0)

    def _commit_active_edit(self):
        if self.editing_field:
            if self.config_mgr.set_numeric_field(self.editing_field, self.editing_buffer):
                self.apply_live_config()
                self.show_toast(f"Actualizado: {self.editing_field}")
            self.editing_field = None
            self.editing_buffer = ""

    def handle_input(self, event):
        if event.type == pygame.KEYDOWN:
            # 1. Si se está escribiendo el nombre de un nuevo archivo .env
            if self.saving_new_env:
                if event.key == pygame.K_RETURN:
                    fname = self.new_env_buffer.strip() or "personalizado"
                    saved = self.config_mgr.save_env(fname)
                    self.saving_new_env = False
                    self.show_toast(f"Guardado en configs/{saved}")
                elif event.key == pygame.K_ESCAPE:
                    self.saving_new_env = False
                elif event.key == pygame.K_BACKSPACE:
                    self.new_env_buffer = self.new_env_buffer[:-1]
                else:
                    ch = event.unicode
                    if ch and (ch.isalnum() or ch in ("_", "-")):
                        self.new_env_buffer += ch
                return

            # 2. Si se está editando un número específico en el Modo Avanzado
            if self.editing_field is not None:
                if event.key == pygame.K_RETURN:
                    self._commit_active_edit()
                elif event.key == pygame.K_ESCAPE:
                    self.editing_field = None
                    self.editing_buffer = ""
                elif event.key == pygame.K_BACKSPACE:
                    self.editing_buffer = self.editing_buffer[:-1]
                else:
                    ch = event.unicode
                    if ch and (ch.isdigit() or ch in (".", "-")):
                        self.editing_buffer += ch
                return

            # 3. Atajos normales de juego
            if event.key == pygame.K_SPACE:
                if self.state in (self.STATE_WELCOME, self.STATE_GAME_OVER):
                    self.start_new_game()
                elif self.state == self.STATE_PREPARE_FLAT:
                    self._start_active_phase()
            elif event.key == pygame.K_r:
                self.provider.reset()
            elif event.key == pygame.K_g:
                if self.metrics.session.rounds:
                    self.metrics.export_session()
                    self.show_toast("Reporte CSV/JSON exportado en records/")

    def handle_inspector_click(self, mx: int, my: int) -> bool:
        """
        Procesa clics sobre los botones y controles interactivos de la ventana de Telemetría.
        Retorna True si el clic fue consumido por un botón de interfaz.
        """
        for rect, action, payload in self.ui_hitboxes:
            if rect.collidepoint(mx, my):
                if self.editing_field and action != "EDIT_FIELD":
                    self._commit_active_edit()

                if action == "SWITCH_TAB":
                    self.inspector_tab = str(payload)
                    self.saving_new_env = False
                    return True

                elif action == "SWITCH_CFG_MODE":
                    self.config_mode = str(payload)
                    self.saving_new_env = False
                    return True

                elif action == "CYCLE_ENV":
                    files = self.config_mgr.list_env_files()
                    if files:
                        curr_idx = files.index(self.config_mgr.active_file) if self.config_mgr.active_file in files else 0
                        next_idx = (curr_idx + int(payload)) % len(files)
                        target_env = files[next_idx]
                        self.config_mgr.load_env(target_env)
                        self.apply_live_config()
                        self.show_toast(f"Cargado: configs/{target_env}")
                    return True

                elif action == "SET_CATEGORY":
                    cat_key, cat_val = payload
                    self.config_mgr.apply_easy_category(cat_key, cat_val)
                    self.apply_live_config()
                    self.show_toast(f"{cat_key} -> {cat_val}")
                    return True

                elif action == "STEP_FIELD":
                    fname, step_dir = payload
                    self.config_mgr.step_numeric_field(fname, int(step_dir))
                    self.apply_live_config()
                    return True

                elif action == "EDIT_FIELD":
                    fname = str(payload)
                    self.editing_field = fname
                    val = getattr(self.config_mgr.config, fname)
                    self.editing_buffer = str(val)
                    return True

                elif action == "SAVE_CURRENT_ENV":
                    saved = self.config_mgr.save_env(self.config_mgr.active_file)
                    self.show_toast(f"Configuración guardada en configs/{saved}")
                    return True

                elif action == "OPEN_SAVE_NEW":
                    self.saving_new_env = not self.saving_new_env
                    return True

                elif action == "CONFIRM_SAVE_NEW":
                    fname = self.new_env_buffer.strip() or "personalizado"
                    saved = self.config_mgr.save_env(fname)
                    self.saving_new_env = False
                    self.show_toast(f"Nuevo archivo creado: configs/{saved}")
                    return True

                elif action == "RESET_DEFAULT_ENV":
                    self.config_mgr.reset_to_default()
                    self.apply_live_config()
                    self.show_toast("Restablecido a configs/default.env")
                    return True

        if self.editing_field:
            self._commit_active_edit()
        return False

    # =========================================================================
    # VENTANA 1: VISTA DE PROYECCIÓN (PACIENTE / CAJA DE ARENA)
    # =========================================================================
    def render(self, surface: pygame.Surface, is_emulator: bool = True):
        width, height = surface.get_size()
        heights = self.provider.get_heights()
        now = time.time()
        cfg = self.config_mgr.config

        for r in range(self.rows):
            for c in range(self.cols):
                idx = r * self.cols + c
                x0 = int(c * width / self.cols)
                x1 = int((c + 1) * width / self.cols)
                y0 = int(r * height / self.rows)
                y1 = int((r + 1) * height / self.rows)
                cell_rect = pygame.Rect(x0, y0, x1 - x0, y1 - y0)

                curr_h = heights[idx] if idx < len(heights) else 0.0
                is_target = (self.state in (self.STATE_ROUND_ACTIVE, self.STATE_ROUND_WON)) and (idx == self.target_quadrant)

                if self.state == self.STATE_ROUND_WON and is_target:
                    elapsed_win = min(1.0, (now - self.round_win_time) / max(0.2, cfg.WIN_PAUSE_SEC))
                    flash_col = _lerp_color(self.palette["target_success"], self.palette["cyan_base"], elapsed_win)
                    pygame.draw.rect(surface, flash_col, cell_rect)

                elif self.state == self.STATE_ROUND_ACTIVE and is_target:
                    action_col = (
                        self.palette["target_elevate"]
                        if self.target_action == "ELEVATE"
                        else self.palette["target_dig"]
                    )
                    progress = self._get_target_progress(curr_h)
                    pygame.draw.rect(surface, self.palette["cyan_base"], cell_rect)

                    remaining = 1.0 - progress
                    active_color = _lerp_color(action_col, self.palette["target_success"], progress * 0.55)
                    rem_w = max(0, int(cell_rect.width * math.sqrt(remaining)))
                    rem_h = max(0, int(cell_rect.height * math.sqrt(remaining)))
                    rem_rect = pygame.Rect(
                        cell_rect.centerx - rem_w // 2,
                        cell_rect.centery - rem_h // 2,
                        rem_w,
                        rem_h
                    )
                    pygame.draw.rect(surface, active_color, rem_rect)

                elif self.state == self.STATE_PREPARE_FLAT:
                    tol = cfg.FLAT_TOLERANCE_MM
                    if curr_h > tol:
                        t = min(0.55, (curr_h - tol) / 50.0)
                        col = _lerp_color(self.palette["cyan_base"], self.palette["target_dig"], t)
                    elif curr_h < -tol:
                        t = min(0.55, (abs(curr_h) - tol) / 50.0)
                        col = _lerp_color(self.palette["cyan_base"], self.palette["target_elevate"], t)
                    else:
                        col = self.palette["cyan_base"]
                    pygame.draw.rect(surface, col, cell_rect)

                else:
                    pygame.draw.rect(surface, self.palette["cyan_base"], cell_rect)

        line_thickness = 5
        for c in range(1, self.cols):
            x = int(c * width / self.cols)
            pygame.draw.line(surface, self.palette["grid_line"], (x, 0), (x, height), line_thickness)
        for r in range(1, self.rows):
            y = int(r * height / self.rows)
            pygame.draw.line(surface, self.palette["grid_line"], (0, y), (width, y), line_thickness)

        if self.state in (self.STATE_ROUND_ACTIVE, self.STATE_ROUND_WON):
            timer_ratio = max(0.0, min(1.0, self.time_left / self.time_limit))
            self._draw_translucent_pie_timer(
                surface,
                width // 2,
                height // 2,
                int(min(width, height) * 0.20),
                timer_ratio,
                cfg.PIE_TIMER_OPACITY,
            )

        self._draw_superimposed_hud(surface, width, height)

    # =========================================================================
    # VENTANA 2: PANTALLA DE INSPECCIÓN, TELEMETRÍA Y CONFIGURACIÓN (.ENV)
    # =========================================================================
    def render_inspector(self, surface: pygame.Surface, is_emulator: bool = True):
        self.ui_hitboxes.clear()
        w, h = surface.get_size()
        surface.fill((16, 20, 28))

        font_title = pygame.font.SysFont("Arial", 15, bold=True)
        font_sec = pygame.font.SysFont("Arial", 13, bold=True)
        font_body = pygame.font.SysFont("Arial", 12)
        font_mono = pygame.font.SysFont("DejaVu Sans Mono", 11, bold=True)

        pad = 14
        y_cursor = 10

        # --- BARRA SUPERIOR DE PESTAÑAS (MONITOREO vs CONFIGURACIÓN .ENV) ---
        tab_w = (w - pad * 2 - 8) // 2
        tab1_rect = pygame.Rect(pad, y_cursor, tab_w, 36)
        tab2_rect = pygame.Rect(pad + tab_w + 8, y_cursor, tab_w, 36)

        is_mon = (self.inspector_tab == self.TAB_MONITOR)
        pygame.draw.rect(surface, (0, 145, 185) if is_mon else (28, 36, 50), tab1_rect, border_radius=8)
        pygame.draw.rect(surface, (100, 220, 255) if is_mon else (60, 75, 100), tab1_rect, 2 if is_mon else 1, border_radius=8)
        t1_s = font_title.render("1. MONITOREO Y TELEMETRÍA", True, (255, 255, 255) if is_mon else (165, 185, 210))
        surface.blit(t1_s, (tab1_rect.centerx - t1_s.get_width() // 2, tab1_rect.centery - t1_s.get_height() // 2))
        self.ui_hitboxes.append((tab1_rect, "SWITCH_TAB", self.TAB_MONITOR))

        is_cfg = (self.inspector_tab == self.TAB_CONFIG)
        pygame.draw.rect(surface, (0, 145, 185) if is_cfg else (28, 36, 50), tab2_rect, border_radius=8)
        pygame.draw.rect(surface, (100, 220, 255) if is_cfg else (60, 75, 100), tab2_rect, 2 if is_cfg else 1, border_radius=8)
        t2_s = font_title.render(f"2. CONFIGURACIÓN ({self.config_mgr.active_file})", True, (255, 255, 255) if is_cfg else (165, 185, 210))
        surface.blit(t2_s, (tab2_rect.centerx - t2_s.get_width() // 2, tab2_rect.centery - t2_s.get_height() // 2))
        self.ui_hitboxes.append((tab2_rect, "SWITCH_TAB", self.TAB_CONFIG))

        y_cursor += 46

        if self.inspector_tab == self.TAB_MONITOR:
            self._render_monitor_tab(surface, w, h, pad, y_cursor, is_emulator, font_sec, font_body, font_mono)
        else:
            self._render_config_tab(surface, w, h, pad, y_cursor, font_sec, font_body, font_mono)

        # Toast de confirmación si se guardó/cargó un .env recientemente
        if time.time() < self.status_toast_until and self.status_toast_msg:
            toast_s = font_sec.render(self.status_toast_msg, True, (255, 255, 255))
            tw = toast_s.get_width() + 28
            t_rect = pygame.Rect((w - tw) // 2, h - 58, tw, 28)
            pygame.draw.rect(surface, (0, 155, 95), t_rect, border_radius=6)
            pygame.draw.rect(surface, (180, 255, 210), t_rect, 1, border_radius=6)
            surface.blit(toast_s, (t_rect.centerx - toast_s.get_width() // 2, t_rect.centery - toast_s.get_height() // 2))

        # Pie de controles
        ctrl_txt = "[ESPACIO]: Iniciar / Saltar Nivelación  |  [R]: Aplanar Arena  |  [G]: Exportar CSV/JSON  |  [ESC]: Salir"
        ctrl_s = font_body.render(ctrl_txt, True, (145, 165, 190))
        surface.blit(ctrl_s, (w // 2 - ctrl_s.get_width() // 2, h - 22))

    def _render_monitor_tab(self, surface, w, h, pad, y_cursor, is_emulator, font_sec, font_body, font_mono):
        cfg = self.config_mgr.config
        sec1_title = font_sec.render(
            f"1. INSPECCIÓN FÍSICA DE CUADRANTES — Perfil: configs/{self.config_mgr.active_file}",
            True,
            (0, 195, 235),
        )
        surface.blit(sec1_title, (pad, y_cursor))
        y_cursor += 20

        grid_box_h = int(h * 0.30)
        grid_box = pygame.Rect(pad, y_cursor, w - pad * 2, grid_box_h)
        pygame.draw.rect(surface, (22, 28, 38), grid_box, border_radius=8)

        heights = self.provider.get_heights()
        cw = grid_box.width // self.cols
        ch = grid_box.height // self.rows

        for r in range(self.rows):
            for c in range(self.cols):
                idx = r * self.cols + c
                cell_r = pygame.Rect(grid_box.x + c * cw + 4, grid_box.y + r * ch + 4, cw - 8, ch - 8)
                curr_h = heights[idx] if idx < len(heights) else 0.0
                is_target = (self.state in (self.STATE_ROUND_ACTIVE, self.STATE_ROUND_WON)) and (idx == self.target_quadrant)

                bg_c = (38, 48, 66) if is_target else (28, 35, 48)
                border_c = (
                    self.palette["target_elevate"]
                    if (is_target and self.target_action == "ELEVATE")
                    else (self.palette["target_dig"] if is_target else (65, 80, 105))
                )
                pygame.draw.rect(surface, bg_c, cell_r, border_radius=6)
                pygame.draw.rect(surface, border_c, cell_r, 2 if is_target else 1, border_radius=6)

                q_lbl = f"Q{idx + 1} {'[OBJETIVO]' if is_target else ''}"
                surface.blit(font_sec.render(q_lbl, True, (255, 255, 255) if is_target else (160, 180, 205)), (cell_r.x + 8, cell_r.y + 5))

                mm_str = f"Altura: {curr_h:+.1f} mm"
                mm_col = (255, 110, 110) if curr_h < -cfg.FLAT_TOLERANCE_MM else ((100, 235, 140) if curr_h > cfg.FLAT_TOLERANCE_MM else (180, 220, 250))
                surface.blit(font_mono.render(mm_str, True, mm_col), (cell_r.x + 8, cell_r.y + 23))

                if is_target:
                    prog = self._get_target_progress(curr_h)
                    act_word = "PONER (Rojo)" if self.target_action == "ELEVATE" else "SACAR (Verde)"
                    meta_str = f"{act_word} -> {self.target_threshold:+.0f} mm ({int(prog * 100)}%)"
                    surface.blit(font_body.render(meta_str, True, (255, 220, 110)), (cell_r.x + 8, cell_r.y + 42))

                    bar_r = pygame.Rect(cell_r.x + 8, cell_r.bottom - 12, cell_r.width - 16, 7)
                    pygame.draw.rect(surface, (15, 20, 28), bar_r, border_radius=4)
                    fill_r = pygame.Rect(bar_r.x, bar_r.y, int(bar_r.width * prog), bar_r.height)
                    pygame.draw.rect(surface, border_c, fill_r, border_radius=4)
                else:
                    flat_ok = abs(curr_h) < cfg.FLAT_TOLERANCE_MM
                    st_str = "Estado: NIVELADO" if flat_ok else "Estado: DESNIVELADO"
                    surface.blit(font_body.render(st_str, True, (110, 205, 145) if flat_ok else (240, 165, 70)), (cell_r.x + 8, cell_r.y + 42))

        y_cursor += grid_box_h + 12

        # --- SECCIÓN 2: MÉTRICAS CLÍNICAS Y BIOMECÁNICAS DE LA SESIÓN ---
        sec2_title = font_sec.render("2. INDICADORES CLÍNICOS DE REHABILITACIÓN MOTRIZ", True, (0, 195, 235))
        surface.blit(sec2_title, (pad, y_cursor))
        y_cursor += 20

        stats_box_h = 108
        stats_box = pygame.Rect(pad, y_cursor, w - pad * 2, stats_box_h)
        pygame.draw.rect(surface, (22, 28, 38), stats_box, border_radius=8)
        pygame.draw.rect(surface, (50, 65, 88), stats_box, 1, border_radius=8)

        rounds = self.metrics.session.rounds
        won_rounds = [r for r in rounds if r.success]
        avg_time = (sum(r.time_taken_sec for r in won_rounds) / len(won_rounds)) if won_rounds else 0.0

        left_times = [r.time_taken_sec for r in won_rounds if (r.target_quadrant % self.cols) < (self.cols / 2)]
        right_times = [r.time_taken_sec for r in won_rounds if (r.target_quadrant % self.cols) >= (self.cols / 2)]
        avg_left = (sum(left_times) / len(left_times)) if left_times else 0.0
        avg_right = (sum(right_times) / len(right_times)) if right_times else 0.0

        elev_times = [r.time_taken_sec for r in won_rounds if r.target_action == "ELEVATE"]
        dig_times = [r.time_taken_sec for r in won_rounds if r.target_action == "DIG"]
        avg_elev = (sum(elev_times) / len(elev_times)) if elev_times else 0.0
        avg_dig = (sum(dig_times) / len(dig_times)) if dig_times else 0.0

        col1_x = stats_box.x + 12
        col2_x = stats_box.x + int(stats_box.width * 0.46)
        sy = stats_box.y + 9

        metrics_left = [
            f"Paciente ID: {self.metrics.patient_id}",
            f"Estado: {self.state} (Nivel {self.round_number})",
            f"Tiempo: {max(0.0, self.time_left):.2f} s / {self.time_limit:.1f} s",
            f"Rondas: {len(won_rounds)}/{len(rounds)} | Puntaje: {self.score}",
        ]
        metrics_right = [
            f"Tiempo Medio Respuesta: {avg_time:.2f} s",
            f"Simetría Izq: {avg_left:.2f} s | Der: {avg_right:.2f} s",
            f"Poner (Rojo): {avg_elev:.2f} s | Sacar (Verde): {avg_dig:.2f} s",
            f"UDP: TX->{cfg.OSC_HOST}:{cfg.OSC_TX_PORT} | RX<-:{cfg.OSC_RX_PORT}",
        ]

        for i in range(4):
            surface.blit(font_body.render(metrics_left[i], True, (220, 230, 245)), (col1_x, sy + i * 23))
            surface.blit(font_body.render(metrics_right[i], True, (195, 220, 250)), (col2_x, sy + i * 23))

        y_cursor += stats_box_h + 12

        # --- SECCIÓN 3: HISTORIAL DE RONDAS RECIENTES ---
        sec3_title = font_sec.render("3. REGISTRO DE RONDAS RECIENTES", True, (0, 195, 235))
        surface.blit(sec3_title, (pad, y_cursor))
        y_cursor += 20

        hist_h = max(70, h - y_cursor - 34)
        hist_box = pygame.Rect(pad, y_cursor, w - pad * 2, hist_h)
        pygame.draw.rect(surface, (22, 28, 38), hist_box, border_radius=8)
        pygame.draw.rect(surface, (50, 65, 88), hist_box, 1, border_radius=8)

        hdr = "RONDA  CELDA  ACCIÓN         META      FINAL      TIEMPO   ESTADO"
        surface.blit(font_mono.render(hdr, True, (140, 165, 195)), (hist_box.x + 12, hist_box.y + 8))
        pygame.draw.line(surface, (50, 65, 88), (hist_box.x + 8, hist_box.y + 26), (hist_box.right - 8, hist_box.y + 26), 1)

        recent = rounds[-5:]
        for idx_r, rm in enumerate(reversed(recent)):
            ry = hist_box.y + 32 + idx_r * 19
            if ry + 16 > hist_box.bottom:
                break
            act_str = "PONER (Rojo) " if rm.target_action == "ELEVATE" else "SACAR (Verde)"
            res_str = "SUPERADA" if rm.success else "FALLO"
            row_txt = (
                f"#{rm.round_number:<5} Q{rm.target_quadrant + 1:<5} {act_str}  "
                f"{rm.target_threshold_mm:+5.0f}mm   {rm.final_height_mm:+6.1f}mm   "
                f"{rm.time_taken_sec:5.2f}s   {res_str}"
            )
            row_col = (110, 230, 150) if rm.success else (245, 110, 110)
            surface.blit(font_mono.render(row_txt, True, row_col), (hist_box.x + 12, ry))

    def _render_config_tab(self, surface, w, h, pad, y_cursor, font_sec, font_body, font_mono):
        cfg = self.config_mgr.config

        # --- BARRA DE SELECCIÓN DE PERFIL .ENV Y SUBMODO (FÁCIL / AVANZADO) ---
        bar_rect = pygame.Rect(pad, y_cursor, w - pad * 2, 42)
        pygame.draw.rect(surface, (24, 32, 44), bar_rect, border_radius=8)
        pygame.draw.rect(surface, (55, 75, 105), bar_rect, 1, border_radius=8)

        lbl_env = font_sec.render("Archivo .env:", True, (180, 205, 235))
        surface.blit(lbl_env, (bar_rect.x + 10, bar_rect.y + 12))

        prev_btn = pygame.Rect(bar_rect.x + 100, bar_rect.y + 6, 28, 30)
        env_box = pygame.Rect(prev_btn.right + 4, bar_rect.y + 6, 175, 30)
        next_btn = pygame.Rect(env_box.right + 4, bar_rect.y + 6, 28, 30)

        for btn_r, sym, step_d in [(prev_btn, "<", -1), (next_btn, ">", +1)]:
            pygame.draw.rect(surface, (42, 56, 78), btn_r, border_radius=5)
            pygame.draw.rect(surface, (90, 120, 160), btn_r, 1, border_radius=5)
            s = font_sec.render(sym, True, (255, 255, 255))
            surface.blit(s, (btn_r.centerx - s.get_width() // 2, btn_r.centery - s.get_height() // 2))
            self.ui_hitboxes.append((btn_r, "CYCLE_ENV", step_d))

        pygame.draw.rect(surface, (16, 22, 32), env_box, border_radius=5)
        pygame.draw.rect(surface, (0, 185, 225), env_box, 1, border_radius=5)
        env_s = font_mono.render(self.config_mgr.active_file, True, (255, 230, 110))
        surface.blit(env_s, (env_box.centerx - env_s.get_width() // 2, env_box.centery - env_s.get_height() // 2))

        # Botones Modo Fácil vs Modo Avanzado
        mode_w = (bar_rect.right - next_btn.right - 20) // 2
        easy_btn = pygame.Rect(next_btn.right + 10, bar_rect.y + 6, mode_w, 30)
        adv_btn = pygame.Rect(easy_btn.right + 6, bar_rect.y + 6, mode_w, 30)

        is_easy = (self.config_mode == self.CFG_MODE_EASY)
        pygame.draw.rect(surface, (0, 155, 115) if is_easy else (36, 46, 62), easy_btn, border_radius=6)
        pygame.draw.rect(surface, (110, 245, 195) if is_easy else (70, 90, 115), easy_btn, 1, border_radius=6)
        es = font_sec.render("FÁCIL (CATEGORÍAS)", True, (255, 255, 255) if is_easy else (170, 190, 215))
        surface.blit(es, (easy_btn.centerx - es.get_width() // 2, easy_btn.centery - es.get_height() // 2))
        self.ui_hitboxes.append((easy_btn, "SWITCH_CFG_MODE", self.CFG_MODE_EASY))

        pygame.draw.rect(surface, (195, 115, 0) if not is_easy else (36, 46, 62), adv_btn, border_radius=6)
        pygame.draw.rect(surface, (255, 210, 110) if not is_easy else (70, 90, 115), adv_btn, 1, border_radius=6)
        ad_s = font_sec.render("AVANZADO (NUMÉRICO)", True, (255, 255, 255) if not is_easy else (170, 190, 215))
        surface.blit(ad_s, (adv_btn.centerx - ad_s.get_width() // 2, adv_btn.centery - ad_s.get_height() // 2))
        self.ui_hitboxes.append((adv_btn, "SWITCH_CFG_MODE", self.CFG_MODE_ADVANCED))

        y_cursor += 50

        # --- CUERPO CENTRAL: FÁCIL (CATEGORÍAS) O AVANZADO (NUMÉRICO) ---
        body_h = h - y_cursor - 90
        body_rect = pygame.Rect(pad, y_cursor, w - pad * 2, body_h)
        pygame.draw.rect(surface, (20, 26, 36), body_rect, border_radius=8)
        pygame.draw.rect(surface, (50, 65, 88), body_rect, 1, border_radius=8)

        if is_easy:
            self._render_easy_config_body(surface, body_rect, font_sec, font_body, font_mono)
        else:
            self._render_advanced_config_body(surface, body_rect, font_sec, font_body, font_mono)

        y_cursor += body_h + 10

        # --- BARRA INFERIOR DE GUARDADO Y RESTABLECIMIENTO (.ENV) ---
        if self.saving_new_env:
            prompt_lbl = font_sec.render("Nombre nuevo .env:", True, (255, 230, 110))
            surface.blit(prompt_lbl, (pad, y_cursor + 8))

            inp_r = pygame.Rect(pad + 145, y_cursor + 2, 230, 32)
            pygame.draw.rect(surface, (12, 16, 24), inp_r, border_radius=6)
            pygame.draw.rect(surface, (0, 210, 255), inp_r, 2, border_radius=6)
            txt_s = font_mono.render(f"{self.new_env_buffer}.env|", True, (255, 255, 255))
            surface.blit(txt_s, (inp_r.x + 10, inp_r.centery - txt_s.get_height() // 2))

            ok_btn = pygame.Rect(inp_r.right + 10, y_cursor + 2, 130, 32)
            cancel_btn = pygame.Rect(ok_btn.right + 8, y_cursor + 2, 110, 32)

            pygame.draw.rect(surface, (0, 165, 95), ok_btn, border_radius=6)
            ok_s = font_sec.render("CONFIRMAR [ENTER]", True, (255, 255, 255))
            surface.blit(ok_s, (ok_btn.centerx - ok_s.get_width() // 2, ok_btn.centery - ok_s.get_height() // 2))
            self.ui_hitboxes.append((ok_btn, "CONFIRM_SAVE_NEW", None))

            pygame.draw.rect(surface, (140, 45, 55), cancel_btn, border_radius=6)
            can_s = font_sec.render("CANCELAR", True, (255, 255, 255))
            surface.blit(can_s, (cancel_btn.centerx - can_s.get_width() // 2, cancel_btn.centery - can_s.get_height() // 2))
            self.ui_hitboxes.append((cancel_btn, "OPEN_SAVE_NEW", None))
        else:
            btn_w = (w - pad * 2 - 16) // 3
            b1 = pygame.Rect(pad, y_cursor + 2, btn_w, 34)
            b2 = pygame.Rect(b1.right + 8, y_cursor + 2, btn_w, 34)
            b3 = pygame.Rect(b2.right + 8, y_cursor + 2, btn_w, 34)

            for rect_b, label_b, col_b, act_b in [
                (b1, f"GUARDAR ({cfg and self.config_mgr.active_file})", (0, 145, 95), "SAVE_CURRENT_ENV"),
                (b2, "GUARDAR COMO NUEVO .ENV", (0, 120, 185), "OPEN_SAVE_NEW"),
                (b3, "RESTABLECER PREDETERMINADO", (175, 55, 65), "RESET_DEFAULT_ENV"),
            ]:
                pygame.draw.rect(surface, col_b, rect_b, border_radius=6)
                pygame.draw.rect(surface, (220, 240, 255), rect_b, 1, border_radius=6)
                bs = font_sec.render(label_b, True, (255, 255, 255))
                surface.blit(bs, (rect_b.centerx - bs.get_width() // 2, rect_b.centery - bs.get_height() // 2))
                self.ui_hitboxes.append((rect_b, act_b, None))

    def _render_easy_config_body(self, surface, body_rect, font_sec, font_body, font_mono):
        cfg = self.config_mgr.config
        x0 = body_rect.x + 14
        y0 = body_rect.y + 12
        avail_w = body_rect.width - 28

        hdr = font_sec.render(
            "CONFIGURACIONES ESENCIALES POR CATEGORÍA (Haz clic para cambiar entre Baja, Media o Alta):",
            True,
            (0, 200, 240),
        )
        surface.blit(hdr, (x0, y0))
        y0 += 26

        row_h = 54
        for cat_key, cat_label, options in EASY_CATEGORIES_META:
            row_rect = pygame.Rect(x0, y0, avail_w, row_h - 6)
            pygame.draw.rect(surface, (26, 34, 48), row_rect, border_radius=6)
            pygame.draw.rect(surface, (45, 60, 82), row_rect, 1, border_radius=6)

            lbl_s = font_sec.render(cat_label, True, (230, 240, 255))
            surface.blit(lbl_s, (row_rect.x + 12, row_rect.centery - lbl_s.get_height() // 2))

            curr_val = getattr(cfg, cat_key)
            btns_area_x = row_rect.x + int(avail_w * 0.36)
            btns_area_w = row_rect.right - btns_area_x - 10
            opt_w = (btns_area_w - (len(options) - 1) * 6) // len(options)

            for i, (opt_code, opt_text) in enumerate(options):
                bx = btns_area_x + i * (opt_w + 6)
                by = row_rect.y + 7
                brect = pygame.Rect(bx, by, opt_w, row_rect.height - 14)

                selected = (curr_val == opt_code)
                bg_c = (0, 150, 195) if selected else (38, 48, 66)
                bd_c = (130, 235, 255) if selected else (70, 88, 115)
                pygame.draw.rect(surface, bg_c, brect, border_radius=5)
                pygame.draw.rect(surface, bd_c, brect, 2 if selected else 1, border_radius=5)

                ts = font_body.render(opt_text, True, (255, 255, 255) if selected else (175, 195, 220))
                surface.blit(ts, (brect.centerx - ts.get_width() // 2, brect.centery - ts.get_height() // 2))
                self.ui_hitboxes.append((brect, "SET_CATEGORY", (cat_key, opt_code)))

            y0 += row_h

        # Resumen inferior de traducción numérica
        y0 += 6
        sum_rect = pygame.Rect(x0, y0, avail_w, max(48, body_rect.bottom - y0 - 10))
        pygame.draw.rect(surface, (15, 20, 28), sum_rect, border_radius=6)
        pygame.draw.rect(surface, (45, 65, 90), sum_rect, 1, border_radius=6)

        s1 = (
            f"Valores Activos -> Tiempo Base: {cfg.BASE_TIME_LIMIT_SEC:.1f}s (mín {cfg.MIN_TIME_LIMIT_SEC:.1f}s) | "
            f"Poner: +{cfg.ELEVATE_THRESHOLD_MM:.0f}mm | Sacar: {cfg.DIG_THRESHOLD_MM:.0f}mm"
        )
        s2 = (
            f"Cuadrícula Inicial: {cfg.INITIAL_COLS}x{cfg.INITIAL_ROWS} (Etapa máx: {cfg.MAX_GRID_STAGE}) | "
            f"Tolerancia Nivelado: ±{cfg.FLAT_TOLERANCE_MM:.0f}mm | Acción: {cfg.ACTION_CATEGORY}"
        )
        surface.blit(font_mono.render(s1, True, (150, 220, 250)), (sum_rect.x + 12, sum_rect.y + 8))
        surface.blit(font_mono.render(s2, True, (150, 220, 250)), (sum_rect.x + 12, sum_rect.y + 28))

    def _render_advanced_config_body(self, surface, body_rect, font_sec, font_body, font_mono):
        cfg = self.config_mgr.config
        x0 = body_rect.x + 12
        y0 = body_rect.y + 10
        avail_w = body_rect.width - 24

        hdr = font_sec.render(
            "MODO AVANZADO: Haz clic en un número para escribir con el teclado (+ Enter) o usa [-] y [+]:",
            True,
            (255, 205, 90),
        )
        surface.blit(hdr, (x0, y0))
        y0 += 24

        col_w = (avail_w - 12) // 2
        row_h = 38

        for idx, (fname, flabel, ftype, _, _, _) in enumerate(ADVANCED_FIELDS_META):
            col_idx = idx % 2
            row_idx = idx // 2
            rx = x0 + col_idx * (col_w + 12)
            ry = y0 + row_idx * row_h

            if ry + row_h - 4 > body_rect.bottom:
                break

            item_r = pygame.Rect(rx, ry, col_w, row_h - 5)
            is_editing = (self.editing_field == fname)

            pygame.draw.rect(surface, (28, 36, 50), item_r, border_radius=5)
            pygame.draw.rect(surface, (0, 210, 255) if is_editing else (48, 62, 85), item_r, 1, border_radius=5)

            lbl_s = font_body.render(flabel, True, (220, 232, 248))
            surface.blit(lbl_s, (item_r.x + 8, item_r.centery - lbl_s.get_height() // 2))

            btn_plus = pygame.Rect(item_r.right - 28, item_r.y + 4, 24, item_r.height - 8)
            val_box = pygame.Rect(btn_plus.left - 72, item_r.y + 4, 68, item_r.height - 8)
            btn_minus = pygame.Rect(val_box.left - 26, item_r.y + 4, 24, item_r.height - 8)

            # Botón [-]
            pygame.draw.rect(surface, (45, 58, 78), btn_minus, border_radius=4)
            ms = font_sec.render("-", True, (255, 255, 255))
            surface.blit(ms, (btn_minus.centerx - ms.get_width() // 2, btn_minus.centery - ms.get_height() // 2))
            self.ui_hitboxes.append((btn_minus, "STEP_FIELD", (fname, -1)))

            # Caja de valor numérico (clicable para escribir)
            pygame.draw.rect(surface, (12, 16, 24), val_box, border_radius=4)
            pygame.draw.rect(surface, (0, 225, 255) if is_editing else (80, 105, 135), val_box, 2 if is_editing else 1, border_radius=4)

            if is_editing:
                val_str = f"{self.editing_buffer}|"
                val_col = (255, 240, 120)
            else:
                raw_v = getattr(cfg, fname)
                val_str = f"{raw_v:.2f}" if ftype is float else str(raw_v)
                val_col = (130, 235, 255)

            vs = font_mono.render(val_str, True, val_col)
            surface.blit(vs, (val_box.centerx - vs.get_width() // 2, val_box.centery - vs.get_height() // 2))
            self.ui_hitboxes.append((val_box, "EDIT_FIELD", fname))

            # Botón [+]
            pygame.draw.rect(surface, (45, 58, 78), btn_plus, border_radius=4)
            ps = font_sec.render("+", True, (255, 255, 255))
            surface.blit(ps, (btn_plus.centerx - ps.get_width() // 2, btn_plus.centery - ps.get_height() // 2))
            self.ui_hitboxes.append((btn_plus, "STEP_FIELD", (fname, +1)))

    def _draw_translucent_pie_timer(self, surface: pygame.Surface, cx: int, cy: int, radius: int, ratio: float, opacity: int = 75):
        overlay = pygame.Surface((radius * 2 + 10, radius * 2 + 10), pygame.SRCALPHA)
        ocx, ocy = radius + 5, radius + 5

        pygame.draw.circle(overlay, (0, 0, 0, 35), (ocx, ocy), radius)

        if ratio > 0.001:
            alpha = max(20, min(220, int(opacity)))
            pie_color = (255, 255, 255, alpha) if ratio > 0.25 else (255, 235, 80, min(230, alpha + 20))

            num_segments = max(3, int(90 * ratio))
            start_angle = -math.pi / 2
            end_angle = start_angle + (2 * math.pi * ratio)

            points = [(ocx, ocy)]
            for i in range(num_segments + 1):
                ang = start_angle + (end_angle - start_angle) * (i / num_segments)
                px = ocx + int(radius * math.cos(ang))
                py = ocy + int(radius * math.sin(ang))
                points.append((px, py))

            if len(points) >= 3:
                pygame.draw.polygon(overlay, pie_color, points)

        pygame.draw.circle(overlay, (0, 0, 0, 65), (ocx, ocy), radius, 3)
        surface.blit(overlay, (cx - ocx, cy - ocy))

    def _draw_superimposed_hud(self, surface: pygame.Surface, width: int, height: int):
        hud_layer = pygame.Surface((width, height), pygame.SRCALPHA)

        font_hud = pygame.font.SysFont("Arial", int(height * 0.038), bold=True)
        font_title = pygame.font.SysFont("Arial", int(height * 0.050), bold=True)
        font_sub = pygame.font.SysFont("Arial", int(height * 0.032), bold=True)

        safe_x = int(width * 0.12)
        safe_y = int(height * 0.08)

        if self.round_number > 0:
            lvl_shadow = font_hud.render(f"NIVEL {self.round_number}", True, (0, 0, 0, 100))
            pts_shadow = font_hud.render(f"{self.score} PTS", True, (0, 0, 0, 100))
            lvl_fg = font_hud.render(f"NIVEL {self.round_number}", True, (255, 255, 255, 135))
            pts_fg = font_hud.render(f"{self.score} PTS", True, (255, 255, 255, 135))

            hud_layer.blit(lvl_shadow, (safe_x + 2, safe_y + 2))
            hud_layer.blit(lvl_fg, (safe_x, safe_y))

            px = width - safe_x - pts_fg.get_width()
            hud_layer.blit(pts_shadow, (px + 2, safe_y + 2))
            hud_layer.blit(pts_fg, (px, safe_y))

        cx, cy = width // 2, height // 2
        if self.state == self.STATE_WELCOME:
            self._blit_centered_translucent(hud_layer, "ESPACIO PARA INICIAR", font_title, cx, cy)
        elif self.state == self.STATE_PREPARE_FLAT:
            self._blit_centered_translucent(hud_layer, "NIVELA LA ARENA", font_title, cx, cy)
        elif self.state == self.STATE_GAME_OVER:
            self._blit_centered_translucent(hud_layer, f"FIN DEL JUEGO — {self.score} PTS", font_title, cx, cy - 22)
            self._blit_centered_translucent(hud_layer, "ESPACIO PARA REINICIAR", font_sub, cx, cy + 28)

        surface.blit(hud_layer, (0, 0))

    def _blit_centered_translucent(self, layer: pygame.Surface, text: str, font: pygame.font.Font, cx: int, cy: int):
        shadow = font.render(text, True, (0, 0, 0, 120))
        fg = font.render(text, True, (255, 255, 255, 175))
        pad_x, pad_y = 22, 10
        bg_rect = pygame.Rect(
            cx - fg.get_width() // 2 - pad_x,
            cy - fg.get_height() // 2 - pad_y,
            fg.get_width() + pad_x * 2,
            fg.get_height() + pad_y * 2
        )
        pygame.draw.rect(layer, (0, 0, 0, 65), bg_rect, border_radius=10)
        layer.blit(shadow, (cx - fg.get_width() // 2 + 2, cy - fg.get_height() // 2 + 2))
        layer.blit(fg, (cx - fg.get_width() // 2, cy - fg.get_height() // 2))
