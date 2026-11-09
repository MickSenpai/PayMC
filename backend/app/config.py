from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_webhook_id: str = ""
    paypal_base_url: str = "https://api-m.sandbox.paypal.com"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    api_key: str = "dev-key"
    database_url: str = "sqlite:///./trustshield.db"
    velocity_window_seconds: int = 600
    velocity_threshold: int = 5


settings = Settings()
