from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "ContractSaaS"
    secret_key: str = "change-me-in-production"
    api_key: str = "dev-key-123"
    max_upload_mb: int = 50
    upload_dir: str = "/tmp/contractsaas_uploads"
    db_path: str = "data/contractsaas.db"
    stripe_secret_key: str = ""
    stripe_price_id: str = ""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
