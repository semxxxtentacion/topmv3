import logging
import re
import uuid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, formataddr

import aiosmtplib

from backend.config import settings

logger = logging.getLogger(__name__)

SENDER_NAME = "Топмашина"


def _html_to_plain(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html)
    text = re.sub(r"<hr[^>]*>", "\n---\n", text)
    text = re.sub(r"<a\s+[^>]*href=[\"']([^\"']+)[\"'][^>]*>([^<]+)</a>", r"\2: \1", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


async def _send_email(to: str, subject: str, html_body: str) -> None:
    message = MIMEMultipart("alternative")
    message["From"] = formataddr((SENDER_NAME, settings.mail_email))
    message["To"] = to
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = f"<{uuid.uuid4()}@topmashina.ru>"
    message["MIME-Version"] = "1.0"
    message["List-Unsubscribe"] = f"<mailto:{settings.mail_email}?subject=unsubscribe>"

    plain_body = _html_to_plain(html_body)
    message.attach(MIMEText(plain_body, "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))

    await aiosmtplib.send(
        message,
        hostname=settings.mail_host,
        port=465,
        use_tls=True,
        username=settings.mail_email,
        password=settings.mail_password,
    )
    logger.info(f"Email sent to {to}: {subject}")


async def send_verification_email(to: str, token: str) -> None:
    link = f"{settings.frontend_url}/verify-email?token={token}"
    html = f"""\
<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"></head>
<body style="margin:0; padding:0; background:#f4f4f4;">
  <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
    <div style="background: #ffffff; border-radius: 12px; padding: 32px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">
      <h2 style="color: #7c3aed; margin-top:0;">Топмашина</h2>
      <p style="color: #333; font-size: 16px; line-height: 1.5;">
        Здравствуйте! Подтвердите ваш email, нажав на кнопку ниже:
      </p>
      <p style="text-align: center; margin: 24px 0;">
        <a href="{link}"
           style="display: inline-block; background: #7c3aed; color: #ffffff; padding: 14px 28px;
                  border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 16px;">
          Подтвердить email
        </a>
      </p>
      <p style="color: #555; font-size: 13px;">Или скопируйте ссылку: {link}</p>
      <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">
      <p style="color: #666; font-size: 12px;">
        Ссылка действительна 24 часа. Если вы не регистриро��ались на Топмашина — просто проигнорируйте это письмо.
      </p>
    </div>
  </div>
</body>
</html>"""
    await _send_email(to, "Подтвердите ваш email — Топмашина", html)


async def send_password_reset_email(to: str, token: str) -> None:
    link = f"{settings.frontend_url}/new-password?token={token}"
    html = f"""\
<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"></head>
<body style="margin:0; padding:0; background:#f4f4f4;">
  <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
    <div style="background: #ffffff; border-radius: 12px; padding: 32px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">
      <h2 style="color: #7c3aed; margin-top:0;">Топмашина</h2>
      <p style="color: #333; font-size: 16px; line-height: 1.5;">
        Вы запросили сброс пароля. Нажмите на кнопку ниже для установки нового пароля:
      </p>
      <p style="text-align: center; margin: 24px 0;">
        <a href="{link}"
           style="display: inline-block; background: #7c3aed; color: #ffffff; padding: 14px 28px;
                  border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 16px;">
          Сбросить пароль
        </a>
      </p>
      <p style="color: #555; font-size: 13px;">Или скопируйте ссылку: {link}</p>
      <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">
      <p style="color: #666; font-size: 12px;">
        Ссылка действительна 1 час. Если вы не запрашивали сброс — просто проигнорируйте это письмо.
      </p>
    </div>
  </div>
</body>
</html>"""
    await _send_email(to, "Сброс пароля — Топмашина", html)


async def send_admin_invite_email(to: str, token: str, role: str) -> None:
    role_name = {"admin": "администратора", "manager": "менеджера"}.get(role, role)
    link = f"{settings.admin_url}/invite?token={token}"
    html = f"""\
<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"></head>
<body style="margin:0; padding:0; background:#f4f4f4;">
  <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 40px 20px;">
    <div style="background: #ffffff; border-radius: 12px; padding: 32px; box-shadow: 0 2px 8px rgba(0,0,0,0.06);">
      <h2 style="color: #2563eb; margin-top:0;">Топмашина — Админ-панель</h2>
      <p style="color: #333; font-size: 16px; line-height: 1.5;">
        Вас пригласили в команду Топмашина в роли {role_name}.
        Нажмите на кнопку ниже для создания аккаунта:
      </p>
      <p style="text-align: center; margin: 24px 0;">
        <a href="{link}"
           style="display: inline-block; background: #2563eb; color: #ffffff; padding: 14px 28px;
                  border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 16px;">
          Создать аккаунт
        </a>
      </p>
      <p style="color: #555; font-size: 13px;">Или скопируйте ссылку: {link}</p>
      <hr style="border: none; border-top: 1px solid #eee; margin: 24px 0;">
      <p style="color: #666; font-size: 12px;">
        Ссылка действительна 7 дней. Если вы не ожидали это приглашение — просто проигнорируйте письмо.
      </p>
    </div>
  </div>
</body>
</html>"""
    await _send_email(to, "Приглашение в команду — Топмашина", html)
