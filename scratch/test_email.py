import os
import sys
import asyncio
from dotenv import load_dotenv

# Add project root to python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load env variables
load_dotenv()

from email_utils import send_certificate_email

def run_test():
    recipient = input("Enter the test recipient email address: ").strip()
    if not recipient:
        print("Recipient email cannot be empty!")
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
        print("  - SMTP_SENDER (optional, e.g., TBR Team <info@example.com>)")
        return

    print(f"\nAttempting to send a test certificate to: {recipient}")
    print(f"SMTP Server: {smtp_host}:{os.getenv('SMTP_PORT', '587')}")
    print(f"SMTP User:   {smtp_user}")
    
    # We will generate a mock empty file to test attachment delivery
    test_cert_path = "assets/test_certificate_stub.png"
    
    # Ensure assets directory exists
    os.makedirs("assets", exist_ok=True)
    
    # Create a simple dummy text/image stub
    with open(test_cert_path, "wb") as f:
        f.write(b"PNG STUB DATA FOR EMAIL TESTING")
        
    try:
        success = send_certificate_email(recipient, "Test Learner Name", test_cert_path)
        if success:
            print("\n✅ Success! The test certificate email was successfully dispatched.")
        else:
            print("\n❌ Failure. The email utility failed to send. Check logs/terminal for SMTP errors.")
    finally:
        # Clean up
        if os.path.exists(test_cert_path):
            os.remove(test_cert_path)

if __name__ == "__main__":
    run_test()
