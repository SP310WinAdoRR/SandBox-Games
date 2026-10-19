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
    - Cuadrícula a pantalla completa sin huecos ni márgenes.
    - Código de color sin conflictos:
        * Cian: Estado neutro / equilibrado.
        * Rojo: Poner / acumular arena (ELEVATE).
        * Verde: Sacar / excavar arena (DIG).
        * Dorado / Blanco brillante: Señal de umbral alcanzado (éxito).
    - Temporizador central tipo torta con alta traslucidad.
    - Nivel y puntaje superpuestos sobre el mapa sin ocupar espacio dedicado.
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

        # Paleta cromática sin conflicto entre Rojo (poner) y Verde (sacar)
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

        # Escalado progresivo de cuadrantes (4 -> 8 -> 16)
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
        self.bridge.send_hud_title(f"NIVEL {self.round_number}")

    def _start_active_phase(self):
        self.state = self.STATE_ROUND_ACTIVE
        self.time_left = self.time_limit
        self.round_start_time = time.time()

    def _get_target_progress(self, current_h: float) -> float:
        """Retorna el progreso normalizado [0.0, 1.0] hacia el umbral de altura."""
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
                    time_taken_sec=time_limit_sec if (time_limit_sec := self.time_limit) else 0.0,
                    success=False,
                    score_awarded=0
                ))
                self.metrics.export_session()

        elif self.state == self.STATE_ROUND_WON:
            if now - self.round_win_time > 1.2:
                self.next_round()

    def handle_input(self, event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                if self.state in (self.STATE_WELCOME, self.STATE_GAME_OVER):
                    self.start_new_game()
                elif self.state == self.STATE_PREPARE_FLAT:
                    self._start_active_phase()
            elif event.key == pygame.K_r:
                self.provider.reset()

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
                    # Meta alcanzada: destello dorado/blanco que se funde hacia el cian neutro
                    elapsed_win = min(1.0, (now - self.round_win_time) / 1.2)
                    flash_col = _lerp_color(self.palette["target_success"], self.palette["cyan_base"], elapsed_win)
                    pygame.draw.rect(surface, flash_col, cell_rect)

                elif self.state == self.STATE_ROUND_ACTIVE and is_target:
                    # Rojo = Poner arena (ELEVATE) | Verde = Sacar arena (DIG)
                    action_col = (
                        self.palette["target_elevate"]
                        if self.target_action == "ELEVATE"
                        else self.palette["target_dig"]
                    )
                    progress = self._get_target_progress(curr_h)

                    # El fondo del cuadrante es Cian neutro y el color de acción (Rojo o Verde)
                    # se va reduciendo/cerrando proporcionalmente al progreso hasta desaparecer en Cian,
                    # a la vez que aumenta su brillo hacia blanco/dorado al acercarse al 100%.
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
                    # En fase de nivelación: si sobra arena (> +7mm) muestra leve matiz verde (sacar),
                    # si falta arena (< -7mm) muestra leve matiz rojo (poner), guiando sin números
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

    def _draw_translucent_pie_timer(self, surface: pygame.Surface, cx: int, cy: int, radius: int, ratio: float):
        overlay = pygame.Surface((radius * 2 + 10, radius * 2 + 10), pygame.SRCALPHA)
        ocx, ocy = radius + 5, radius + 5

        # Sombra circular muy sutil
        pygame.draw.circle(overlay, (0, 0, 0, 35), (ocx, ocy), radius)

        if ratio > 0.001:
            # Alta traslucidad para dejar ver claramente los cuadrantes y líneas debajo
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

        # Posicionados dentro del margen seguro interior para evitar pérdidas por desborde del proyector
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
