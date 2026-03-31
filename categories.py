from config import MEN_CLASSES, WOMEN_CLASSES


def normalize_gender(value: str) -> str:
    if value is None:
        return ""

    v = str(value).strip().lower()

    if v == "мужчина":
        return "M"
    if v == "женщина":
        return "W"

    return ""


def parse_weight(value) -> float | None:
    if value is None:
        return None

    s = str(value).strip().replace(",", ".")
    if not s:
        return None

    try:
        return float(s)
    except ValueError:
        return None


def get_weight_class(gender: str, weight: float) -> tuple[str, str]:
    if gender == "M":
        for limit in MEN_CLASSES:
            if weight <= limit:
                return f"до {limit} кг", f"M_{limit}"
        return "выше 90 кг", "M_PLUS"

    if gender == "W":
        for limit in WOMEN_CLASSES:
            if weight <= limit:
                return f"до {limit} кг", f"W_{limit}"
        return "выше 60 кг", "W_PLUS"

    return "", ""