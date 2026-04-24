from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from typing import Dict
from urllib.parse import quote
load_dotenv()

class Settings(BaseSettings):
    # Internal shared secret между бэком и ботом (ротировать при компрометации)
    bot_api_secret: str = ""
    # PostgreSQL
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "top-machine"
    db_user: str = "admin"
    db_password: str = ""

    # Bot internal
    bot_internal_url: str = "http://localhost:8081/internal/notify"

    # Mail
    mail_host: str = ""
    mail_email: str = ""
    mail_password: str = ""

    # Frontend URL (для ссылок в письмах)
    frontend_url: str = "https://topmashina.ru"

    # Admin panel URL
    admin_url: str = "https://admin.topmashina.ru"

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 7
    tinkoff_init_url: str = 'https://securepay.tinkoff.ru/v2/Init'
    tinkoff_get_state_url: str = 'https://securepay.tinkoff.ru/v2/GetState'
    URL_topvisor_url: str = 'https://api.topvisor.com/v2/'
    topvizor_token: str = ''
    topvizor_user: int = 0
    URL_add_new_project_at_topvisor: str = 'add/projects_2/projects'
    URL_add_positions_2_searchers_regions: str = 'add/positions_2/searchers_regions'
    URL_get_positions_2_history_links: str = 'get/positions_2/history/links'
    URL_add_keywords_2_keywords_import: str = 'add/keywords_2/keywords/import'
    URL_get_keywords_2_keywords: str = 'get/keywords_2/keywords'
    URL_edit_keywords_2_keywords_rename: str = 'edit/keywords_2/keywords/rename'
    URL_del_keywords_2_keywords: str = 'del/keywords_2/keywords'
    URL_del_projects_2_projects: str = 'del/projects_2/projects'
    URL_get_keywords_2_groups: str = 'get/keywords_2/groups'
    BASE_api_keys_so: str = 'https://api.keys.so/report/simple/organic/keywords'
    BASE_PARAMS_api_keys_so: str = "base=msk&per_page=100&sort=ws|desc"

    # ASocks Proxy
    asocks_api_key: str = ""
    asocks_base_url: str = "https://api.asocks.com/v2"

    # Yandex OAuth (server-side authorization code flow)
    yandex_client_id: str = "9a0a11d361714c3089d41efaf191162c"
    yandex_client_secret: str = ""
    yandex_redirect_uri: str = "https://topmashina.ru/yandex-oauth"

    # Bot profiles DB (acc_generator)
    bot_db_host: str = ""
    bot_db_port: int = 5433
    bot_db_name: str = "acc_generator"
    bot_db_user: str = ""
    bot_db_password: str = ""

    def get_url(self, domain: str) -> str:
        return f"{self.BASE_api_keys_so}?{self.BASE_PARAMS_api_keys_so}&domain={domain}"
    
    @property
    def topvizor_headers(self) -> Dict[str, str]:
        return {
            "User-id": str(self.topvizor_user),
            "Authorization": f"Bearer {self.topvizor_token}",
            "Content-Type": "application/json"
        }
    @property
    def database_url(self) -> str:
        # URL-encode пароля — может содержать @/:/? и ломать URL-парсер asyncpg.
        pw = quote(self.db_password, safe="")
        user = quote(self.db_user, safe="")
        return f"postgresql://{user}:{pw}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def bot_database_url(self) -> str:
        pw = quote(self.bot_db_password, safe="")
        user = quote(self.bot_db_user, safe="")
        return f"postgresql://{user}:{pw}@{self.bot_db_host}:{self.bot_db_port}/{self.bot_db_name}"

    class Config:
        env_file = ".env"
        extra = "ignore"   


settings = Settings()
