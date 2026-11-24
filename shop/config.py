from dataclasses import dataclass
import os

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    max_agent_iterations: int
    database_path: str = "shop.db"


def get_settings() -> Settings:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key or api_key == "replace_me":
        raise RuntimeError(
            "Set GEMINI_API_KEY in your .env file before starting the agent. "
            "You can create a Gemini API key in Google AI Studio."
        )

    return Settings(
        gemini_api_key=api_key,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
        max_agent_iterations=int(os.getenv("MAX_AGENT_ITERATIONS", "8")),
        database_path=os.getenv("DATABASE_PATH", "shop.db"),
    )
