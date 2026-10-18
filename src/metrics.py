import csv
import json
import os
import time
from dataclasses import asdict, dataclass, field

@dataclass
class RoundMetric:
    round_number: int
    target_quadrant: int
    target_action: str          # "ELEVATE" o "DIG"
    target_threshold_mm: float
    final_height_mm: float
    time_limit_sec: float
    time_taken_sec: float
    success: bool
    score_awarded: int
    reaction_time_sec: float = 0.0

@dataclass
class SessionData:
    patient_id: str
    timestamp: str
    rounds_completed: int = 0
    total_score: int = 0
    rounds: list[RoundMetric] = field(default_factory=list)

class TherapyMetricsManager:
    """
    Gestiona el registro de desempeño clínico y motor de los pacientes.
    Permite calcular estadísticas objetivas para terapeutas y exportar reportes.
    """
    def __init__(self, patient_id: str = "PACIENTE_01", output_dir: str = "records"):
        self.patient_id = patient_id
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.session = SessionData(
            patient_id=patient_id,
            timestamp=time.strftime("%Y-%m-%d_%H-%M-%S")
        )

    def record_round(self, metric: RoundMetric):
        self.session.rounds.append(metric)
        if metric.success:
            self.session.rounds_completed += 1
        self.session.total_score += metric.score_awarded

    def export_session(self):
        """Exporta la sesión actual a formatos JSON y CSV."""
        base_filename = os.path.join(
            self.output_dir,
            f"sesion_{self.patient_id}_{self.session.timestamp}"
        )

        # 1. Guardar JSON completo
        json_path = f"{base_filename}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(asdict(self.session), f, indent=4, ensure_ascii=False)

        # 2. Guardar CSV tabular para hojas de cálculo
        csv_path = f"{base_filename}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Ronda", "Cuadrante", "Accion", "Umbral_mm", "Altura_Final_mm",
                "Tiempo_Limite_s", "Tiempo_Empleado_s", "Exito", "Puntos"
            ])
            for r in self.session.rounds:
                writer.writerow([
                    r.round_number, r.target_quadrant, r.target_action,
                    r.target_threshold_mm, round(r.final_height_mm, 1),
                    r.time_limit_sec, round(r.time_taken_sec, 2),
                    1 if r.success else 0, r.score_awarded
                ])

        print(f"[Metrics] Reportes clínicos exportados exitosamente en:\n  - {json_path}\n  - {csv_path}")
