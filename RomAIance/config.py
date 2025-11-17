from dataclasses import dataclass
from pathlib import Path

# Get the absolute path to the MatchMaker folder
BASE_DIR = Path(__file__).parent.resolve()  # folder containing config.py

@dataclass
class MatchMakerConfiguration:
    """Configuration for models and parameters."""
    app_name: str = "matchmaking_app"
    model_to_use: str = "gemini-2.5-flash-lite"
    db_path: Path = BASE_DIR / "db" / "matchmaking_data.db"
    sample_data: Path = BASE_DIR / "db" / "sample_users.json"

config = MatchMakerConfiguration()