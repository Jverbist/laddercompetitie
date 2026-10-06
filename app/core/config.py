from datetime import datetime

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./laddercompetitie.db"
    admin_emails: str = "christophe@example.com,yasmine@example.com"
    admin_bootstrap_password: str = ""
    session_secret: str = "development-only-secret-change-before-production"
    session_https_only: bool = False
    auto_create_schema: bool = True
    allowed_hosts: str = "*"
    registration_enabled: bool = True
    registration_email_domains: str = ""
    qualification_deadline: datetime = datetime.fromisoformat("2026-10-15T23:59:59+02:00")
    final_day_start: datetime = datetime.fromisoformat("2026-10-16T09:00:00+02:00")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def admin_email_set(self) -> set[str]:
        return {email.strip().lower() for email in self.admin_emails.split(",") if email.strip()}

    @property
    def registration_domain_set(self) -> set[str]:
        return {d.strip().lower().lstrip("@") for d in self.registration_email_domains.split(",") if d.strip()}

    @property
    def allowed_host_list(self) -> list[str]:
        return [host.strip() for host in self.allowed_hosts.split(",") if host.strip()]


settings = Settings()
