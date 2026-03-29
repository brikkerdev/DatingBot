from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: str

    # Webhook
    webhook_enabled: bool = False
    webhook_host: str = "0.0.0.0"
    webhook_port: int = 8443
    webhook_path: str = "/webhook"
    webhook_url: str = ""

    # Database
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "dating_bot"
    db_user: str = "postgres"
    db_password: str = "postgres"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
