"""
app/notifications/email_sender.py
──────────────────────────────────
Gmail SMTP email sender.
"""
import asyncio
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import html
import smtplib
import ssl
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.logging_config import get_logger
from app.config.settings import get_settings
from app.database.models import (
    EligibilityResult,
    ExtractedData,
    NotificationLog,
    PlacementPost,
)

logger = get_logger(__name__)


def _build_html_email(
    post: PlacementPost,
    extracted: Optional[ExtractedData],
    eligibility_status: str,
    eligibility_reason: str = "",
) -> str:
    is_eligible = "ELIGIBLE" in eligibility_status.upper() and "NOT" not in eligibility_status.upper()

    if is_eligible:
        banner_color = "#16a34a"
        banner_tag = "🎯 Placement Alert"
        banner_heading = "ELIGIBLE FOR PLACEMENT"
        status_bg = "#f0fdf4"
        status_border = "#bbf7d0"
        status_text_color = "#166534"
    else:
        banner_color = "#ea580c"
        banner_tag = "⚠️ Action Required"
        banner_heading = "VERIFY ELIGIBILITY"
        status_bg = "#fff7ed"
        status_border = "#fed7aa"
        status_text_color = "#9a3412"

    title_escaped = html.escape(post.title or "Placement Notice")
    notice_url = post.post_url or ""
    escaped_notice_url = html.escape(notice_url)

    company = extracted.company_name if (extracted and extracted.company_name) else "Not specified in official notice"
    company_escaped = html.escape(company)

    program = extracted.program_name if (extracted and extracted.program_name) else "Not specified in official notice"
    program_escaped = html.escape(program)

    if extracted and extracted.location:
        location_str = ", ".join(str(loc) for loc in extracted.location) if isinstance(extracted.location, list) else str(extracted.location)
    else:
        location_str = "Not specified in official notice"
    location_escaped = html.escape(location_str)

    if extracted and extracted.eligible_degrees:
        degrees_str = ", ".join(str(d) for d in extracted.eligible_degrees) if isinstance(extracted.eligible_degrees, list) else str(extracted.eligible_degrees)
    else:
        degrees_str = "Not specified in official notice"
    degrees_escaped = html.escape(degrees_str)

    academics = []
    if extracted:
        if extracted.minimum_10th_percentage is not None: academics.append(f"10th: {extracted.minimum_10th_percentage}%")
        if extracted.minimum_12th_percentage is not None: academics.append(f"12th: {extracted.minimum_12th_percentage}%")
        if extracted.minimum_cgpa is not None: academics.append(f"CGPA: {extracted.minimum_cgpa}")
        if extracted.backlog_allowed is not None: academics.append("Backlogs Allowed" if extracted.backlog_allowed else "No Backlogs")
    academics_str = " | ".join(academics) if academics else "Not specified in official notice"
    academics_escaped = html.escape(academics_str)

    if extracted and extracted.graduation_years:
        grad_years_str = ", ".join(str(y) for y in extracted.graduation_years) if isinstance(extracted.graduation_years, list) else str(extracted.graduation_years)
    else:
        grad_years_str = "Not specified in official notice"
    grad_years_escaped = html.escape(grad_years_str)

    if extracted and extracted.application_deadline:
        deadline_str = extracted.application_deadline.strip()
    else:
        deadline_str = "Not specified in official notice"
    deadline_escaped = html.escape(deadline_str)

    reason_escaped = html.escape(eligibility_reason.strip() if eligibility_reason else "No specific criteria notes provided.")

    if extracted and extracted.application_link:
        escaped_app_url = html.escape(extracted.application_link)
        apply_btn_html = f"""<a href="{escaped_app_url}" target="_blank" style="display: inline-block; min-width: 140px; padding: 12px 24px; margin: 6px; font-size: 15px; font-weight: 700; color: #ffffff; background-color: #16a34a; text-decoration: none; border-radius: 6px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">🚀 Apply Now &rarr;</a>"""
    else:
        apply_btn_html = f"""<a href="{escaped_notice_url}" target="_blank" style="display: inline-block; min-width: 140px; padding: 12px 24px; margin: 6px; font-size: 15px; font-weight: 700; color: #ffffff; background-color: #059669; text-decoration: none; border-radius: 6px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">🚀 Apply via Notice</a>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title_escaped}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #f3f4f6; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1f2937; line-height: 1.5;">
  <div style="max-width: 600px; margin: 24px auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06); border: 1px solid #e5e7eb;">
    <div style="background-color: {banner_color}; color: #ffffff; padding: 24px 20px; text-align: center;">
      <span style="font-size: 12px; font-weight: 700; letter-spacing: 1.5px; text-transform: uppercase; background: rgba(255, 255, 255, 0.2); padding: 4px 12px; border-radius: 9999px; display: inline-block; margin-bottom: 8px;">
        {banner_tag}
      </span>
      <h1 style="margin: 0; font-size: 22px; font-weight: 800; letter-spacing: -0.5px;">
        {banner_heading}
      </h1>
    </div>
    <div style="padding: 24px 20px;">
      <div style="margin-bottom: 20px; padding-bottom: 16px; border-bottom: 1px solid #e5e7eb;">
        <span style="font-size: 12px; text-transform: uppercase; color: #6b7280; font-weight: 600; letter-spacing: 0.5px;">Portal Notice</span>
        <h2 style="margin: 4px 0 0 0; font-size: 18px; font-weight: 700; color: #111827; line-height: 1.4;">
          {title_escaped}
        </h2>
      </div>
      <div style="margin-bottom: 20px; background-color: {status_bg}; border: 1px solid {status_border}; border-left: 4px solid {banner_color}; border-radius: 6px; padding: 14px 16px;">
        <div style="font-size: 13px; font-weight: 700; color: {status_text_color}; text-transform: uppercase; margin-bottom: 4px;">
          Eligibility Assessment: {eligibility_status.upper()}
        </div>
        <div style="font-size: 14px; color: #374151; line-height: 1.5;">
          {reason_escaped}
        </div>
      </div>
      <table style="width: 100%; border-collapse: collapse; margin-bottom: 24px; font-size: 14px;">
        <tbody>
          <tr style="border-bottom: 1px solid #f3f4f6;"><td style="padding: 8px 0; color: #6b7280; font-weight: 600; width: 38%;">Company</td><td style="padding: 8px 0; color: #111827; font-weight: 600;">{company_escaped}</td></tr>
          <tr style="border-bottom: 1px solid #f3f4f6;"><td style="padding: 8px 0; color: #6b7280; font-weight: 600;">Program</td><td style="padding: 8px 0; color: #111827;">{program_escaped}</td></tr>
          <tr style="border-bottom: 1px solid #f3f4f6;"><td style="padding: 8px 0; color: #6b7280; font-weight: 600;">Location</td><td style="padding: 8px 0; color: #111827;">{location_escaped}</td></tr>
          <tr style="border-bottom: 1px solid #f3f4f6;"><td style="padding: 8px 0; color: #6b7280; font-weight: 600;">Eligible Degrees</td><td style="padding: 8px 0; color: #111827;">{degrees_escaped}</td></tr>
          <tr style="border-bottom: 1px solid #f3f4f6;"><td style="padding: 8px 0; color: #6b7280; font-weight: 600;">Academic Requirements</td><td style="padding: 8px 0; color: #111827;">{academics_escaped}</td></tr>
          <tr style="border-bottom: 1px solid #f3f4f6;"><td style="padding: 8px 0; color: #6b7280; font-weight: 600;">Eligible YOP</td><td style="padding: 8px 0; color: #111827;">{grad_years_escaped}</td></tr>
          <tr><td style="padding: 8px 0; color: #6b7280; font-weight: 600;">Application Deadline</td><td style="padding: 8px 0; color: #b91c1c; font-weight: 600;">{deadline_escaped}</td></tr>
        </tbody>
      </table>
      <table border="0" cellpadding="0" cellspacing="0" style="width: 100%; margin: 24px 0 12px 0;">
        <tr>
          <td align="center" style="padding-bottom: 8px;">
            <a href="{escaped_notice_url}" target="_blank" style="display: inline-block; min-width: 140px; padding: 12px 24px; margin: 6px; font-size: 15px; font-weight: 700; color: #ffffff; background-color: #2563eb; text-decoration: none; border-radius: 6px; text-align: center; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">📄 View Notice</a>
            {apply_btn_html}
          </td>
        </tr>
      </table>
    </div>
  </div>
</body>
</html>"""

def _send_smtp(to: str, subject: str, html_body: str) -> None:
    settings = get_settings()
    sender = settings.gmail_sender
    app_password = settings.gmail_app_password
    if not sender or not app_password:
        raise ValueError("Gmail sender or app password is not configured.")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    context = ssl.create_default_context()
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
        server.ehlo()
        server.starttls(context=context)
        server.ehlo()
        server.login(sender, app_password)
        server.sendmail(sender, [to], msg.as_string())

async def send_notification(session: AsyncSession, post_id: int, eligibility_status: str, eligibility_reason: str) -> bool:
    post = await session.get(PlacementPost, post_id)
    if not post:
        return False
    stmt_extracted = select(ExtractedData).where(ExtractedData.post_id == post_id)
    res_extracted = await session.execute(stmt_extracted)
    extracted = res_extracted.scalar_one_or_none()

    if not eligibility_reason:
        stmt_elig = select(EligibilityResult).where(EligibilityResult.post_id == post_id)
        res_elig = await session.execute(stmt_elig)
        elig_result = res_elig.scalar_one_or_none()
        if elig_result and elig_result.reason:
            eligibility_reason = elig_result.reason

    settings = get_settings()
    recipient = settings.gmail_recipient

    stmt_log = select(NotificationLog).where(NotificationLog.post_id == post_id, NotificationLog.recipient == recipient)
    res_log = await session.execute(stmt_log)
    notif_log = res_log.scalar_one_or_none()

    if notif_log and notif_log.status == "sent":
        return True
    if not notif_log:
        notif_log = NotificationLog(post_id=post_id, recipient=recipient)
        session.add(notif_log)

    company = extracted.company_name.strip() if (extracted and extracted.company_name) else "Placement Notice"
    if "ELIGIBLE" in eligibility_status.upper() and "NOT" not in eligibility_status.upper():
        subject = f"🚨 Placement Alert — {company}"
    else:
        subject = f"⚠️ Verify Eligibility — {company}"

    html_body = _build_html_email(post, extracted, eligibility_status, eligibility_reason)

    loop = asyncio.get_event_loop()
    try:
        await loop.run_in_executor(None, _send_smtp, recipient, subject, html_body)
        notif_log.status = "sent"
        notif_log.subject = subject
        notif_log.sent_at = datetime.now(timezone.utc)
        notif_log.error_message = None
        await session.commit()
        return True
    except Exception as exc:
        notif_log.status = "failed"
        notif_log.subject = subject
        notif_log.error_message = str(exc)
        notif_log.retry_count = (notif_log.retry_count or 0) + 1
        await session.commit()
        return False

async def skip_notification(session: AsyncSession, post_id: int, reason: str) -> None:
    settings = get_settings()
    recipient = settings.gmail_recipient

    stmt = select(NotificationLog).where(NotificationLog.post_id == post_id, NotificationLog.recipient == recipient)
    res = await session.execute(stmt)
    notif_log = res.scalar_one_or_none()

    if not notif_log:
        notif_log = NotificationLog(post_id=post_id, recipient=recipient)
        session.add(notif_log)

    notif_log.status = "skipped"
    notif_log.error_message = reason
    await session.commit()
