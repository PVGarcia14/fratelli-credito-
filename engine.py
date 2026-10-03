from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import re

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
    fields = {
        "Razão social": first_match(text, [r"Raz[aã]o Social\s*[:|]?\s*([^|]{3,120}?)(?=\s+Nome Fantasia|\s+CNPJ|\s+Data)" ]),
        "Nome fantasia": first_match(text, [r"Nome Fantasia\s*[:|]?\s*([^|]{2,120}?)(?=\s+Data|\s+CNPJ|\s+Porte)" ]),
        "Data de abertura": first_match(text, [r"Data da Abertura\s*[:|]?\s*(\d{2}/\d{2}/\d{4})", r"Data de abertura\s*[:|]?\s*(\d{2}/\d{2}/\d{4})"]),
        "Situação cadastral": first_match(text, [r"Situa[cç][aã]o Cadastral\s*[:|]?\s*([^|]{3,40})(?=\s+Data|\s+Capital|\s+Natureza)"]),
        "Natureza jurídica": first_match(text, [r"Natureza Jur[ií]dica\s*[:|]?\s*([^|]{5,120}?)(?=\s+Capital|\s+Porte|\s+CNAE)"]),
        "Capital social": first_match(text, [r"Capital Social\s*[:|]?\s*(R\$\s*[0-9\.\,]+)"]),
        "Porte": first_match(text, [r"Porte\s*[:|]?\s*([^|]{2,50})(?=\s+Natureza|\s+Capital|\s+CNAE)"]),
        "CNAE principal": first_match(text, [r"CNAE principal\s*[:|]?\s*([0-9\.\-/]+\s*-\s*[^|]{4,140})", r"Principal\s*[:|]?\s*([0-9\.\-/]+\s*-\s*[^|]{4,140})"]),
        "Endereço": first_match(text, [r"Logradouro\s*[:|]?\s*([^|]{5,150}?)(?=\s+Bairro|\s+CEP|\s+Munic[ií]pio)"]),
        "Bairro": first_match(text, [r"Bairro\s*[:|]?\s*([^|]{2,80})(?=\s+CEP|\s+Munic[ií]pio)"]),
        "Município/UF": first_match(text, [r"Munic[ií]pio\s*[:|]?\s*([^|]{2,100}?)(?=\s+Estado|\s+CNAE)"]),
        "CEP": first_match(text, [r"CEP\s*[:|]?\s*(\d{5}-\d{3})"]),
        "Telefone": first_match(text, [r"Telefone\s*[:|]?\s*(\(?\d{2}\)?\s*[0-9\- ]{7,20})"]),
    }
    return {k:v for k,v in fields.items() if v}
