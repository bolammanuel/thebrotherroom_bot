import os
import sys
from dotenv import load_dotenv

# Add project root to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load env variables
load_dotenv()

from email_utils import send_monthly_status_email
import db_manager

def run_test():
    # Make sure DB is initialized so we can run get_stats_data
    db_manager.init_db()
    
    admin_email = os.getenv("ADMIN_EMAIL")
    if not admin_email:
        admin_email = input("Enter the test administrator email address: ").strip()
        
    if not admin_email:
        print("❌ Error: ADMIN_EMAIL is not configured in .env and no address was provided.")
        return

    # Check configuration
    smtp_host = os.getenv("SMTP_HOST")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    
    if not smtp_host or not smtp_user or not smtp_pass:
        print("\n❌ Error: SMTP credentials are not fully configured in your .env file!")
        print("Please ensure the following environment variables are set:")
        print("  - SMTP_HOST (e.g., smtp.gmail.com)")
        print("  - SMTP_PORT (e.g., 587)")
        print("  - SMTP_USER (e.g., your_email@gmail.com)")
        print("  - SMTP_PASSWORD (e.g., your_app_password)")
        return

    print(f"\nAttempting to send monthly status report email to: {admin_email}")
    print(f"SMTP Server: {smtp_host}:{os.getenv('SMTP_PORT', '587')}")
    print(f"SMTP User:   {smtp_user}")
    
    try:
        success = send_monthly_status_email(admin_email)
        if success:
            print("\n✅ Success! The monthly status report email was successfully dispatched.")
        else:
            print("\n❌ Failure. The email utility failed to send. Check logs/terminal for SMTP errors.")
    except Exception as e:
        print(f"\n❌ Error during execution: {e}")

if __name__ == "__main__":
    run_test()
