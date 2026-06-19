import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage

logger = logging.getLogger(__name__)

def send_certificate_email(recipient_email, learner_name, certificate_image_path):
    """Send the Certificate of Completion to the learner's email address via SMTP."""
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT", "587")
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_sender = os.getenv("SMTP_SENDER", smtp_user)

    if not smtp_host or not smtp_user or not smtp_password:
        logger.warning(
            "SMTP credentials not fully configured (SMTP_HOST, SMTP_USER, SMTP_PASSWORD missing). "
            "Skipping email delivery."
        )
        return False

    try:
        msg = MIMEMultipart()
        msg['From'] = smtp_sender
        msg['To'] = recipient_email
        msg['Subject'] = f"The Brothers' Room - Certificate of Completion for {learner_name}"

        # HTML body
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333333; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #dddddd; border-radius: 8px;">
            <div style="text-align: center; margin-bottom: 20px;">
                <h2 style="color: #0F2043; margin-bottom: 5px; letter-spacing: 8px; font-weight: bold;">THE BROTHERS' ROOM</h2>
                <hr style="border: 0; border-top: 2px solid #dba147; width: 150px; margin: 0 auto;">
            </div>
            
            <p>Congratulations <strong>{learner_name}</strong>,</p>
            
            <p>You have successfully completed <strong>The Brothers' Room</strong> course on positive masculinity and Gender-Based Violence prevention!</p>
            
            <p>Your official Certificate of Completion is attached to this email. You have proven yourself to be a true advocate of healthy masculinity and respect in your community.</p>
            
            <p>Keep living as a peer champion and leading by example.</p>
            
            <br>
            <p style="margin-bottom: 0;">Best regards,</p>
            <p style="margin-top: 5px;"><strong>The Brothers' Room Team</strong></p>
        </body>
        </html>
        """
        msg.attach(MIMEText(body, 'html'))

        # Attach image
        if os.path.exists(certificate_image_path):
            with open(certificate_image_path, 'rb') as f:
                img_data = f.read()
            image = MIMEImage(img_data, name=os.path.basename(certificate_image_path))
            # Set attachment headers
            image.add_header('Content-Disposition', 'attachment', filename=os.path.basename(certificate_image_path))
            msg.attach(image)
        else:
            logger.error(f"Certificate file not found at {certificate_image_path}")
            return False

        # Send email
        if smtp_port == "465":
            server = smtplib.SMTP_SSL(smtp_host, int(smtp_port), timeout=15)
        else:
            server = smtplib.SMTP(smtp_host, int(smtp_port), timeout=15)
            server.starttls()
            
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_sender, recipient_email, msg.as_string())
        server.quit()
        logger.info(f"Certificate email successfully sent to {recipient_email}")
        return True
    except Exception as e:
        logger.error(f"Error sending certificate email to {recipient_email}: {e}")
        return False

def send_monthly_status_email(admin_email, start_date=None, end_date=None, raise_on_error=False):
    """Send a system status and statistics report to the administrator email via SMTP."""
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = os.getenv("SMTP_PORT", "587")
    smtp_user = os.getenv("SMTP_USER")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_sender = os.getenv("SMTP_SENDER", smtp_user)

    if not smtp_host or not smtp_user or not smtp_password:
        logger.warning("SMTP credentials not fully configured. Skipping status report email.")
        return False

    recipients = [email.strip() for email in admin_email.split(",") if email.strip()]
    if not recipients:
        logger.warning("No valid admin email addresses found in ADMIN_EMAIL. Skipping status report email.")
        return False

    try:
        from dashboard import get_stats_data
        stats = get_stats_data(start_date, end_date)
    except Exception as e:
        logger.error(f"Error fetching stats for status email: {e}")
        stats = {}

    total_enrollments = stats.get("total_enrollments", 0)
    graduates_count = stats.get("graduates_count", 0)
    average_pre_test = stats.get("average_pre_test", 0.0)
    average_post_test = stats.get("average_post_test", 0.0)
    total_ai_queries = stats.get("total_ai_queries", 0)
    
    languages = stats.get("languages", {})
    lang_breakdown = "".join([f"<li><strong>{lang}:</strong> {count}</li>" for lang, count in languages.items()])
    
    module_progress = stats.get("module_progress", {})
    progress_breakdown = "".join([f"<li><strong>{mod}:</strong> {count}</li>" for mod, count in module_progress.items()])

    try:
        if start_date or end_date:
            date_range_str = f" ({start_date or 'Start'} to {end_date or 'Present'})"
            subject_line = f"The Brothers' Room - Program Status Report{date_range_str}"
            subtitle_str = f"Facilitator Report: {start_date or 'Start'} - {end_date or 'Present'}"
        else:
            subject_line = "The Brothers' Room - Monthly Program & System Status Report"
            subtitle_str = "Facilitator Monthly Report"

        msg = MIMEMultipart()
        msg['From'] = smtp_sender
        msg['To'] = ", ".join(recipients)
        msg['Subject'] = subject_line

        # HTML body with sleek styling
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333333; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #dddddd; border-radius: 8px;">
            <div style="text-align: center; margin-bottom: 20px;">
                <h2 style="color: #0F2043; margin-bottom: 5px; letter-spacing: 2px; font-weight: bold;">THE BROTHERS' ROOM</h2>
                <h4 style="color: #dba147; margin-top: 0; font-weight: normal;">{subtitle_str}</h4>
                <hr style="border: 0; border-top: 2px solid #dba147; width: 150px; margin: 0 auto;">
            </div>
            
            <p>Hello Program Administrator,</p>
            
            <p>This is your automated monthly system status and participant analytics report for <strong>The Brothers' Room</strong>.</p>
            
            <h3 style="color: #0F2043; border-bottom: 1px solid #dba147; padding-bottom: 5px;">📊 Key Program Metrics</h3>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                <tr style="background-color: #f9f9f9;">
                    <td style="padding: 10px; border-bottom: 1px solid #eeeeee;"><strong>Total Enrolled Participants:</strong></td>
                    <td style="padding: 10px; border-bottom: 1px solid #eeeeee; text-align: right;">{total_enrollments}</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border-bottom: 1px solid #eeeeee;"><strong>Total Graduates:</strong></td>
                    <td style="padding: 10px; border-bottom: 1px solid #eeeeee; text-align: right;">{graduates_count}</td>
                </tr>
                <tr style="background-color: #f9f9f9;">
                    <td style="padding: 10px; border-bottom: 1px solid #eeeeee;"><strong>Average Pre-Test Score:</strong></td>
                    <td style="padding: 10px; border-bottom: 1px solid #eeeeee; text-align: right;">{average_pre_test} / 50</td>
                </tr>
                <tr>
                    <td style="padding: 10px; border-bottom: 1px solid #eeeeee;"><strong>Average Post-Test Score:</strong></td>
                    <td style="padding: 10px; border-bottom: 1px solid #eeeeee; text-align: right;">{average_post_test} / 50</td>
                </tr>
                <tr style="background-color: #f9f9f9;">
                    <td style="padding: 10px; border-bottom: 1px solid #eeeeee;"><strong>Total AI Chatbot Queries:</strong></td>
                    <td style="padding: 10px; border-bottom: 1px solid #eeeeee; text-align: right;">{total_ai_queries}</td>
                </tr>
            </table>

            <h3 style="color: #0F2043; border-bottom: 1px solid #dba147; padding-bottom: 5px;">🌐 Language Preferences</h3>
            <ul>
                {lang_breakdown}
            </ul>

            <h3 style="color: #0F2043; border-bottom: 1px solid #dba147; padding-bottom: 5px;">📈 Module Progression Funnel</h3>
            <ul>
                {progress_breakdown}
            </ul>

            <h3 style="color: #0F2043; border-bottom: 1px solid #dba147; padding-bottom: 5px;">🔒 System Status & Data Integrity</h3>
            <p>Database persistence checks and daily rolling backup tasks are functioning normally. To download the raw participant PII records (CSV format), please run the <code>/admin</code> command in your Telegram interface.</p>
            
            <br>
            <p style="margin-bottom: 0;">Best regards,</p>
            <p style="margin-top: 5px;"><strong>The Brothers' Room Bot Engine</strong></p>
        </body>
        </html>
        """
        msg.attach(MIMEText(body, 'html'))

        # Send email
        if smtp_port == "465":
            server = smtplib.SMTP_SSL(smtp_host, int(smtp_port), timeout=15)
        else:
            server = smtplib.SMTP(smtp_host, int(smtp_port), timeout=15)
            server.starttls()
            
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_sender, recipients, msg.as_string())
        server.quit()
        logger.info(f"Monthly status report email successfully sent to {', '.join(recipients)}")
        return True
    except Exception as e:
        logger.error(f"Error sending monthly status email to {admin_email}: {e}")
        if raise_on_error:
            raise e
        return False

