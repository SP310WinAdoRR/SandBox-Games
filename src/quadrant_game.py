import math
import random
import time
import pygame

from .data_provider import BaseDataProvider, EmulatorDataProvider
from .bridge_client import MagicSandBridgeClient
from .metrics import RoundMetric, TherapyMetricsManager


class QuadrantTherapyGame:
    """
    Videojuego de modulación de alturas por cuadrantes para rehabilitación motriz.
    Basado en las especificaciones de 'ARSandbox2.pdf'.
    """

    # Estados de la máquina de juego
    STATE_WELCOME = "WELCOME"
    STATE_PREPARE_FLAT = "PREPARE_FLAT"
    STATE_ROUND_ACTIVE = "ROUND_ACTIVE"
    STATE_ROUND_WON = "ROUND_WON"
    STATE_GAME_OVER = "GAME_OVER"

    def __init__(self, data_provider: BaseDataProvider, bridge: MagicSandBridgeClient = None, patient_id: str = "PACIENTE_01"):
        self.provider = data_provider
        self.bridge = bridge or MagicSandBridgeClient()
        self.metrics = TherapyMetricsManager(patient_id=patient_id)

        # Dimensiones de la cuadrícula (comienza 2x2 = 4 cuadrantes)
        self.cols = 2
        self.rows = 2
        self.provider.set_grid_size(self.cols, self.rows)

        # Estado del juego
        self.state = self.STATE_WELCOME
        self.round_number = 0
        self.score = 0
        self.target_quadrant = 0
        self.target_action = "ELEVATE"   # "ELEVATE" (+mm) o "DIG" (-mm)
        self.target_threshold = 30.0     # mm
        self.time_limit = 15.0           # segundos
        self.time_left = 15.0
        self.round_start_time = 0.0
        self.round_win_time = 0.0
        self.last_update_time = time.time()

        # Configuración visual
        self.palette = {
            "bg": (15, 18, 25),
            "grid_border": (60, 75, 100),
            "cell_idle": (28, 36, 52),
            "cell_elevate": (0, 180, 216),    # Azul cian brillante para elevar
            "cell_dig": (247, 127, 0),        # Naranja vivo para excavar
            "text": (240, 245, 255),
            "timer_bar": (46, 196, 182),
            "timer_danger": (230, 57, 70),
            "accent": (255, 209, 102),
        }

    def start_new_game(self):
        self.round_number = 0
        self.score = 0
        self.next_round()

    def next_round(self):
        self.round_number += 1
        num_cells = self.cols * self.rows

        # Dificultad adaptativa inspirada en roguelite / Balatro
        if self.round_number <= 3:
            # Rondas iniciales: acumulación simple de arena
            self.target_action = "ELEVATE"
            self.target_threshold = 28.0 + (self.round_number * 3.0)
            self.time_limit = max(10.0, 16.0 - (self.round_number * 1.0))
        elif self.round_number <= 6:
            # Rondas medias: alternar excavación y acumulación
            self.target_action = random.choice(["ELEVATE", "DIG"])
            self.target_threshold = 35.0 if self.target_action == "ELEVATE" else -25.0
            self.time_limit = 12.0
        else:
            # Rondas avanzadas: mayor precisión y menor tiempo
            self.target_action = random.choice(["ELEVATE", "DIG"])
            self.target_threshold = 42.0 if self.target_action == "ELEVATE" else -32.0
            self.time_limit = max(7.0, 11.0 - (self.round_number * 0.4))

        self.target_quadrant = random.randint(0, num_cells - 1)
        self.state = self.STATE_PREPARE_FLAT

        # Informar a Magic Sand (proyector)
        self.bridge.send_grid_setup(self.cols, self.rows)
        self.bridge.send_hud_title(f"RONDA {self.round_number}: APLANAR ARENA")

    def _start_active_phase(self):
        self.state = self.STATE_ROUND_ACTIVE
        self.time_left = self.time_limit
        self.round_start_time = time.time()

        action_text = "ACUMULA ARENA" if self.target_action == "ELEVATE" else "EXCAVA ARENA"
        sign = "+" if self.target_threshold > 0 else ""
        self.bridge.send_hud_title(f"Q{self.target_quadrant + 1}: {action_text} ({sign}{int(self.target_threshold)} mm)")

    def update(self):
        now = time.time()
        dt = now - self.last_update_time
        self.last_update_time = now

        # 1. Obtener lecturas de altura en tiempo real
        heights = self.provider.get_heights()
        if not heights or self.target_quadrant >= len(heights):
            return

        current_h = heights[self.target_quadrant]

        # 2. Lógica según estado
        if self.state == self.STATE_PREPARE_FLAT:
            # Verifica si la arena está razonablemente nivelada (entre -5mm y +5mm)
            is_flat = all(abs(h) < 7.0 for h in heights)
            if is_flat:
                self._start_active_phase()

        elif self.state == self.STATE_ROUND_ACTIVE:
            self.time_left -= dt
            timer_ratio = max(0.0, self.time_left / self.time_limit)

            # Notificar progreso al HUD proyectado
            t_color = self.palette["timer_danger"] if timer_ratio < 0.25 else self.palette["timer_bar"]
            self.bridge.send_hud_timer(timer_ratio, *t_color)

            # --- VALIDACIÓN CONTINUA EN TIEMPO REAL ---
            success = False
            if self.target_action == "ELEVATE" and current_h >= self.target_threshold:
                success = True
            elif self.target_action == "DIG" and current_h <= self.target_threshold:
                success = True

            if success:
                # ¡Ronda superada inmediatamente!
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

                self.bridge.send_hud_title(f"¡EXCELENTE! +{points} pts")
                return

            # Tiempo agotado -> Game Over
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
                self.bridge.send_hud_title("FIN DE SESIÓN - TIEMPO AGOTADO")

        elif self.state == self.STATE_ROUND_WON:
            # Pausa de 1.8 segundos para celebrar y continuar
            if now - self.round_win_time > 1.8:
                self.next_round()

    def handle_input(self, event):
        """Maneja eventos de teclado y ratón (para el emulador)."""
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                if self.state in (self.STATE_WELCOME, self.STATE_GAME_OVER):
                    self.start_new_game()
                elif self.state == self.STATE_PREPARE_FLAT:
                    # Permite saltar la fase de aplanado manualmente
                    self._start_active_phase()
            elif event.key == pygame.K_r:
                self.provider.reset()

    def render(self, surface: pygame.Surface, is_emulator: bool = True):
        """Dibuja la interfaz completa del juego sobre la superficie de Pygame."""
        width, height = surface.get_size()
        surface.fill(self.palette["bg"])

        font_large = pygame.font.SysFont("Arial", int(height * 0.055), bold=True)
        font_med = pygame.font.SysFont("Arial", int(height * 0.035), bold=True)
        font_small = pygame.font.SysFont("Arial", int(height * 0.024))

        # --- ÁREA SUPERIOR: BARRA DE TIEMPO Y ESTADÍSTICAS ---
        hud_height = int(height * 0.14)
        pygame.draw.rect(surface, (20, 25, 36), (0, 0, width, hud_height))
        pygame.draw.line(surface, self.palette["grid_border"], (0, hud_height), (width, hud_height), 2)

        # Textos de Score y Ronda
        score_surf = font_med.render(f"PUNTAJE: {self.score}", True, self.palette["accent"])
        round_surf = font_med.render(f"RONDA: {self.round_number}", True, self.palette["text"])
        surface.blit(score_surf, (25, int(hud_height * 0.2)))
        surface.blit(round_surf, (width - round_surf.get_width() - 25, int(hud_height * 0.2)))

        # Barra de tiempo
        timer_ratio = max(0.0, self.time_left / self.time_limit) if self.state == self.STATE_ROUND_ACTIVE else 1.0
        bar_w = int(width * 0.45)
        bar_h = 16
        bar_x = (width - bar_w) // 2
        bar_y = int(hud_height * 0.65)
        pygame.draw.rect(surface, (40, 50, 70), (bar_x, bar_y, bar_w, bar_h), border_radius=8)
        fill_color = self.palette["timer_danger"] if timer_ratio < 0.25 else self.palette["timer_bar"]
        pygame.draw.rect(surface, fill_color, (bar_x, bar_y, int(bar_w * timer_ratio), bar_h), border_radius=8)

        # --- ÁREA INFERIOR: MALLA DE CUADRANTES DE LA ARENA ---
        grid_top = hud_height + 15
        grid_margin = 25
        grid_w = width - (grid_margin * 2)
        grid_h = height - grid_top - (50 if is_emulator else 25)

        cell_w = grid_w // self.cols
        cell_h = grid_h // self.rows
        heights = self.provider.get_heights()

        for r in range(self.rows):
            for c in range(self.cols):
                idx = r * self.cols + c
                cell_x = grid_margin + (c * cell_w)
                cell_y = grid_top + (r * cell_h)
                cell_rect = pygame.Rect(cell_x + 6, cell_y + 6, cell_w - 12, cell_h - 12)

                is_target = (self.state in (self.STATE_ROUND_ACTIVE, self.STATE_ROUND_WON)) and (idx == self.target_quadrant)
                curr_h = heights[idx] if idx < len(heights) else 0.0

                # Color de fondo de la celda
                if is_target:
                    target_color = self.palette["cell_elevate"] if self.target_action == "ELEVATE" else self.palette["cell_dig"]
                    # Efecto de pulso suave
                    pulse = 0.85 + (0.15 * math.sin(time.time() * 6.0))
                    c_rgb = tuple(int(ch * pulse) for ch in target_color)
                else:
                    c_rgb = self.palette["cell_idle"]

                pygame.draw.rect(surface, c_rgb, cell_rect, border_radius=12)
                border_color = (255, 255, 255) if is_target else self.palette["grid_border"]
                border_thick = 4 if is_target else 2
                pygame.draw.rect(surface, border_color, cell_rect, border_thick, border_radius=12)

                # Información dentro de la celda
                num_text = font_large.render(f"Q{idx + 1}", True, (255, 255, 255) if is_target else (120, 140, 170))
                surface.blit(num_text, (cell_rect.x + 18, cell_rect.y + 14))

                h_str = f"{curr_h:+.1f} mm"
                h_text = font_med.render(h_str, True, self.palette["text"])
                surface.blit(h_text, (cell_rect.centerx - (h_text.get_width() // 2), cell_rect.centery - 10))

                if is_target:
                    action_lbl = f"META: {self.target_threshold:+.0f} mm"
                    act_text = font_small.render(action_lbl, True, self.palette["accent"])
                    surface.blit(act_text, (cell_rect.centerx - (act_text.get_width() // 2), cell_rect.centery + 30))

        # --- OVERLAYS SEGÚN ESTADO ---
        if self.state == self.STATE_WELCOME:
            self._draw_modal_box(surface, "TERAPIA MOTRIZ - CAJA DE ARENA AR",
                                 "Presiona [ESPACIO] para comenzar la sesión",
                                 font_large, font_med)
        elif self.state == self.STATE_PREPARE_FLAT:
            self._draw_modal_box(surface, "FASE DE PREPARACIÓN",
                                 "Aplana la arena para nivelar el terreno (o presiona [ESPACIO])",
                                 font_large, font_med, color=(40, 120, 180))
        elif self.state == self.STATE_ROUND_WON:
            self._draw_banner(surface, f"¡RONDA {self.round_number} COMPLETADA!", font_large, color=(46, 196, 182))
        elif self.state == self.STATE_GAME_OVER:
            self._draw_modal_box(surface, "SESIÓN FINALIZADA",
                                 f"Rondas superadas: {self.metrics.session.rounds_completed} | Puntaje: {self.score}\nPresiona [ESPACIO] para reiniciar",
                                 font_large, font_med, color=(200, 50, 60))

        # Instrucciones del emulador en la parte inferior
        if is_emulator:
            footer_text = font_small.render(
                "MODO EMULADOR: [Clic Izquierdo]: Subir arena  |  [Clic Derecho]: Excavar  |  [R]: Aplanar arena",
                True, (140, 160, 190)
            )
            surface.blit(footer_text, (width // 2 - footer_text.get_width() // 2, height - 30))

    def _draw_modal_box(self, surface, title, subtitle, font_title, font_sub, color=(20, 30, 48)):
        w, h = surface.get_size()
        box_w = int(w * 0.75)
        box_h = int(h * 0.35)
        box_rect = pygame.Rect((w - box_w) // 2, (h - box_h) // 2, box_w, box_h)

        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        surface.blit(overlay, (0, 0))

        pygame.draw.rect(surface, color, box_rect, border_radius=16)
        pygame.draw.rect(surface, (255, 255, 255), box_rect, 3, border_radius=16)

        t_surf = font_title.render(title, True, (255, 255, 255))
        surface.blit(t_surf, (box_rect.centerx - t_surf.get_width() // 2, box_rect.y + 40))

        lines = subtitle.split("\n")
        y_offset = box_rect.y + 110
        for line in lines:
            s_surf = font_sub.render(line, True, self.palette["accent"])
            surface.blit(s_surf, (box_rect.centerx - s_surf.get_width() // 2, y_offset))
            y_offset += 35

    def _draw_banner(self, surface, message, font, color):
        w, h = surface.get_size()
        banner_rect = pygame.Rect(0, int(h * 0.42), w, int(h * 0.16))
        pygame.draw.rect(surface, color, banner_rect)
        pygame.draw.line(surface, (255, 255, 255), (0, banner_rect.top), (w, banner_rect.top), 2)
        pygame.draw.line(surface, (255, 255, 255), (0, banner_rect.bottom), (w, banner_rect.bottom), 2)

        text_surf = font.render(message, True, (0, 20, 30))
        surface.blit(text_surf, (w // 2 - text_surf.get_width() // 2, banner_rect.centery - text_surf.get_height() // 2))
