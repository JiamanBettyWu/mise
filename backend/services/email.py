"""Send email via Gmail SMTP using a Google app password."""

import os
import smtplib
from email.message import EmailMessage


def send_html_email(*, to: str, subject: str, html: str) -> None:
    sender = os.environ["GMAIL_SENDER"]
    app_password = os.environ["GMAIL_APP_PASSWORD"]

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content("This email is best viewed in HTML.")
    msg.add_alternative(html, subtype="html")

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(sender, app_password)
        smtp.send_message(msg)
