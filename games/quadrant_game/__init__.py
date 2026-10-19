"""
Módulo Caja Negra del Juego de Rehabilitación por Cuadrantes ('quadrant_game').

Recibe sus dependencias (entrada de alturas y salida de proyección) por
Inyección de Dependencias a través de 'create_game(...)'.
"""
from __future__ import annotations
import os
from core.contracts import ISandInputPort, IProjectionOutputPort, ISandboxGame
from .config_manager import ConfigManager
from .game import QuadrantTherapyGame


def create_game(
    input_port: ISandInputPort,
    output_port: IProjectionOutputPort,
    patient_id: str = "PACIENTE_01",
    env_file: str = "default.env",
) -> ISandboxGame:
    """
    Fábrica de Inyección de Dependencias del juego de cuadrantes.
    Configura los puertos de red según el perfil .env del juego y retorna
    la instancia de 'QuadrantTherapyGame' lista para ser ejecutada por el Runner.
    """
    game_dir = os.path.dirname(os.path.abspath(__file__))
    config_mgr = ConfigManager(configs_dir=os.path.join(game_dir, "configs"))
    config_mgr.load_env(env_file)
    cfg = config_mgr.config

    output_port.reconfigure_endpoint(cfg.OSC_HOST, cfg.OSC_TX_PORT)

    return QuadrantTherapyGame(
        input_port=input_port,
        output_port=output_port,
        config_mgr=config_mgr,
        patient_id=patient_id,
    )


__all__ = ["QuadrantTherapyGame", "ConfigManager", "create_game"]
