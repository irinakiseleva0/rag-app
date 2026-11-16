import re
import unicodedata

EMAIL_RE = re.compile(
    r"(?<![\w.%+-])[\w.%+-]+@[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}\b")

PHONE_RE = re.compile(
    r"(?<![\w.])(?:\+\d{1,3}[ .-]?)?(?:\(\d{1,4}\)[ .-]?)?\d{1,4}(?:[ .-]\d{2,4}){1,5}(?![\w.]\d)")

TITLE_RE = re.compile(
    r"\b(?:(?:Mr|Mrs|Ms|Miss|Dr|Prof|Mme|Mlle)\.?|M\.) ([A-ZÀ-Ý][a-zà-ÿ'-]+)(?: [A-ZÀ-Ý][a-zà-ÿ'-]+)?")

FIRST_NAMES = {
    "adam", "alex", "alice", "amelia", "anna", "antoine", "ben", "camille", "carlos", "charlotte",
    "chloe", "chloé", "claire", "daniel", "david", "elena", "emma", "eric", "fatima", "hugo",
    "inès", "ines", "irina", "isabelle", "james", "jean", "john", "jonas", "julia", "julien",
    "karim", "laura", "léa", "lea", "louis", "lucas", "maria", "marie", "martin",
    "mohamed", "nathan", "nicolas", "olivia", "omar", "paul", "paulo", "pierre", "priya", "rahul",
    "sam", "samuel", "sara", "sarah", "sophie", "thomas", "tom", "tomasz", "yuki", "zoe",
}

NAME_RE = re.compile(r"\b(?:" + "|".join(n.capitalize()
                     for n in FIRST_NAMES) + r")\b(?: [A-ZÀ-Ý][a-zà-ÿ'-]+)?")


def is_phone(match):
    digits = re.sub(r"\D", "", match)
    if len(digits) < 9 or len(digits) > 15:
        return False
    parts = re.split(r"[ .-]", match.strip("+"))
    if "." in match and " " not in match and "-" not in match and len(parts) == 4:
        return False
    return True


def redact(text, names=True):
    found = 0
    text = unicodedata.normalize("NFC", text)

    def email(m):
        nonlocal found
        found += 1
        return "[EMAIL]"

    def phone(m):
        nonlocal found
        if not is_phone(m.group(0)):
            return m.group(0)
        found += 1
        return "[PHONE]"

    def title(m):
        nonlocal found
        found += 1
        return "[NAME]"

    def name(m):
        nonlocal found
        found += 1
        return "[NAME]"

    text = EMAIL_RE.sub(email, text)
    text = PHONE_RE.sub(phone, text)
    if names:
        text = TITLE_RE.sub(title, text)
        text = NAME_RE.sub(name, text)
    return text, found


class Pseudonyms:
    """Keep reversible placeholders in memory for one question and its passages."""

    def __init__(self):
        self.mapping: dict[str, str] = {}
        self.reverse: dict[str, str] = {}
        self.counts = {"EMAIL": 0, "PHONE": 0, "NAME": 0}

    def redact(self, text):
        found = 0
        text = unicodedata.normalize("NFC", text)

        def replace(match, kind):
            nonlocal found
            original = match.group(0)
            if kind == "PHONE" and not is_phone(original):
                return original
            found += 1
            if original not in self.reverse:
                self.counts[kind] += 1
                placeholder = f"[{kind}_{self.counts[kind]}]"
                self.mapping[placeholder] = original
                self.reverse[original] = placeholder
            return self.reverse[original]

        text = EMAIL_RE.sub(lambda match: replace(match, "EMAIL"), text)
        text = PHONE_RE.sub(lambda match: replace(match, "PHONE"), text)
        text = TITLE_RE.sub(lambda match: replace(match, "NAME"), text)
        text = NAME_RE.sub(lambda match: replace(match, "NAME"), text)
        return text, found

    def restore(self, text):
        return re.sub(r"\[(?:EMAIL|PHONE|NAME)_\d+\]",
                      lambda match: self.mapping.get(match.group(0), match.group(0)), text)
