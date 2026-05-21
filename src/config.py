from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    LLM_PROVIDER: str = "kisski"
    KISSKI_API_KEY: str = ""
    KISSKI_BASE_URL: str = "https://chat-ai.academiccloud.de/v1"
    LLM_MODEL: str = "meta-llama/llama-3.3-70b-instruct"

    TRACKER_DB_PATH: str = "data/tracker.db"
    USER_PROFILE_PATH: str = "data/user_profile.yaml"

    INTERNAL_API_KEY: str = "change-me-to-a-long-random-string"

    HOST: str = "0.0.0.0"
    PORT: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
