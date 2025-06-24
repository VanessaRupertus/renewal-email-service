from datetime import datetime, timedelta
import logging
import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

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


def send_renewal_email(to_address, company_name, days_out):
    msg = EmailMessage()
    msg['Subject'] = f"Subscription Renewal in {days_out} Days"
    msg['From'] = os.getenv('MAIL_DEFAULT_SENDER')
    msg['To'] = to_address

    msg.set_content(f"""
    Hello {company_name},

    This is a reminder that your subscription is set to renew in {days_out} days.

    If you have any questions or need to make changes to your plan, please contact support.

    — The Ribbon Team
    """)

    try:
        with smtplib.SMTP_SSL('smtp.office365.com', 465) as smtp:
            smtp.login(os.getenv('MAIL_USERNAME'), os.getenv('MAIL_PASSWORD'))
            smtp.send_message(msg)
        logger.info(f"Email sent to {to_address} for {company_name} ({days_out} days out).")
    except Exception as e:
        logger.error(f"Failed to send email to {to_address}: {e}")


def get_subscriptions_to_notify():
    from connect import connect

    today = datetime.utcnow().date()
    renewal_offsets = [30, 60, 3]  # Days before renewal to notify
    dates = {offset: today + timedelta(days=offset) for offset in renewal_offsets}

    conn = connect()
    cursor = conn.cursor()

    results = []

    try:
        # Annual notifications (60, 30 days out)
        for offset in [60, 30]:
            cursor.execute("""
                SELECT s.id AS sub_id, c.company_name, c.id AS company_id, s.renewal_date,
                       p.billing_cycle, u.email
                FROM subscriptions_draft s
                JOIN company c ON s.company_id = c.id
                JOIN subscription_pricing p ON s.pricing_id = p.id
                JOIN users u ON u.company_id = c.id AND u.super_user_id IS NULL AND u.is_admin = 1
                WHERE LOWER(p.billing_cycle) = 'annual'
                AND s.renewal_date = %s
            """, (dates[offset],))
            for row in cursor.fetchall():
                results.append((row, offset))

        # Monthly notifications (3 days out, price > 0)
        cursor.execute("""
            SELECT s.id AS sub_id, c.company_name, c.id AS company_id, s.renewal_date,
                   p.billing_cycle, p.national_price, u.email
            FROM subscriptions_draft s
            JOIN company c ON s.company_id = c.id
            JOIN subscription_pricing p ON s.pricing_id = p.id
            JOIN users u ON u.company_id = c.id AND u.super_user_id IS NULL AND u.is_admin = 1
            WHERE LOWER(p.billing_cycle) = 'monthly'
            AND s.renewal_date = %s
            AND p.national_price > 0
        """, (dates[3],))
        for row in cursor.fetchall():
            results.append((row, 3))

    finally:
        cursor.close()
        conn.close()

    return results


def main():
    notifications = get_subscriptions_to_notify()
    for row, days_out in notifications:
        email = row.get('email')
        if email:
            send_renewal_email(email, row['company_name'], days_out)
        else:
            logger.warning(f"No email found for company '{row['company_name']}', skipping email.")


if __name__ == '__main__':
    main()
