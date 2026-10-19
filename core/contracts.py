"""
Contratos e Interfaces (Puertos) para Inversión de Dependencias.

Estructura de desacoplamiento para los módulos dentro de 'games/<nombre_juego>/':
  1. Lectura de datos de entrada a través de 'ISandInputPort'.
  2. Emisión de órdenes gráficas y de proyección a través de 'IProjectionOutputPort'.
  3. Renderizado de interfaz sobre superficies 'pygame.Surface' provistas por el ejecutor.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
import pygame


class ISandInputPort(ABC):
    """
    Puerto de Entrada:
    Provee las alturas actuales de la arena (en mm), abstrayendo la fuente de datos
    (Kinect vía UDP/OSC, simulación local o generadores sintéticos).
    """
    @abstractmethod
    def get_heights(self) -> list[float]:
        """Retorna una lista con la elevación media (en mm) de cada celda."""
        pass

    @abstractmethod
    def set_grid_size(self, cols: int, rows: int) -> None:
        """Notifica al proveedor que la cuadrícula lógica cambió de dimensiones."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reinicia o aplana el estado de referencia si el proveedor lo soporta."""
        pass


class IProjectionOutputPort(ABC):
    """
    Puerto de Salida:
    Permite al juego emitir estados visuales hacia el proyector de la caja de arena,
    desacoplado de la implementación de red o del protocolo de transmisión.
    """
    @abstractmethod
    def reconfigure_endpoint(self, host: str, port: int) -> None:
        """Actualiza el destino de red si el perfil .env modifica host/puerto."""
        pass

    @abstractmethod
    def send_grid_setup(self, cols: int, rows: int) -> None:
        pass

    @abstractmethod
    def send_cell_state(
        self,
        index: int,
        r: int,
        g: int,
        b: int,
        alpha: float = 1.0,
        text: str = "",
    ) -> None:
        pass

    @abstractmethod
    def send_cell_progress(
        self,
        index: int,
        base_col: tuple[int, int, int],
        inner_col: tuple[int, int, int],
        inner_scale: float,
    ) -> None:
        pass

    @abstractmethod
    def send_hud_timer(
        self,
        progress: float,
        r: int = 255,
        g: int = 255,
        b: int = 255,
        alpha: int = 75,
    ) -> None:
        pass

    @abstractmethod
    def send_hud_stats(self, round_num: int, score: int) -> None:
        pass

    @abstractmethod
    def send_hud_title(self, text: str) -> None:
        pass

    @abstractmethod
    def send_round_clear(self) -> None:
        pass


class ISandboxGame(ABC):
    """
    Interfaz base para los módulos de juego dentro de 'games/'.
    Define los métodos requeridos para la actualización lógica, procesamiento
    de eventos y renderizado de interfaces.
    """
    @property
    @abstractmethod
    def title(self) -> str:
        """Título descriptivo del juego para la ventana del operador."""
        pass

    @property
    @abstractmethod
    def grid_shape(self) -> tuple[int, int]:
        """Retorna (cols, rows) actuales del juego."""
        pass

    @abstractmethod
    def get_network_config(self) -> tuple[str, int, int]:
        """Retorna (host, rx_port, tx_port) requeridos por la configuración del juego."""
        pass

    @abstractmethod
    def can_exit_on_escape(self) -> bool:
        """Indica si la tecla ESC puede cerrar la aplicación o si está editando un campo."""
        pass

    @abstractmethod
    def handle_key_event(self, event: pygame.event.Event) -> None:
        """Procesa eventos de teclado inyectados por el Runner."""
        pass

    @abstractmethod
    def handle_inspector_click(self, mx: int, my: int) -> bool:
        """Procesa un clic izquierdo en la ventana de telemetría. Retorna True si fue consumido."""
        pass

    @abstractmethod
    def update(self, dt: float) -> None:
        """Actualiza un frame de lógica del juego leyendo ISandInputPort y emitiendo a IProjectionOutputPort."""
        pass

    @abstractmethod
    def render_inspector(self, surface: pygame.Surface, is_emulator: bool = False) -> None:
        """Renderiza la interfaz de monitoreo/configuración sobre la superficie inyectada."""
        pass

    @abstractmethod
    def render_projection(self, surface: pygame.Surface) -> None:
        """Renderiza la vista de proyección sobre una superficie inyectada (cuando aplica)."""
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Llamado al cerrar la aplicación para guardar/exportar datos de la sesión."""
        pass
