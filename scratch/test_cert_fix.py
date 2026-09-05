import os
import datetime
from bot import generate_certificate_image
from db_manager import sanitize_learner_name

test_cases = [
    (
        "Corrupted multi-line block string",
        "Full Name: Gbaeren, Tersoo James\nEmail Address: Gbaerenjames4God@Gmail.Com\nState Of Residence: Cross River State",
        1001
    ),
    (
        "Very long name (testing dynamic font auto-scaling)",
        "His Excellency Prince Emmanuel Oluwaseun Alexander Montgomery III",
        1002
    ),
    (
        "Standard name",
        "Tersoo James Gbaeren",
        1003
    )
]

current_date = datetime.datetime.now().strftime("%B %d, %Y")

print("--- TESTING NAME SANITIZATION AND CERTIFICATE GENERATION ---")
for label, raw_name, user_id in test_cases:
    clean_name = sanitize_learner_name(raw_name)
    output_file = generate_certificate_image(raw_name, current_date, user_id)
    print(f"\n[Test Case: {label}]")
    print(f"Raw Input : {repr(raw_name)}")
    print(f"Cleaned   : {repr(clean_name)}")
    print(f"Output File: {output_file}")

print("\n✅ All certificates generated successfully!")
