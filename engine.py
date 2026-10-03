from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import re
import math

WEIGHTS = {
    "Cadastro e estabilidade": 15,
    "Estrutura empresarial": 15,
    "Histórico público": 20,
    "Capacidade empresarial": 20,
    "Confiabilidade das informações": 10,
    "Histórico comercial identificado": 20,
}
MISSING_FACTOR = 0.25


def clean_cnpj(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))


def validate_cnpj(value: str) -> Tuple[bool, str]:
    d = clean_cnpj(value)
    if len(d) != 14 or len(set(d)) == 1:
        return False, "CNPJ inválido: informe os 14 dígitos."
    nums = [int(x) for x in d]
    w1 = [5,4,3,2,9,8,7,6,5,4,3,2]
    r1 = sum(a*b for a,b in zip(nums[:12], w1)) % 11
    d1 = 0 if r1 < 2 else 11-r1
    w2 = [6,5,4,3,2,9,8,7,6,5,4,3,2]
    r2 = sum(a*b for a,b in zip(nums[:13], w2)) % 11
    d2 = 0 if r2 < 2 else 11-r2
    if nums[12] != d1 or nums[13] != d2:
        return False, "CNPJ inválido: dígitos verificadores não conferem."
    return True, f"CNPJ válido matematicamente: {d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def score_from_evidence(items: Dict[str, Optional[float]]) -> Tuple[float, float, List[str]]:
    total = sum(WEIGHTS.values())
    score = 0.0
    observed_weight = 0.0
    missing = []
    for name, weight in WEIGHTS.items():
        value = items.get(name)
        if value is None:
            value = 100 * MISSING_FACTOR
            missing.append(name)
        else:
            observed_weight += weight
        score += weight * max(0, min(100, float(value)))
    return round(score / total, 1), round(observed_weight / total * 100, 1), missing


def risk_band(score: float) -> str:
    if score < 25: return "MUITO ELEVADO"
    if score < 35: return "ELEVADO"
    if score < 45: return "MODERADO-ALTO"
    if score < 55: return "MODERADO"
    if score <= 70: return "CONTROLADO"
    return "BAIXO"


def policy_ceiling(score: float, requested: float) -> Tuple[float, str, str]:
    if score < 25:
        return 0.0, "< 25", "NÃO VENDER A PRAZO"
    if score < 35:
        return 1500.0, "25 a <35", "ATÉ R$ 1.500"
    if score < 45:
        return 5000.0, "35 a <45", "ATÉ R$ 5.000"
    if score < 55:
        return 10000.0, "45 a <55", "ATÉ R$ 10.000"
    if score <= 70:
        return 20000.0, "55 a 70", "ATÉ R$ 20.000"
    return max(0.0, requested), "> 70", "ANALISAR O VALOR SOLICITADO"


def decision(score: float, requested: float, financial_available: float, coverage: float, hard_block: bool=False) -> Dict[str, Any]:
    ceiling, band, policy = policy_ceiling(score, requested)
    if hard_block:
        return {"status":"RECUSAR", "approved":0.0, "ceiling":ceiling, "band":band,
                "reason":"Bloqueio crítico confirmado."}
    if coverage < 50:
        return {"status":"REVISÃO MANUAL", "approved":0.0, "ceiling":ceiling, "band":band,
                "reason":"Cobertura de evidências inferior a 50%."}
    if score < 25:
        return {"status":"RECUSAR", "approved":0.0, "ceiling":0.0, "band":band,
                "reason":"Score abaixo de 25: política determina não vender a prazo."}
    if requested <= 0:
        return {"status":"LIMITE DISPONÍVEL", "approved":0.0, "ceiling":ceiling, "band":band,
                "reason":policy}
    effective = min(ceiling, max(0.0, financial_available))
    if requested <= effective:
        return {"status":"APROVAR", "approved":requested, "ceiling":ceiling, "band":band,
                "reason":"Pedido dentro do teto de política e do limite financeiro disponível."}
    if effective > 0:
        return {"status":"APROVAR COM LIMITE", "approved":effective, "ceiling":ceiling, "band":band,
                "reason":"Pedido excede o limite calculado; aprovar somente o valor permitido."}
    return {"status":"RECUSAR", "approved":0.0, "ceiling":ceiling, "band":band,
            "reason":"Não há limite financeiro disponível para o pedido."}



def suggest_automatic_mix(approved_limit: float, products: List[Dict[str, Any]],
                         tiers: Optional[List[Dict[str, Any]]] = None,
                         seed: Optional[int] = None, max_boxes_per_product: int = 60) -> Dict[str, Any]:
    """Build the best whole-box B2B composition automatically."""
    from itertools import product as cartesian_product
    import random

    limit = max(0.0, float(approved_limit or 0))
    valid = [x for x in (products or [])
             if float(x.get("unit_price", 0) or 0) > 0
             and int(x.get("units_per_box", 0) or 0) > 0]
    if limit <= 0 or not valid:
        return {"status": "SEM_CREDITO", "items": [], "gross": 0.0,
                "discount": 0.0, "net": 0.0, "remaining": limit,
                "units": 0, "discount_pct": 0.0, "tier": None}

    tiers = tiers or []
    valid = valid[:3]
    min_discount = min([float(t.get("discount_pct", 0) or 0) for t in tiers] or [0.0])
    ranges = []
    for x in valid:
        box_gross = float(x["unit_price"]) * int(x["units_per_box"])
        box_floor = box_gross * (1 - min_discount / 100.0)
        upper = int(limit // box_floor) + 1 if box_floor > 0 else 0
        ranges.append(range(0, min(max_boxes_per_product, upper) + 1))

    candidates = []
    for counts in cartesian_product(*ranges):
        if not any(counts):
            continue
        gross = 0.0
        units = 0
        for x, boxes in zip(valid, counts):
            gross += boxes * float(x["unit_price"]) * int(x["units_per_box"])
            units += boxes * int(x["units_per_box"])
        discount_pct = discount_for_quantity(units, tiers)
        net = round(gross * (1 - discount_pct / 100.0), 2)
        if net <= limit + 1e-9:
            diversity = sum(1 for b in counts if b > 0)
            total_boxes = sum(counts)
            candidates.append((net, diversity, -total_boxes, counts, gross, units, discount_pct))

    if not candidates:
        return {"status": "SEM_COMBINACAO", "items": [], "gross": 0.0,
                "discount": 0.0, "net": 0.0, "remaining": limit,
                "units": 0, "discount_pct": 0.0, "tier": None}

    best_net = max(x[0] for x in candidates)
    near = [x for x in candidates if x[0] >= best_net - max(1.0, best_net * 0.005)]
    max_diversity = max(x[1] for x in near)
    near = [x for x in near if x[1] == max_diversity]
    chosen = random.Random(seed).choice(near)
    net, _, _, counts, gross, units, discount_pct = chosen

    items = []
    for x, boxes in zip(valid, counts):
        if boxes <= 0:
            continue
        box_gross = float(x["unit_price"]) * int(x["units_per_box"])
        items.append({
            "name": x["name"], "boxes": int(boxes),
            "units": int(boxes) * int(x["units_per_box"]),
            "unit_price": float(x["unit_price"]),
            "units_per_box": int(x["units_per_box"]),
            "box_value": round(box_gross, 2),
            "gross": round(boxes * box_gross, 2),
        })

    tier_label = None
    for t in tiers:
        mn = int(t.get("min_units", 0) or 0); mx = t.get("max_units")
        if units >= mn and (mx is None or units <= int(mx)):
            tier_label = t.get("label") or f"{discount_pct:.1f}%"
            break

    return {
        "status": "OK", "items": items, "gross": round(gross, 2),
        "discount": round(gross - net, 2), "net": net,
        "remaining": round(max(0.0, limit - net), 2),
        "units": units, "discount_pct": discount_pct, "tier": tier_label,
    }

def public_confidence(source_count: int, successful_sources: int, conflicts: int, documented_fields: int) -> float:
    if source_count <= 0:
        return 0.0
    source_ratio = successful_sources / source_count
    conflict_penalty = min(0.35, conflicts * 0.05)
    field_bonus = min(0.25, documented_fields / 40)
    return round(max(0.0, min(1.0, 0.45*source_ratio + 0.35*field_bonus + 0.20*(1-conflict_penalty))), 3)


def normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def first_match(text: str, patterns: List[str]) -> Optional[str]:
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return normalize_text(m.group(1)).strip(" |:")
    return None


def parse_public_page(text: str) -> Dict[str, Any]:
    """Extract stable company fields from public company pages.

    The location parser deliberately stops at known field labels so page-menu text
    cannot leak into the municipality value. Age/status are derived later in the UI
    from the opening date and the cadastral status, respectively.
    """
    t = normalize_text(text)
    fields = {
        "Razão social": first_match(t, [r"Raz[aã]o Social\s*[:|]?\s*([^|]{3,120}?)(?=\s+Nome Fantasia|\s+CNPJ|\s+Data)" ]),
        "Nome fantasia": first_match(t, [r"Nome Fantasia\s*[:|]?\s*([^|]{2,120}?)(?=\s+Data|\s+CNPJ|\s+Porte)" ]),
        "Data de abertura": first_match(t, [r"Data da Abertura\s*[:|]?\s*(\d{2}/\d{2}/\d{4})", r"Data de abertura\s*[:|]?\s*(\d{2}/\d{2}/\d{4})", r"In[ií]cio de atividade\s*[:|]?\s*(\d{2}/\d{2}/\d{4})"]),
        "Situação cadastral": first_match(t, [r"Situa[cç][aã]o Cadastral\s*[:|]?\s*([A-ZÁÀÃÂÉÊÍÓÔÕÚÇ][^|]{2,40}?)(?=\s+Data|\s+Capital|\s+Natureza|\s+Porte)", r"Situa[cç][aã]o\s*[:|]?\s*(ATIVA|INATIVA|SUSPENSA|INAPTA|BAIXADA)"]),
        "Natureza jurídica": first_match(t, [r"Natureza Jur[ií]dica\s*[:|]?\s*([^|]{5,120}?)(?=\s+Capital|\s+Porte|\s+CNAE)"]),
        "Capital social": first_match(t, [r"Capital Social\s*[:|]?\s*(R\$\s*[0-9\.\,]+)"]),
        "Porte": first_match(t, [r"Porte\s*[:|]?\s*([^|]{2,50})(?=\s+Natureza|\s+Capital|\s+CNAE)", r"Enquadramento de Porte\s*[:|]?\s*([^|]{2,50})"]),
        "CNAE principal": first_match(t, [r"CNAE principal\s*[:|]?\s*([0-9\.\-/]+\s*\-\s*[^|]{4,140})", r"Principal\s*[:|]?\s*([0-9\.\-/]+\s*\-\s*[^|]{4,140})"]),
        "Endereço": first_match(t, [r"Logradouro\s*[:|]?\s*([^|]{5,150}?)(?=\s+Bairro|\s+CEP|\s+Munic[ií]pio)", r"Endere[cç]o\s*[:|]?\s*([^|]{5,150}?)(?=\s+Bairro|\s+CEP|\s+Munic[ií]pio)"]),
        "Bairro": first_match(t, [r"Bairro\s*[:|]?\s*([^|]{2,80})(?=\s+CEP|\s+Munic[ií]pio)"]),
        "Município/UF": first_match(t, [r"Munic[ií]pio\s*/?\s*UF\s*[:|]?\s*([A-Za-zÀ-ÿ'’\- ]{2,80})", r"Munic[ií]pio\s*[:|]?\s*([A-Za-zÀ-ÿ'’\- ]{2,80}?)(?=\s+Estado\b|\s+CNAE\b|\s+CEP\b)", r"Munic[ií]pio\s*[:|]?\s*([A-Za-zÀ-ÿ'’\- ]{2,80},\s*[A-Z]{2})"]),
        "CEP": first_match(t, [r"CEP\s*[:|]?\s*(\d{5}-\d{3})"]),
        "Telefone": first_match(t, [r"Telefone\s*[:|]?\s*(\(?\d{2}\)?\s*[0-9\- ]{7,20})"]),
    }
    # Guard against navigation/UI text accidentally captured as municipality.
    loc = fields.get("Município/UF")
    if loc:
        loc = normalize_text(loc)
        bad_tokens = ("entrar", "minha conta", "sair", "assistente", "home", "empresas", "dados de")
        if any(tok in loc.lower() for tok in bad_tokens) or len(loc) > 60:
            fields["Município/UF"] = None
        else:
            fields["Município/UF"] = loc
    return {k:v for k,v in fields.items() if v}


# --- 6.0.2: commercial simulation (generic B2B, product-agnostic) ---
DEFAULT_BOX_UNITS = 9

def calculate_box_value(unit_price: float, units_per_box: int = DEFAULT_BOX_UNITS) -> float:
    """Return the gross value of one box for a configurable product."""
    unit_price = max(0.0, float(unit_price or 0))
    units_per_box = max(1, int(units_per_box or 1))
    return round(unit_price * units_per_box, 2)


def quantity_within_limit(limit: float, box_value: float, units_per_box: int = DEFAULT_BOX_UNITS) -> Dict[str, Any]:
    """Calculate the maximum whole boxes and units that fit without exceeding a limit."""
    limit = max(0.0, float(limit or 0))
    box_value = max(0.0, float(box_value or 0))
    units_per_box = max(1, int(units_per_box or 1))
    if box_value <= 0:
        return {"boxes": 0, "units": 0, "gross": 0.0, "remainder": limit}
    boxes = int(math.floor((limit + 1e-9) / box_value))
    gross = round(boxes * box_value, 2)
    return {"boxes": boxes, "units": boxes * units_per_box, "gross": gross,
            "remainder": round(max(0.0, limit - gross), 2)}


def discount_for_quantity(units: int, tiers: List[Dict[str, Any]]) -> float:
    """Return the configured discount percentage for a quantity of units."""
    units = max(0, int(units or 0))
    selected = 0.0
    for tier in tiers or []:
        min_units = max(0, int(tier.get("min_units", 0)))
        max_units = tier.get("max_units")
        pct = max(0.0, min(100.0, float(tier.get("discount_pct", 0) or 0)))
        if units >= min_units and (max_units is None or units <= int(max_units)):
            selected = max(selected, pct)
    return selected


def simulate_order(unit_price: float, boxes: int, units_per_box: int = DEFAULT_BOX_UNITS,
                   tiers: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Simulate a generic B2B order using configurable box size and discount tiers."""
    unit_price = max(0.0, float(unit_price or 0))
    boxes = max(0, int(boxes or 0))
    units_per_box = max(1, int(units_per_box or 1))
    units = boxes * units_per_box
    gross = round(units * unit_price, 2)
    discount_pct = discount_for_quantity(units, tiers or [])
    discount = round(gross * discount_pct / 100.0, 2)
    net = round(gross - discount, 2)
    return {
        "boxes": boxes, "units": units, "unit_price": unit_price,
        "box_value": calculate_box_value(unit_price, units_per_box),
        "gross": gross, "discount_pct": discount_pct,
        "discount": discount, "net": net
    }


def max_boxes_by_approved_limit(approved_limit: float, unit_price: float,
                                units_per_box: int = DEFAULT_BOX_UNITS,
                                tiers: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Find the largest whole-box order whose net value does not exceed the approved limit."""
    approved_limit = max(0.0, float(approved_limit or 0))
    unit_price = max(0.0, float(unit_price or 0))
    units_per_box = max(1, int(units_per_box or 1))
    if unit_price <= 0:
        return {"boxes": 0, "units": 0, "gross": 0.0, "discount": 0.0, "net": 0.0}
    # A safe finite upper bound comes from the no-discount value.
    upper = int(math.floor(approved_limit / calculate_box_value(unit_price, units_per_box))) + 1
    best = {"boxes": 0, "units": 0, "gross": 0.0, "discount": 0.0, "net": 0.0}
    for boxes in range(1, max(0, upper) + 1):
        sim = simulate_order(unit_price, boxes, units_per_box, tiers)
        if sim["net"] <= approved_limit + 1e-9:
            best = sim
    return best
