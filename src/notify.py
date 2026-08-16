"""推送日报：支持 Telegram、邮件、通用 Webhook；未配置则只写文件。"""
import json
import os
import smtplib
from email.mime.text import MIMEText
from urllib import request


def send(md_text: str, subject: str) -> str:
    """按优先级尝试各推送渠道，返回实际使用的渠道名。"""
    channel = _send_telegram(md_text) or _send_email(md_text, subject) or _send_webhook(md_text, subject)
    return channel or "file-only"


def _send_telegram(md_text: str) -> str | None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return None
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": md_text}
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with request.urlopen(req, timeout=30):
        pass
    return "telegram"


def _send_email(md_text: str, subject: str) -> str | None:
    host = os.environ.get("SMTP_HOST")
    to_addr = os.environ.get("EMAIL_TO")
    if not host or not to_addr:
        return None
    from_addr = os.environ.get("EMAIL_FROM", os.environ.get("SMTP_USER", "opera-hub@localhost"))
    msg = MIMEText(md_text, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ.get("SMTP_USER")
    pwd = os.environ.get("SMTP_PASS")
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=30)
    else:
        server = smtplib.SMTP(host, port, timeout=30)
        server.starttls()
    try:
        if user and pwd:
            server.login(user, pwd)
        server.sendmail(from_addr, [to_addr], msg.as_string())
    finally:
        server.quit()
    return "email"


def _send_webhook(md_text: str, subject: str) -> str | None:
    url = os.environ.get("WEBHOOK_URL")
    if not url:
        return None
    payload = json.dumps({"subject": subject, "text": md_text}).encode("utf-8")
    req = request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=30):
        pass
    return "webhook"
