from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = ""
    stow_llm_base_url: str = ""
    stow_llm_model: str = ""
