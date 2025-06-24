from datetime import datetime, timedelta, UTC
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.utils import make_msgid
import os
from connect import connect

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("renewal_email_notifier.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

SMTP_SERVER = 'smtp.office365.com'
SMTP_PORT = 587
SMTP_USER = os.getenv('MAIL_USERNAME')
SMTP_PASS = os.getenv('MAIL_PASSWORD')
DEFAULT_SENDER = os.getenv('MAIL_DEFAULT_SENDER')
LOGO_PATH = 'logo.jpg'  # Path to the Ribbon Demographics logo


def get_subscriptions_to_notify():
    today = datetime.now(UTC).date()
    renewal_offsets = [30, 60, 3]
    dates = {offset: today + timedelta(days=offset) for offset in renewal_offsets}
    logging.info(dates)
    conn = connect()
    cursor = conn.cursor()

    notifications = {}

    try:
        for offset in [60, 30]:
            cursor.execute("""
                SELECT s.id AS sub_id, c.company_name, c.id AS company_id, s.renewal_date,
                       p.billing_cycle, u.email, u.fname, u.lname, rt.report_name
                FROM subscriptions_draft s
                JOIN company c ON s.company_id = c.id
                JOIN subscription_pricing p ON s.pricing_id = p.id
                JOIN users u ON u.company_id = c.id AND u.super_user_id IS NULL AND u.is_admin = 1
                JOIN report_types rt ON p.report_type_id = rt.id
                WHERE LOWER(p.billing_cycle) = 'annual'
                AND s.renewal_date = %s
            """, (dates[offset],))
            for row in cursor.fetchall():
                key = (row['email'], offset, row['fname'], row['lname'])
                notifications.setdefault(key, []).append(row)

        cursor.execute("""
            SELECT s.id AS sub_id, c.company_name, c.id AS company_id, s.renewal_date,
                   p.billing_cycle, p.national_price, u.email, u.fname, u.lname, rt.report_name
            FROM subscriptions_draft s
            JOIN company c ON s.company_id = c.id
            JOIN subscription_pricing p ON s.pricing_id = p.id
            JOIN users u ON u.company_id = c.id AND u.super_user_id IS NULL AND u.is_admin = 1
            JOIN report_types rt ON p.report_type_id = rt.id
            WHERE LOWER(p.billing_cycle) = 'monthly'
            AND s.renewal_date = %s
            AND p.national_price > 0
        """, (dates[3],))
        for row in cursor.fetchall():
            key = (row['email'], 3, row['fname'], row['lname'])
            notifications.setdefault(key, []).append(row)

    finally:
        cursor.close()
        conn.close()

    return notifications


def send_renewal_email(email, days_out, subscriptions, fname, lname):
    msg = MIMEMultipart('related')
    msg['Subject'] = f"Upcoming Subscription Renewal in {days_out} Days"
    msg['From'] = DEFAULT_SENDER
    msg['To'] = email

    logo_cid = make_msgid(domain='ribbondemographics.com')[1:-1]  # strip <>

    html = f"""
    <html>
      <body>
        <div style='text-align: center;'>
          <img src="cid:{logo_cid}" alt="Ribbon Demographics Logo" width="150"><br><br>
        </div>
        <p>Hi {fname} {lname},</p>
        <p>This is a friendly reminder that the following Ribbon DAS subscription(s) are set to renew in 
        <strong>{days_out} days</strong>:</p>
        <ul>
    """

    for sub in subscriptions:
        html += f"<li>{sub['company_name']} — {sub['report_name']} (Renewal Date: {sub['renewal_date']})</li>"

    html += """
        </ul>
        <p>If you have any questions, feel free to reach out to our support team. You can also manage your subscriptions
        by logging into your DAS account and going to Account Settings > Manage Subscriptions.</p>
        <p>– Ribbon Demographics</p>
      </body>
    </html>
    """

    msg.attach(MIMEText(html, 'html'))

    try:
        with open(LOGO_PATH, 'rb') as img:
            logo = MIMEImage(img.read())
            logo.add_header('Content-ID', f'<{logo_cid}>')
            msg.attach(logo)
    except Exception as e:
        logger.warning(f"Logo not attached: {e}")

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
            logger.info(f"Email sent to {email} for {days_out}-day renewal notice.")
    except Exception as e:
        logger.error(f"Failed to send email to {email}: {e}")


def main():
    notifications = get_subscriptions_to_notify()
    logging.info(notifications)
    for (email, days_out, fname, lname), subs in notifications.items():
        send_renewal_email(email, days_out, subs, fname, lname)


if __name__ == '__main__':
    main()
