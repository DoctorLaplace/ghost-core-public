import json
import os
from pathlib import Path
import config

FITNESS_FILE = Path(config.DATA_DIR) / "protocol_fitness.json"

def init_fitness_store() -> None:
    """Creates data/protocol_fitness.json if missing."""
    if not os.path.exists(FITNESS_FILE):
        with open(FITNESS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)

def record_outcome(protocol_name: str, task_succeeded: bool) -> None:
    """
    Loads fitness data, updates the exponential moving average fitness score
    for the given protocol, and saves it.
    """
    init_fitness_store()
    try:
        with open(FITNESS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}

    entry = data.get(protocol_name, {"score": 1.0, "trials": 0})
    score = entry["score"]
    trials = entry["trials"]

    if task_succeeded:
        score = score * 0.9 + 1.0 * 0.1
    else:
        score = score * 0.9

    trials += 1
    data[protocol_name] = {"score": score, "trials": trials}

    try:
        with open(FITNESS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception:
        pass

def get_doomed_protocols(min_trials: int = 10, threshold: float = 0.4) -> list[str]:
    """Returns protocol names with trials >= min_trials and score < threshold."""
    init_fitness_store()
    try:
        with open(FITNESS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []

    doomed = []
    for name, stats in data.items():
        if stats.get("trials", 0) >= min_trials and stats.get("score", 0.0) < threshold:
            doomed.append(name)
    return doomed
