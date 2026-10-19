import math
import random
import time
import pygame

from .data_provider import BaseDataProvider
from .bridge_client import MagicSandBridgeClient
from .metrics import RoundMetric, TherapyMetricsManager


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
    Cuenta con dos vistas diferenciadas:
      1. Vista de Proyección (render): Pantalla limpia 100% sin huecos ni números en cuadros,
         torta central translúcida y código de color sin conflictos (Cian, Rojo=Poner, Verde=Sacar).
      2. Vista de Inspección y Monitoreo (render_inspector): Panel clínico para el terapeuta/operador
         con lecturas exactas en milímetros, barras de umbral, simetría motora izquierda/derecha,
         historial de tiempos de respuesta y estado de los sockets UDP/OSC.
    """

    STATE_WELCOME = "WELCOME"
    STATE_PREPARE_FLAT = "PREPARE_FLAT"
    STATE_ROUND_ACTIVE = "ROUND_ACTIVE"
    STATE_ROUND_WON = "ROUND_WON"
    STATE_GAME_OVER = "GAME_OVER"

    def __init__(self, data_provider: BaseDataProvider, bridge: MagicSandBridgeClient = None, patient_id: str = "PACIENTE_01"):
        self.provider = data_provider
        self.bridge = bridge or MagicSandBridgeClient()
        self.metrics = TherapyMetricsManager(patient_id=patient_id)

        self.cols = 2
        self.rows = 2
        self.provider.set_grid_size(self.cols, self.rows)

        self.state = self.STATE_WELCOME
        self.round_number = 0
        self.score = 0
        self.target_quadrant = 0
        self.target_action = "ELEVATE"   # "ELEVATE" (Rojo: poner arena) o "DIG" (Verde: sacar arena)
        self.target_threshold = 30.0     # mm
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

    def start_new_game(self):
        self.round_number = 0
        self.score = 0
        self.cols = 2
        self.rows = 2
        self.provider.set_grid_size(self.cols, self.rows)
        self.next_round()

    def next_round(self):
        self.round_number += 1

        if self.round_number <= 4:
            new_cols, new_rows = 2, 2
        elif self.round_number <= 8:
            new_cols, new_rows = 4, 2
        else:
            new_cols, new_rows = 4, 4

        if (new_cols, new_rows) != (self.cols, self.rows):
            self.cols, self.rows = new_cols, new_rows
            self.provider.set_grid_size(self.cols, self.rows)

        num_cells = self.cols * self.rows

        if self.round_number <= 2:
            self.target_action = "ELEVATE"
            self.target_threshold = 28.0 + (self.round_number * 3.0)
            self.time_limit = max(10.0, 16.0 - (self.round_number * 1.0))
        elif self.round_number <= 6:
            self.target_action = random.choice(["ELEVATE", "DIG"])
            self.target_threshold = 35.0 if self.target_action == "ELEVATE" else -25.0
            self.time_limit = 12.0
        else:
            self.target_action = random.choice(["ELEVATE", "DIG"])
            self.target_threshold = 40.0 if self.target_action == "ELEVATE" else -30.0
            self.time_limit = max(7.0, 11.5 - (self.round_number * 0.35))

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

        heights = self.provider.get_heights()
        if not heights or self.target_quadrant >= len(heights):
            return

        current_h = heights[self.target_quadrant]

        if self.state == self.STATE_PREPARE_FLAT:
            is_flat = all(abs(h) < 7.0 for h in heights)
            if is_flat:
                self._start_active_phase()

        elif self.state == self.STATE_ROUND_ACTIVE:
            self.time_left -= dt
            timer_ratio = max(0.0, self.time_left / self.time_limit)
            self.bridge.send_hud_timer(timer_ratio)

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
            if now - self.round_win_time > 1.2:
                self.next_round()

        # Sincronizar el estado visual de las celdas hacia el motor C++ (puerto 7001)
        self._sync_cells_to_bridge(heights, now)

    def _sync_cells_to_bridge(self, heights: list[float], now: float):
        num_cells = self.cols * self.rows
        for idx in range(num_cells):
            curr_h = heights[idx] if idx < len(heights) else 0.0
            is_target = (self.state in (self.STATE_ROUND_ACTIVE, self.STATE_ROUND_WON)) and (idx == self.target_quadrant)

            if self.state == self.STATE_ROUND_WON and is_target:
                elapsed_win = min(1.0, (now - self.round_win_time) / 1.2)
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
                if curr_h > 7.0:
                    t = min(0.55, (curr_h - 7.0) / 50.0)
                    col = _lerp_color(self.palette["cyan_base"], self.palette["target_dig"], t)
                elif curr_h < -7.0:
                    t = min(0.55, (abs(curr_h) - 7.0) / 50.0)
                    col = _lerp_color(self.palette["cyan_base"], self.palette["target_elevate"], t)
                else:
                    col = self.palette["cyan_base"]
                self.bridge.send_cell_state(idx, col[0], col[1], col[2], 1.0)
            else:
                c = self.palette["cyan_base"]
                self.bridge.send_cell_state(idx, c[0], c[1], c[2], 1.0)

    def handle_input(self, event):
        if event.type == pygame.KEYDOWN:
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

    # =========================================================================
    # VENTANA 1: VISTA DE PROYECCIÓN (PACIENTE / CAJA DE ARENA)
    # =========================================================================
    def render(self, surface: pygame.Surface, is_emulator: bool = True):
        width, height = surface.get_size()
        heights = self.provider.get_heights()
        now = time.time()

        # 1. CUADRANTES A PANTALLA COMPLETA (0, 0, width, height)
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
                    elapsed_win = min(1.0, (now - self.round_win_time) / 1.2)
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
                    if curr_h > 7.0:
                        t = min(0.55, (curr_h - 7.0) / 50.0)
                        col = _lerp_color(self.palette["cyan_base"], self.palette["target_dig"], t)
                    elif curr_h < -7.0:
                        t = min(0.55, (abs(curr_h) - 7.0) / 50.0)
                        col = _lerp_color(self.palette["cyan_base"], self.palette["target_elevate"], t)
                    else:
                        col = self.palette["cyan_base"]
                    pygame.draw.rect(surface, col, cell_rect)

                else:
                    pygame.draw.rect(surface, self.palette["cyan_base"], cell_rect)

        # 2. LÍNEAS DIVISORIAS NEGRAS SÓLIDAS
        line_thickness = 5
        for c in range(1, self.cols):
            x = int(c * width / self.cols)
            pygame.draw.line(surface, self.palette["grid_line"], (x, 0), (x, height), line_thickness)
        for r in range(1, self.rows):
            y = int(r * height / self.rows)
            pygame.draw.line(surface, self.palette["grid_line"], (0, y), (width, y), line_thickness)

        # 3. TORTA DE TIEMPO CENTRAL CON ALTA TRASLUCIDAD
        if self.state in (self.STATE_ROUND_ACTIVE, self.STATE_ROUND_WON):
            timer_ratio = max(0.0, min(1.0, self.time_left / self.time_limit))
            self._draw_translucent_pie_timer(
                surface,
                width // 2,
                height // 2,
                int(min(width, height) * 0.20),
                timer_ratio
            )

        # 4. NIVEL Y PUNTAJE SUPERPUESTOS SOBRE EL MAPA
        self._draw_superimposed_hud(surface, width, height)

    # =========================================================================
    # VENTANA 2: PANTALLA DE INSPECCIÓN Y MONITOREO (TERAPEUTA / OPERADOR)
    # =========================================================================
    def render_inspector(self, surface: pygame.Surface, is_emulator: bool = True):
        """
        Renderiza el panel de monitoreo e inspección clínica para el operador/terapeuta:
          - Telemetría exacta por cuadrante (altura en mm, umbral objetivo, % de progreso).
          - Estadísticas clínicas de rehabilitación: velocidad media, simetría motora Izq vs Der,
            y balance de fuerza Acumular (Rojo) vs Excavar (Verde).
          - Historial de las últimas rondas y estado de los sockets UDP/OSC.
        """
        w, h = surface.get_size()
        surface.fill((16, 20, 28))

        font_title = pygame.font.SysFont("Arial", 16, bold=True)
        font_sec = pygame.font.SysFont("Arial", 13, bold=True)
        font_body = pygame.font.SysFont("Arial", 12)
        font_mono = pygame.font.SysFont("DejaVu Sans Mono", 11, bold=True)

        pad = 14
        y_cursor = pad

        # --- ENCABEZADO DEL MONITOR ---
        header_rect = pygame.Rect(pad, y_cursor, w - pad * 2, 42)
        pygame.draw.rect(surface, (26, 34, 48), header_rect, border_radius=8)
        pygame.draw.rect(surface, (55, 75, 105), header_rect, 1, border_radius=8)

        title_s = font_title.render("MONITOR DE INSPECCIÓN Y TELEMETRÍA CLÍNICA", True, (235, 245, 255))
        surface.blit(title_s, (header_rect.x + 12, header_rect.y + 11))

        mode_badge = "EMULADOR LOCAL" if is_emulator else "BRIDGE UDP :7000/:7001"
        badge_col = (245, 170, 30) if is_emulator else (0, 200, 110)
        badge_s = font_sec.render(mode_badge, True, badge_col)
        surface.blit(badge_s, (header_rect.right - badge_s.get_width() - 12, header_rect.y + 13))

        y_cursor += 52

        # --- SECCIÓN 1: INSPECTOR DE RELIEVE POR CUADRANTE (EN MILÍMETROS) ---
        sec1_title = font_sec.render("1. INSPECCIÓN FÍSICA DE CUADRANTES (TIEMPO REAL)", True, (0, 195, 235))
        surface.blit(sec1_title, (pad, y_cursor))
        y_cursor += 22

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

                # Etiqueta Q y altura en mm
                q_lbl = f"Q{idx + 1} {'[OBJETIVO]' if is_target else ''}"
                surface.blit(font_sec.render(q_lbl, True, (255, 255, 255) if is_target else (160, 180, 205)), (cell_r.x + 8, cell_r.y + 6))

                mm_str = f"Altura: {curr_h:+.1f} mm"
                mm_col = (255, 110, 110) if curr_h < -7.0 else ((100, 235, 140) if curr_h > 7.0 else (180, 220, 250))
                surface.blit(font_mono.render(mm_str, True, mm_col), (cell_r.x + 8, cell_r.y + 26))

                if is_target:
                    prog = self._get_target_progress(curr_h)
                    act_word = "PONER (Rojo)" if self.target_action == "ELEVATE" else "SACAR (Verde)"
                    meta_str = f"{act_word} -> {self.target_threshold:+.0f} mm ({int(prog * 100)}%)"
                    surface.blit(font_body.render(meta_str, True, (255, 220, 110)), (cell_r.x + 8, cell_r.y + 46))

                    # Barra de progreso de la celda objetivo
                    bar_r = pygame.Rect(cell_r.x + 8, cell_r.bottom - 14, cell_r.width - 16, 8)
                    pygame.draw.rect(surface, (15, 20, 28), bar_r, border_radius=4)
                    fill_r = pygame.Rect(bar_r.x, bar_r.y, int(bar_r.width * prog), bar_r.height)
                    pygame.draw.rect(surface, border_c, fill_r, border_radius=4)
                else:
                    flat_ok = abs(curr_h) < 7.0
                    st_str = "Estado: NIVELADO" if flat_ok else "Estado: DESNIVELADO"
                    surface.blit(font_body.render(st_str, True, (110, 205, 145) if flat_ok else (240, 165, 70)), (cell_r.x + 8, cell_r.y + 46))

        y_cursor += grid_box_h + 14

        # --- SECCIÓN 2: MÉTRICAS CLÍNICAS Y BIOMECÁNICAS DE LA SESIÓN ---
        sec2_title = font_sec.render("2. INDICADORES CLÍNICOS DE REHABILITACIÓN MOTRIZ", True, (0, 195, 235))
        surface.blit(sec2_title, (pad, y_cursor))
        y_cursor += 22

        stats_box_h = 112
        stats_box = pygame.Rect(pad, y_cursor, w - pad * 2, stats_box_h)
        pygame.draw.rect(surface, (22, 28, 38), stats_box, border_radius=8)
        pygame.draw.rect(surface, (50, 65, 88), stats_box, 1, border_radius=8)

        rounds = self.metrics.session.rounds
        won_rounds = [r for r in rounds if r.success]
        avg_time = (sum(r.time_taken_sec for r in won_rounds) / len(won_rounds)) if won_rounds else 0.0

        # Simetría izquierda vs derecha (columnas pares vs impares)
        left_times = [r.time_taken_sec for r in won_rounds if (r.target_quadrant % self.cols) < (self.cols / 2)]
        right_times = [r.time_taken_sec for r in won_rounds if (r.target_quadrant % self.cols) >= (self.cols / 2)]
        avg_left = (sum(left_times) / len(left_times)) if left_times else 0.0
        avg_right = (sum(right_times) / len(right_times)) if right_times else 0.0

        # Desempeño por tipo de esfuerzo (Poner/Acumular vs Sacar/Excavar)
        elev_times = [r.time_taken_sec for r in won_rounds if r.target_action == "ELEVATE"]
        dig_times = [r.time_taken_sec for r in won_rounds if r.target_action == "DIG"]
        avg_elev = (sum(elev_times) / len(elev_times)) if elev_times else 0.0
        avg_dig = (sum(dig_times) / len(dig_times)) if dig_times else 0.0

        col1_x = stats_box.x + 12
        col2_x = stats_box.x + int(stats_box.width * 0.46)
        sy = stats_box.y + 10

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
            "UDP: TX->127.0.0.1:7001 | RX<-:7000",
        ]

        for i in range(4):
            surface.blit(font_body.render(metrics_left[i], True, (220, 230, 245)), (col1_x, sy + i * 24))
            surface.blit(font_body.render(metrics_right[i], True, (195, 220, 250)), (col2_x, sy + i * 24))

        y_cursor += stats_box_h + 14

        # --- SECCIÓN 3: HISTORIAL DE RONDAS RECIENTES ---
        sec3_title = font_sec.render("3. REGISTRO DE RONDAS RECIENTES", True, (0, 195, 235))
        surface.blit(sec3_title, (pad, y_cursor))
        y_cursor += 22

        hist_h = max(70, h - y_cursor - 36)
        hist_box = pygame.Rect(pad, y_cursor, w - pad * 2, hist_h)
        pygame.draw.rect(surface, (22, 28, 38), hist_box, border_radius=8)
        pygame.draw.rect(surface, (50, 65, 88), hist_box, 1, border_radius=8)

        hdr = "RONDA  CELDA  ACCIÓN         META      FINAL      TIEMPO   ESTADO"
        surface.blit(font_mono.render(hdr, True, (140, 165, 195)), (hist_box.x + 12, hist_box.y + 8))
        pygame.draw.line(surface, (50, 65, 88), (hist_box.x + 8, hist_box.y + 28), (hist_box.right - 8, hist_box.y + 28), 1)

        recent = rounds[-5:]
        for idx_r, rm in enumerate(reversed(recent)):
            ry = hist_box.y + 34 + idx_r * 20
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

        # --- PIE DE CONTROLES DEL OPERADOR ---
        ctrl_txt = "[TAB]: Vista Monitor/Proyector | [ESPACIO]: Iniciar | [R]: Aplanar | [G]: Exportar CSV"
        ctrl_s = font_body.render(ctrl_txt, True, (145, 165, 190))
        surface.blit(ctrl_s, (w // 2 - ctrl_s.get_width() // 2, h - 22))

    def _draw_translucent_pie_timer(self, surface: pygame.Surface, cx: int, cy: int, radius: int, ratio: float):
        overlay = pygame.Surface((radius * 2 + 10, radius * 2 + 10), pygame.SRCALPHA)
        ocx, ocy = radius + 5, radius + 5

        pygame.draw.circle(overlay, (0, 0, 0, 35), (ocx, ocy), radius)

        if ratio > 0.001:
            pie_color = (255, 255, 255, 75) if ratio > 0.25 else (255, 235, 80, 95)

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
