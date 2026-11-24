from dataclasses import dataclass
import os

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_model: str
    max_agent_iterations: int
    database_path: str = "shop.db"


def get_settings() -> Settings:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key or api_key == "replace_me":
        raise RuntimeError(
            "Set OPENAI_API_KEY in your .env file before starting the agent."
        )

    return Settings(
        openai_api_key=api_key,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-6.2-astra"),
        max_agent_iterations=int(os.getenv("MAX_AGENT_ITERATIONS", "8")),
    )
