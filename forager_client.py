"""Central configuration. All secrets come from environment variables."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    forager_api_key: str
    forager_account_id: str
    hubspot_access_token: str

    webhook_secret: str = "change-me"

    # comma separated keywords, e.g. "Engineering,Engineer,VP"
    job_title_filter: str = ""
    max_contacts_per_company: int = 5
    fetch_work_email: bool = True
    fetch_phone: bool = True

    @property
    def job_title_keywords(self) -> list[str]:
        return [k.strip() for k in self.job_title_filter.split(",") if k.strip()]

    @property
    def forager_base_url(self) -> str:
        return f"https://api-v2.forager.ai/api/{self.forager_account_id}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
