from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from typing import Dict
load_dotenv()

class Settings(BaseSettings):
    #пароль для софта
    bot_api_secret: str = "topmachine-super-secret-2026"
    # PostgreSQL
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "top-machine"
    db_user: str = "admin"
    db_password: str = "MIIEvQIBADANBg@"

    # Bot internal
    bot_internal_url: str = "http://localhost:8081/internal/notify"

    # Mail
    mail_host: str = ""
    mail_email: str = ""
    mail_password: str = ""

    # Frontend URL (для ссылок в письмах)
    frontend_url: str = "http://localhost:3000"

    # Admin panel URL
    admin_url: str = "http://localhost:5173"

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_days: int = 7
    tinkoff_init_url: str = 'https://securepay.tinkoff.ru/v2/Init'
    tinkoff_get_state_url: str = 'https://securepay.tinkoff.ru/v2/GetState'
    URL_topvisor_url: str = 'https://api.topvisor.com/v2/'
    topvizor_token: str = '7054ecc884f9d2726782534057db68cf'
    topvizor_user: int = 400956
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

    # Bot profiles DB (acc_generator)
    bot_db_host: str = "5.129.206.79"
    bot_db_port: int = 5433
    bot_db_name: str = "acc_generator"
    bot_db_user: str = "admin"
    bot_db_password: str = "s5YX15RUJv6B3vsjr4"

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
        return f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def bot_database_url(self) -> str:
        return f"postgresql://{self.bot_db_user}:{self.bot_db_password}@{self.bot_db_host}:{self.bot_db_port}/{self.bot_db_name}"

    class Config:
        env_file = ".env"
        extra = "ignore"   


settings = Settings()
