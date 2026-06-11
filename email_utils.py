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
            server = smtplib.SMTP_SSL(smtp_host, int(smtp_port))
        else:
            server = smtplib.SMTP(smtp_host, int(smtp_port))
            server.starttls()
            
        server.login(smtp_user, smtp_password)
        server.sendmail(smtp_sender, recipient_email, msg.as_string())
        server.quit()
        logger.info(f"Certificate email successfully sent to {recipient_email}")
        return True
    except Exception as e:
        logger.error(f"Error sending certificate email to {recipient_email}: {e}")
        return False
