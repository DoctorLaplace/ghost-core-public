import os
from dotenv import load_dotenv
from pathlib import Path

# --- Torch FP8 Compatibility Hotfix ---
try:
    import torch
    if not hasattr(torch, "float8_e8m0fnu"):
        setattr(torch, "float8_e8m0fnu", getattr(torch, "float32", None))
except ImportError:
    pass

# Load environment variables from .env file
load_dotenv()

# --- Gemini API Configuration ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GOOGLE_API_KEY_HERE":
    raise ValueError("GEMINI_API_KEY not found or not set in .env file. Please get a key from Google AI Studio.")

GEMINI_MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", "gemini-3.5-flash") #--- options: gemini-3.5-flash, gemini-3.1-pro, gemini-3.1-flash-lite
LIGHT_DUTY_MODEL_NAME = os.getenv("LIGHT_DUTY_MODEL_NAME", "gemini-3.1-flash-lite")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")

# --- Anthropic API Configuration ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


# --- Database Configurations ---
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
if not NEO4J_PASSWORD or NEO4J_PASSWORD == "YOUR_NEO4J_PASSWORD":
    raise ValueError("NEO4J_PASSWORD not found or not set in .env file. Please set the password for your Neo4j database.")

# --- Agent Settings ---
AGENT_NAME = os.getenv("AGENT_NAME", "Despina")
DIRECTOR_NAME = os.getenv("DIRECTOR_NAME", "Director")

# --- OS Integration Settings ---
OVERLAY_MODE = os.getenv("OVERLAY_MODE", "False").lower() in ("true", "1", "t")
OVERLAY_TOGGLE_HOTKEY = os.getenv("OVERLAY_TOGGLE_HOTKEY", "ctrl+windows")
FOCUS_MODE_HOTKEY = os.getenv("FOCUS_MODE_HOTKEY", "ctrl+alt")

# Windows Automation "Polite Focus" Settings
ALLOW_FOCUS_TAKEOVER = os.getenv("ALLOW_FOCUS_TAKEOVER", "True").lower() in ("true", "1", "t")
USER_IDLE_TIMEOUT_SECONDS = int(os.getenv("USER_IDLE_TIMEOUT_SECONDS", 3))

# --- Action Settings ---
TERMINAL_TIMEOUT_SECONDS = int(os.getenv("TERMINAL_TIMEOUT_SECONDS", 60))

# --- Memory Hyperparameters ---
STM_MAX_TOKENS = int(os.getenv("STM_MAX_TOKENS", 30000))
LTM_RETRIEVAL_COUNT = int(os.getenv("LTM_RETRIEVAL_COUNT", 5))
DYNAMIC_INSIGHT_COUNT = int(os.getenv("DYNAMIC_INSIGHT_COUNT", 5))
TRUNCATE_OVERSIZED_STM_THRESHOLD = int(os.getenv("TRUNCATE_OVERSIZED_STM_THRESHOLD", 100000))

# Tools that produce massive or transient output not worth sending to LTM assessment
TRIVIAL_TOOLS = [
    "search_window_ui",
    "inspect_window_ui",
    "list_open_windows",
    "capture_window_background",
    "analyze_window_visually",
    "get_active_window",
    "look_at_screen",
    "analyze_image_visually"
]

# --- File Paths ---
BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / 'logs'
DATA_DIR = BASE_DIR / 'data'
AGENT_STATE_FILE = DATA_DIR / 'agent_state.json'
GOALS_FILE = DATA_DIR / 'goals.json'
EXPERIMENTS_FILE = DATA_DIR / 'experiments.json'
PROTOCOLS_FILE = DATA_DIR / 'protocols.json'
CORE_CONSTITUTION_FILE = BASE_DIR / 'agent' / 'volition' / 'core_constitution.md'
GENERATED_TOOLS_DIR = BASE_DIR / 'agent' / 'generated_tools'
WORKSPACE_FILE = DATA_DIR / 'current_context.md'

# Create directories if they don't exist
LOG_DIR.mkdir(exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)
GENERATED_TOOLS_DIR.mkdir(exist_ok=True)

# --- Model Router Configuration ---
MODEL_TIERS = {
    "frontier": GEMINI_MODEL_NAME,
    "cheap": LIGHT_DUTY_MODEL_NAME,
    "local": "ollama/llama3.1"
}
ROUTER_ENABLED = True

# --- Grounded Planning Configuration ---
PLANNER_ENABLED = True

# --- Hot-Swap Cortex Canary Configuration ---
CANARY_ENABLED = False
CANARY_RATIO = 0.1

