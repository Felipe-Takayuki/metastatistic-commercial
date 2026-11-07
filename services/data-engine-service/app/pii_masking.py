import hashlib
import re
from typing import Any, List, Optional
from app.schemas import PIIMaskRule


def mask_email(val: str) -> str:
    if not val or not isinstance(val, str) or "@" not in val:
        return "[REDACTED]"
    parts = val.split("@", 1)
    user, domain = parts[0], parts[1]
    if len(user) <= 1:
        masked_user = "*"
    elif len(user) == 2:
        masked_user = f"{user[0]}*"
    else:
        masked_user = f"{user[0]}***{user[-1]}"
    return f"{masked_user}@{domain}"


def mask_cpf(val: str) -> str:
    if not val:
        return "[REDACTED]"
    digits = re.sub(r"\D", "", str(val))
    if len(digits) != 11:
        return "[REDACTED]"
    # CPF formato original: ddd.ddd.ddd-dd -> mascara primeiros 3 e últimos 2: ***.456.789-**
    p2 = digits[3:6]
    p3 = digits[6:9]
    return f"***.{p2}.{p3}-**"


def mask_phone(val: str) -> str:
    if not val:
        return "[REDACTED]"
    digits = re.sub(r"\D", "", str(val))
    if len(digits) >= 10:
        # Exemplo brasileiro: 11 98765 4321 -> (11) 9****-4321
        ddd = digits[:2]
        last4 = digits[-4:]
        if len(digits) == 11:
            first_digit = digits[2]
            return f"({ddd}) {first_digit}****-{last4}"
        else:
            return f"({ddd}) ****-{last4}"
    elif len(digits) >= 8:
        return f"****-{digits[-4:]}"
    return "[REDACTED]"


def hash_sha256(val: Any, salt: str = "") -> str:
    if val is None:
        return "[REDACTED]"
    payload = f"{salt}:{str(val)}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def redact(val: Any) -> str:
    return "[REDACTED]"


def noise_numeric(val: Any, pct: float = 0.05) -> Any:
    if val is None:
        return None
    try:
        num = float(val)
        # Ruído determinístico baseado no hash do valor
        seed = int(hashlib.md5(str(val).encode()).hexdigest()[:8], 16)
        factor = ((seed % 1000) / 1000.0 * 2.0 - 1.0) * pct  # entre -pct e +pct
        res = num * (1.0 + factor)
        return int(round(res)) if isinstance(val, int) else round(res, 4)
    except (ValueError, TypeError):
        return val


def apply_mask_to_value(val: Any, rule: str, tenant_id: str = "") -> Any:
    if val is None:
        return None
    s_val = str(val)
    if rule == "mask_email":
        return mask_email(s_val)
    elif rule == "mask_cpf":
        return mask_cpf(s_val)
    elif rule == "mask_phone":
        return mask_phone(s_val)
    elif rule == "hash_sha256":
        return hash_sha256(val, salt=tenant_id)
    elif rule == "redact":
        return redact(val)
    elif rule == "noise_numeric":
        return noise_numeric(val)
    return val


def apply_pii_masking(
    rows: List[dict[str, Any]], rules: List[PIIMaskRule], tenant_id: str = ""
) -> List[dict[str, Any]]:
    if not rules or not rows:
        return rows

    rule_map = {r.column: r.rule for r in rules}
    result = []
    for row in rows:
        new_row = dict(row)
        for col, rule in rule_map.items():
            if col in new_row:
                new_row[col] = apply_mask_to_value(new_row[col], rule, tenant_id=tenant_id)
        result.append(new_row)
    return result


def auto_detect_and_mask_pii(
    rows: List[dict[str, Any]], tenant_id: str = ""
) -> List[dict[str, Any]]:
    if not rows:
        return rows

    sample_cols = list(rows[0].keys())
    rules: List[PIIMaskRule] = []

    for col in sample_cols:
        col_lower = col.lower().strip()
        if any(term in col_lower for term in ("email", "e_mail", "mail")):
            rules.append(PIIMaskRule(column=col, rule="mask_email"))
        elif any(term in col_lower for term in ("cpf", "documento", "ssn")):
            rules.append(PIIMaskRule(column=col, rule="mask_cpf"))
        elif any(term in col_lower for term in ("phone", "telefone", "celular", "fone")):
            rules.append(PIIMaskRule(column=col, rule="mask_phone"))
        elif any(term in col_lower for term in ("credit_card", "cartao", "card_number")):
            rules.append(PIIMaskRule(column=col, rule="redact"))
        elif any(term in col_lower for term in ("nome", "name", "full_name")):
            rules.append(PIIMaskRule(column=col, rule="hash_sha256"))

    if not rules:
        return rows

    return apply_pii_masking(rows, rules, tenant_id=tenant_id)
