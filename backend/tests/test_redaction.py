import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from redaction import Pseudonyms, redact

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


def test_pseudonyms_repeated_name_reuses_placeholder():
    p = Pseudonyms()
    text, count = p.redact("Inès Moreau leads Messaging. Ask Inès Moreau.")
    assert text == "[NAME_1] leads Messaging. Ask [NAME_1]."
    assert count == 2
    assert p.mapping == {"[NAME_1]": "Inès Moreau"}
    assert p.reverse == {"Inès Moreau": "[NAME_1]"}
    assert p.counts["NAME"] == 1


def test_pseudonyms_number_distinct_values_per_kind():
    p = Pseudonyms()
    text, count = p.redact("Inès Moreau and Omar Haddad: a@b.com")
    assert text == "[NAME_1] and [NAME_2]: [EMAIL_1]"
    assert count == 3
    assert p.counts == {"NAME": 2, "EMAIL": 1, "PHONE": 0}


def test_pseudonyms_restore_known_and_preserve_unknown_placeholders():
    p = Pseudonyms()
    p.redact("Inès Moreau, a@b.com")
    assert p.restore("Contact [NAME_1] at [EMAIL_1]") == "Contact Inès Moreau at a@b.com"
    assert p.restore("Ask [NAME_9] at [EMAIL_9] or [PHONE_9]") == "Ask [NAME_9] at [EMAIL_9] or [PHONE_9]"


def test_pseudonyms_question_and_chunk_share_mapping():
    p = Pseudonyms()
    assert p.redact("Who is Inès Moreau?") == ("Who is [NAME_1]?", 1)
    assert p.redact("Omar Haddad works with Inès Moreau.") == ("[NAME_2] works with [NAME_1].", 2)
    assert Pseudonyms().mapping == {}


def test_pseudonyms_use_existing_phone_and_title_detection():
    p = Pseudonyms()
    original = "Ask Dr. Smith at +33 6 12 34 56 78 or a@b.com. Ask Dr. Smith at a@b.com."
    text, count = p.redact(original)
    assert text == "Ask [NAME_1] at [PHONE_1] or [EMAIL_1]. Ask [NAME_1] at [EMAIL_1]."
    assert count == 5
    assert p.restore(text) == original
    ordinary = "Allow 203.0.113.10, error KST-2044, 08:00-20:00, 2025-01-15, 1 200 EUR, port 5432"
    assert p.redact(ordinary) == (ordinary, 0)
