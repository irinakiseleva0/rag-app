import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from redaction import redact

def test_email():
    text, n = redact("Write to billing@kestrel.example for invoices.")
    assert text == "Write to [EMAIL] for invoices."
    assert n == 1

def test_email_with_dots_and_plus():
    text, n = redact("My mail is paulo.g+rag@mail.example.com")
    assert "[EMAIL]" in text
    assert "@" not in text
    assert n == 1

def test_phone_french():
    text, n = redact("Call 06 12 34 56 78 or +33 6 12 34 56 78 or 06.12.34.56.78")
    assert text == "Call [PHONE] or [PHONE] or [PHONE]"
    assert n == 3

def test_phone_us():
    text, n = redact("Call (555) 123-4567 or +1 415 555 0199")
    assert text == "Call [PHONE] or [PHONE]"
    assert n == 2

def test_name_from_first_name_list():
    text, n = redact("| Messaging | Inès Moreau | #oncall-messaging |")
    assert text == "| Messaging | [NAME] | #oncall-messaging |"
    assert n == 1

def test_name_after_capital_word():
    text, n = redact("Ask Inès Moreau or Jonas Berg.")
    assert text == "Ask [NAME] or [NAME]."
    assert n == 2

def test_name_with_title():
    text, n = redact("Ask Dr. Smith or Mrs Dupont.")
    assert text == "Ask [NAME] or [NAME]."
    assert n == 2

def test_not_personal_data():
    text = "Allow 203.0.113.10, error KST-2044, 08:00-20:00, 2025-01-15, 1 200 EUR, port 5432"
    assert redact(text) == (text, 0)

def test_product_and_team_names_kept():
    text = "Kestrel Analytics, Payments Core, American Express, Google Sheets, Business plan"
    assert redact(text) == (text, 0)

def test_known_misses():
    text, n = redact("my name is paulo, ask Kowalski")
    assert n == 0

def test_count_all():
    text, n = redact("Samuel Okafor (samuel@kestrel.example, +44 20 7946 0958)")
    assert text == "[NAME] ([EMAIL], [PHONE])"
    assert n == 3

def test_empty():
    assert redact("") == ("", 0)