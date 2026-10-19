import os
from dataclasses import dataclass, fields


@dataclass
class GameConfig:
    """
    Almacena los parámetros de configuración del juego terapéutico,
    incluyendo categorías predefinidas y variables numéricas avanzadas.
    """
    # Categorías de configuración simplificada ("BAJA", "MEDIA", "ALTA", etc.)
    FORCE_CATEGORY: str = "MEDIA"       # BAJA | MEDIA | ALTA
    TIME_CATEGORY: str = "MEDIA"        # BAJA | MEDIA | ALTA
    GRID_CATEGORY: str = "MEDIA"        # BAJA | MEDIA | ALTA
    ACTION_CATEGORY: str = "AMBOS"      # PONER | SACAR | AMBOS
    TOLERANCE_CATEGORY: str = "MEDIA"   # BAJA | MEDIA | ALTA
    BIMANUAL_CATEGORY: str = "MIXTO"    # UNIMANUAL | MIXTO | BIMANUAL

    # Variables numéricas específicas (Modo Avanzado)
    INITIAL_COLS: int = 2
    INITIAL_ROWS: int = 2
    MAX_GRID_STAGE: int = 3
    MAX_SIMULTANEOUS_TARGETS: int = 2
    HOLD_TIME_SEC: float = 0.5
    BASE_TIME_LIMIT_SEC: float = 15.0
    MIN_TIME_LIMIT_SEC: float = 7.0
    TIME_DECAY_PER_ROUND: float = 0.45
    WIN_PAUSE_SEC: float = 1.2
    ELEVATE_THRESHOLD_MM: float = 32.0
    DIG_THRESHOLD_MM: float = -25.0
    THRESHOLD_STEP_PER_ROUND_MM: float = 1.5
    FLAT_TOLERANCE_MM: float = 7.0
    PIE_TIMER_OPACITY: int = 75
    EMULATOR_RATE_MM_S: float = 55.0
    OSC_HOST: str = "127.0.0.1"
    OSC_RX_PORT: int = 7000
    OSC_TX_PORT: int = 7001


# Definición de metadatos de los campos numéricos para la UI del Modo Avanzado
ADVANCED_FIELDS_META = [
    ("BASE_TIME_LIMIT_SEC", "Tiempo Base por Ronda (s)", float, 1.0, 3.0, 120.0),
    ("MIN_TIME_LIMIT_SEC", "Tiempo Mínimo por Ronda (s)", float, 0.5, 2.0, 60.0),
    ("TIME_DECAY_PER_ROUND", "Reducción Tiempo / Nivel (s)", float, 0.1, 0.0, 5.0),
    ("HOLD_TIME_SEC", "Tiempo Estabilidad Meta (s)", float, 0.1, 0.0, 5.0),
    ("ELEVATE_THRESHOLD_MM", "Umbral Poner Arena (+mm)", float, 2.0, 5.0, 100.0),
    ("DIG_THRESHOLD_MM", "Umbral Sacar Arena (-mm)", float, 2.0, -100.0, -5.0),
    ("THRESHOLD_STEP_PER_ROUND_MM", "Aumento Umbral / Nivel (mm)", float, 0.5, 0.0, 15.0),
    ("FLAT_TOLERANCE_MM", "Tolerancia Nivelación (±mm)", float, 1.0, 2.0, 30.0),
    ("MAX_SIMULTANEOUS_TARGETS", "Metas Simultáneas Máx (1-4)", int, 1, 1, 4),
    ("INITIAL_COLS", "Columnas Iniciales", int, 1, 1, 8),
    ("INITIAL_ROWS", "Filas Iniciales", int, 1, 1, 8),
    ("MAX_GRID_STAGE", "Etapa Máx. Cuadrícula (1-3)", int, 1, 1, 3),
    ("WIN_PAUSE_SEC", "Pausa al Superar Ronda (s)", float, 0.2, 0.2, 10.0),
    ("PIE_TIMER_OPACITY", "Opacidad Cronómetro (20-220)", int, 10, 20, 220),
    ("OSC_RX_PORT", "Puerto UDP Recepción Alturas", int, 1, 1024, 65535),
    ("OSC_TX_PORT", "Puerto UDP Envío Proyección", int, 1, 1024, 65535),
]

# Definición de las categorías del Modo Fácil
EASY_CATEGORIES_META = [
    (
        "FORCE_CATEGORY",
        "Exigencia de Fuerza (Altura)",
        [("BAJA", "Baja (+20/-15mm)"), ("MEDIA", "Media (+32/-25mm)"), ("ALTA", "Alta (+45/-35mm)")],
    ),
    (
        "TIME_CATEGORY",
        "Presión de Tiempo",
        [("BAJA", "Baja (22s)"), ("MEDIA", "Media (15s)"), ("ALTA", "Alta (10s)")],
    ),
    (
        "BIMANUAL_CATEGORY",
        "Coordinación (Metas Simultáneas)",
        [("UNIMANUAL", "Unimanual (1)"), ("MIXTO", "Progresivo (1->2)"), ("BIMANUAL", "Bimanual (2)")],
    ),
    (
        "GRID_CATEGORY",
        "Complejidad de Cuadrícula",
        [("BAJA", "Baja (Fija 2x2)"), ("MEDIA", "Media (4->8->16)"), ("ALTA", "Alta (Fija 4x4)")],
    ),
    (
        "ACTION_CATEGORY",
        "Gesto Terapéutico",
        [("PONER", "Solo Poner (Rojo)"), ("SACAR", "Solo Sacar (Verde)"), ("AMBOS", "Combinado")],
    ),
    (
        "TOLERANCE_CATEGORY",
        "Estabilidad y Nivelación",
        [("BAJA", "Baja (±12mm/0.2s)"), ("MEDIA", "Media (±7mm/0.5s)"), ("ALTA", "Alta (±4mm/1.0s)")],
    ),
]


class ConfigManager:
    """
    Gestiona la lectura, escritura y sincronización de archivos .env
    dentro de la carpeta 'configs/'.
    """
    def __init__(self, configs_dir: str | None = None):
        base_game_dir = os.path.dirname(os.path.abspath(__file__))
        self.configs_dir = configs_dir or os.path.join(base_game_dir, "configs")
        os.makedirs(self.configs_dir, exist_ok=True)
        self.default_file = "default.env"
        self.active_file = self.default_file
        self.config = GameConfig()

        # Garantizar que default.env exista siempre
        default_path = os.path.join(self.configs_dir, self.default_file)
        if not os.path.exists(default_path):
            self.save_env(self.default_file)
        else:
            self.load_env(self.default_file)

    def list_env_files(self) -> list[str]:
        files = [f for f in os.listdir(self.configs_dir) if f.endswith(".env")]
        files.sort(key=lambda x: (0 if x == "default.env" else 1, x.lower()))
        if not files:
            files = ["default.env"]
        return files

    def load_env(self, filename: str) -> bool:
        if not filename.endswith(".env"):
            filename += ".env"
        path = os.path.join(self.configs_dir, filename)
        if not os.path.exists(path):
            return False

        new_cfg = GameConfig()
        field_types = {f.name: f.type for f in fields(GameConfig)}

        with open(path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k in field_types:
                    ftype = field_types[k]
                    try:
                        if ftype in (int, "int"):
                            setattr(new_cfg, k, int(float(v)))
                        elif ftype in (float, "float"):
                            setattr(new_cfg, k, float(v))
                        else:
                            setattr(new_cfg, k, str(v))
                    except ValueError:
                        pass

        self.config = new_cfg
        self.active_file = filename
        return True

    def save_env(self, filename: str = None) -> str:
        target = filename or self.active_file
        if not target.endswith(".env"):
            target += ".env"
        path = os.path.join(self.configs_dir, target)

        lines = [
            "# ==============================================================================",
            f"# CONFIGURACIÓN SANDBOX GAMES ({target})",
            "# ==============================================================================",
            "",
            "# --- CATEGORÍAS MODO FÁCIL ---",
            f"FORCE_CATEGORY={self.config.FORCE_CATEGORY}",
            f"TIME_CATEGORY={self.config.TIME_CATEGORY}",
            f"BIMANUAL_CATEGORY={self.config.BIMANUAL_CATEGORY}",
            f"GRID_CATEGORY={self.config.GRID_CATEGORY}",
            f"ACTION_CATEGORY={self.config.ACTION_CATEGORY}",
            f"TOLERANCE_CATEGORY={self.config.TOLERANCE_CATEGORY}",
            "",
            "# --- PARÁMETROS NUMÉRICOS ESPECÍFICOS (MODO AVANZADO) ---",
            f"INITIAL_COLS={self.config.INITIAL_COLS}",
            f"INITIAL_ROWS={self.config.INITIAL_ROWS}",
            f"MAX_GRID_STAGE={self.config.MAX_GRID_STAGE}",
            f"MAX_SIMULTANEOUS_TARGETS={self.config.MAX_SIMULTANEOUS_TARGETS}",
            f"HOLD_TIME_SEC={self.config.HOLD_TIME_SEC:.2f}",
            f"BASE_TIME_LIMIT_SEC={self.config.BASE_TIME_LIMIT_SEC:.2f}",
            f"MIN_TIME_LIMIT_SEC={self.config.MIN_TIME_LIMIT_SEC:.2f}",
            f"TIME_DECAY_PER_ROUND={self.config.TIME_DECAY_PER_ROUND:.2f}",
            f"WIN_PAUSE_SEC={self.config.WIN_PAUSE_SEC:.2f}",
            f"ELEVATE_THRESHOLD_MM={self.config.ELEVATE_THRESHOLD_MM:.1f}",
            f"DIG_THRESHOLD_MM={self.config.DIG_THRESHOLD_MM:.1f}",
            f"THRESHOLD_STEP_PER_ROUND_MM={self.config.THRESHOLD_STEP_PER_ROUND_MM:.2f}",
            f"FLAT_TOLERANCE_MM={self.config.FLAT_TOLERANCE_MM:.1f}",
            f"PIE_TIMER_OPACITY={self.config.PIE_TIMER_OPACITY}",
            f"EMULATOR_RATE_MM_S={self.config.EMULATOR_RATE_MM_S:.1f}",
            f"OSC_HOST={self.config.OSC_HOST}",
            f"OSC_RX_PORT={self.config.OSC_RX_PORT}",
            f"OSC_TX_PORT={self.config.OSC_TX_PORT}",
            "",
        ]
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        self.active_file = target
        return target

    def reset_to_default(self):
        """Restablece la configuración actual a los valores predeterminados de default.env."""
        default_path = os.path.join(self.configs_dir, self.default_file)
        if os.path.exists(default_path):
            self.load_env(self.default_file)
        else:
            self.config = GameConfig()
            self.save_env(self.default_file)

    def apply_easy_category(self, category_key: str, value: str):
        """
        Traduce la selección de una categoría del Modo Fácil (BAJA, MEDIA, ALTA)
        en los valores numéricos específicos correspondientes.
        """
        setattr(self.config, category_key, value)

        if category_key == "FORCE_CATEGORY":
            if value == "BAJA":
                self.config.ELEVATE_THRESHOLD_MM = 20.0
                self.config.DIG_THRESHOLD_MM = -15.0
                self.config.THRESHOLD_STEP_PER_ROUND_MM = 1.0
            elif value == "MEDIA":
                self.config.ELEVATE_THRESHOLD_MM = 32.0
                self.config.DIG_THRESHOLD_MM = -25.0
                self.config.THRESHOLD_STEP_PER_ROUND_MM = 1.5
            elif value == "ALTA":
                self.config.ELEVATE_THRESHOLD_MM = 45.0
                self.config.DIG_THRESHOLD_MM = -35.0
                self.config.THRESHOLD_STEP_PER_ROUND_MM = 2.5

        elif category_key == "TIME_CATEGORY":
            if value == "BAJA":
                self.config.BASE_TIME_LIMIT_SEC = 22.0
                self.config.MIN_TIME_LIMIT_SEC = 10.0
                self.config.TIME_DECAY_PER_ROUND = 0.30
            elif value == "MEDIA":
                self.config.BASE_TIME_LIMIT_SEC = 15.0
                self.config.MIN_TIME_LIMIT_SEC = 7.0
                self.config.TIME_DECAY_PER_ROUND = 0.45
            elif value == "ALTA":
                self.config.BASE_TIME_LIMIT_SEC = 10.0
                self.config.MIN_TIME_LIMIT_SEC = 5.0
                self.config.TIME_DECAY_PER_ROUND = 0.65

        elif category_key == "BIMANUAL_CATEGORY":
            if value == "UNIMANUAL":
                self.config.MAX_SIMULTANEOUS_TARGETS = 1
            elif value == "MIXTO":
                self.config.MAX_SIMULTANEOUS_TARGETS = 2
            elif value == "BIMANUAL":
                self.config.MAX_SIMULTANEOUS_TARGETS = 2

        elif category_key == "GRID_CATEGORY":
            if value == "BAJA":
                self.config.INITIAL_COLS = 2
                self.config.INITIAL_ROWS = 2
                self.config.MAX_GRID_STAGE = 1
            elif value == "MEDIA":
                self.config.INITIAL_COLS = 2
                self.config.INITIAL_ROWS = 2
                self.config.MAX_GRID_STAGE = 3
            elif value == "ALTA":
                self.config.INITIAL_COLS = 4
                self.config.INITIAL_ROWS = 4
                self.config.MAX_GRID_STAGE = 3

        elif category_key == "TOLERANCE_CATEGORY":
            if value == "BAJA":
                self.config.FLAT_TOLERANCE_MM = 12.0
                self.config.HOLD_TIME_SEC = 0.2
            elif value == "MEDIA":
                self.config.FLAT_TOLERANCE_MM = 7.0
                self.config.HOLD_TIME_SEC = 0.5
            elif value == "ALTA":
                self.config.FLAT_TOLERANCE_MM = 4.0
                self.config.HOLD_TIME_SEC = 1.0

    def set_numeric_field(self, field_name: str, raw_val: str) -> bool:
        """Actualiza un campo numérico específico validando sus límites."""
        for fname, _, ftype, _, fmin, fmax in ADVANCED_FIELDS_META:
            if fname == field_name:
                try:
                    val = ftype(float(raw_val))
                    val = max(fmin, min(fmax, val))
                    if ftype is int:
                        val = int(val)
                    setattr(self.config, fname, val)
                    return True
                except ValueError:
                    return False
        return False

    def step_numeric_field(self, field_name: str, direction: int):
        """Incrementa o decrementa un campo numérico usando su paso predefinido."""
        for fname, _, ftype, step, fmin, fmax in ADVANCED_FIELDS_META:
            if fname == field_name:
                curr = getattr(self.config, fname)
                new_val = curr + (step * direction)
                new_val = max(fmin, min(fmax, new_val))
                if ftype is int:
                    new_val = int(round(new_val))
                else:
                    new_val = round(new_val, 2)
                setattr(self.config, fname, new_val)
                return
