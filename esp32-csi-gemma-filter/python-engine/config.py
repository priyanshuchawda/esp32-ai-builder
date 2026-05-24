import os

# Path settings
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_DATA_DIR = os.path.join(DATA_DIR, "raw")
FILTERED_DATA_DIR = os.path.join(DATA_DIR, "filtered")
DECISIONS_DIR = os.path.join(DATA_DIR, "decisions")
PLOTS_DIR = os.path.join(DATA_DIR, "plots")
LABELS_DIR = os.path.join(DATA_DIR, "labels")

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(os.path.join(BASE_DIR, ".env"), override=False)
    load_dotenv(os.path.join(os.path.dirname(BASE_DIR), ".env"), override=False)

# Gemma Advisor Settings
GEMMA_ADVISOR_PROVIDER = os.getenv("GEMMA_ADVISOR_PROVIDER", "gemini").strip().lower()

# Hosted Gemini API Settings
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_GEMMA_MODEL = os.getenv("GEMINI_GEMMA_MODEL", "gemma-4-31b-it").strip()
GEMINI_GEMMA_FALLBACK_MODEL = os.getenv(
    "GEMINI_GEMMA_FALLBACK_MODEL", "gemma-4-26b-a4b-it"
).strip()
GEMINI_THINKING_LEVEL = os.getenv("GEMINI_THINKING_LEVEL", "high").strip()

# Ollama Local API Settings
OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "gemma4:e2b"
OLLAMA_TIMEOUT_SECONDS = float(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120.0"))

# Default Serial Connection Settings
DEFAULT_PORT = "COM5"
DEFAULT_BAUD = 115200
SERIAL_TIMEOUT = 1.0

# Windowing Parameters
WINDOW_DURATION_SEC = 2.0  # Time-based window size for serial mode (seconds)
SIMULATED_WINDOW_SAMPLES = 100  # Sample-based window size for simulated mode
SIMULATED_SAMPLING_RATE_HZ = (
    50.0  # 50 Hz sampling rate in simulated mode (20ms interval)
)
SERIAL_SAMPLING_RATE_HZ_EST = (
    10.0  # Est. 10 Hz sampling rate for ESP32 (100ms interval)
)

# Rule-Based Advisor Fallback Settings
FALLBACK_OUTLIER_RATIO_THRESHOLD = 0.10
FALLBACK_HIGH_STD_THRESHOLD = 2.0
FALLBACK_NOISE_STD_THRESHOLD = 0.2

# Ensure directories exist
for directory in [
    RAW_DATA_DIR,
    FILTERED_DATA_DIR,
    DECISIONS_DIR,
    PLOTS_DIR,
    LABELS_DIR,
]:
    os.makedirs(directory, exist_ok=True)
