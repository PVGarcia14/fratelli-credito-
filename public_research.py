from __future__ import annotations
from datetime import datetime
from urllib.parse import quote
from typing import Dict, Any, List
import re
import requests
from bs4 import BeautifulSoup
try:
    from engine import clean_cnpj, parse_public_page, normalize_text
except ImportError:
    from .engine import clean_cnpj, parse_public_page, normalize_text

UA = "Mozilla/5.0 (compatible; Fratelli-B2B-Credit/6.0; +public-web-research)"

DIRECT_SOURCES = [
    ("CNPJ.BIZ", "https://cnpj.biz/{cnpj}"),
    ("CNPJ.ai", "https://cnpj.ai/{cnpj}"),
]
SEARCH_TARGETS = [
    ("Google — CNPJ", "https://www.google.com/search?q={q}"),
    ("DuckDuckGo — CNPJ", "https://html.duckduckgo.com/html/?q={q}"),
    ("Google — processos", "https://www.google.com/search?q={q}+processos"),
    ("Google — notícias", "https://www.google.com/search?q={q}+notícias"),
]
JUSBRASIL_SEARCH = "https://www.jusbrasil.com.br/consulta-processual/?q={q}"

MANUAL_PUBLIC_SOURCES = [
    ("Receita Federal / Redesim", "https://www.gov.br/empresas-e-negocios/pt-br/redesim"),
    ("SINTEGRA", "http://www.sintegra.gov.br/"),
    ("Portal da Transparência", "https://portaldatransparencia.gov.br/"),
    ("Diário Oficial da União", "https://www.in.gov.br/"),
    ("CNJ", "https://www.cnj.jus.br/"),
    ("Junta Comercial — pesquisa manual", "https://www.gov.br/empresas-e-negocios/pt-br/redesim"),
]


def fetch(url: str) -> Dict[str, Any]:
    started = datetime.now().isoformat(timespec="seconds")
    try:
        r = requests.get(url, timeout=12, headers={"User-Agent": UA}, allow_redirects=True)
        if r.status_code >= 400:
            return {"ok":False,"status":r.status_code,"url":url,"text":"","started":started}
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script","style","noscript","svg"]):
            tag.decompose()
        text = " ".join(soup.stripped_strings)
        return {"ok":True,"status":r.status_code,"url":r.url,"text":text[:300000],"started":started}
    except Exception as e:
        return {"ok":False,"status":None,"url":url,"text":"","error":str(e),"started":started}



def extract_partners(text: str) -> List[Dict[str, str]]:
    """Extract QSA names/roles from public company pages when the page exposes them."""
    clean = normalize_text(text)
    out: List[Dict[str, str]] = []
    patterns = [
        r"Quadro de S[oó]cios e Administradores\s+(.*?)(?=\s+Sobre\b|\s+FAQ\b|\s+Rede societ[aá]ria\b|\s+Linha do Tempo\b|$)",
        r"Quadro de s[oó]cios e administradores\s+(.*?)(?=\s+Rede societ[aá]ria\b|\s+Fichas\b|$)",
    ]
    block = None
    for pat in patterns:
        m = re.search(pat, clean, re.I)
        if m:
            block = m.group(1)
            break
    if block:
        role_re = r"([A-ZÀ-Ú][A-ZÀ-Úa-zà-ú.'-]+(?:\s+[A-ZÀ-Úa-zà-ú.'-]+){1,12})\s+-\s+(Sócio-Administrador|Sócio|Administrador|Diretor|Presidente|Gerente)"
        for m in re.finditer(role_re, block, re.I):
            name = normalize_text(m.group(1))
            role = normalize_text(m.group(2))
            if len(name) >= 5 and not any(x["name"].upper() == name.upper() for x in out):
                out.append({"name": name, "role": role})
    # Common cnpj.ai/cnpj.biz one-line representation.
    if not out:
        role_re = r"\b([A-ZÀ-Ú][A-ZÀ-Úa-zà-ú.'-]+(?:\s+[A-ZÀ-Úa-zà-ú.'-]+){1,12})\s+-\s+(Sócio-Administrador|Sócio|Administrador|Diretor|Presidente|Gerente)\b"
        for m in re.finditer(role_re, clean, re.I):
            name = normalize_text(m.group(1))
            role = normalize_text(m.group(2))
            if len(name) >= 5 and not any(x["name"].upper() == name.upper() for x in out):
                out.append({"name": name, "role": role})
    return out


def search_jusbrasil(query: str) -> Dict[str, Any]:
    """Search the publicly accessible Jusbrasil process-search page.
    If Jusbrasil requires login/payment or blocks automated access, report that explicitly.
    """
    q = normalize_text(query)
    url = JUSBRASIL_SEARCH.format(q=quote(q))
    row = fetch(url)
    result = {
        "source": "Jusbrasil",
        "query": q,
        "url": row.get("url") or url,
        "ok": bool(row.get("ok")),
        "status": row.get("status"),
        "snippet": " ".join(row.get("text", "").split())[:8000],
        "available_publicly": bool(row.get("ok")),
    }
    if not row.get("ok"):
        result["note"] = "Fonte não disponível publicamente neste acesso; o sistema não deve inferir ausência de processos."
    return result

def research_company(cnpj: str) -> Dict[str, Any]:
    c = clean_cnpj(cnpj)
    result = {"queried_at":datetime.now().isoformat(timespec="seconds"),"cnpj":c,"sources":[],"fields":{},"field_sources":{},"conflicts":[],"search_leads":[],"partners":[],"partner_sources":{},"partner_judicial":[],"manual_sources":MANUAL_PUBLIC_SOURCES}
    if len(c) != 14:
        result["error"] = "CNPJ inválido."
        return result
    all_fields: Dict[str, List[tuple]] = {}
    for name, template in DIRECT_SOURCES:
        row = fetch(template.format(cnpj=c))
        row.update({"source":name,"kind":"direct"})
        if row.get("ok"):
            fields = parse_public_page(row.get("text",""))
            row["fields"] = fields
            partners = extract_partners(row.get("text", ""))
            row["partners"] = partners
            for partner in partners:
                if not any(p["name"].upper() == partner["name"].upper() for p in result["partners"]):
                    result["partners"].append(partner)
                result["partner_sources"].setdefault(partner["name"], []).append(name)
            for k,v in fields.items():
                all_fields.setdefault(k,[]).append((name,v))
        result["sources"].append(row)
    # Search pages are treated as discovery evidence, not as authoritative records.
    queries = [c, f'"{c}" empresa']
    for q in queries:
        for name, template in SEARCH_TARGETS[:2]:
            row = fetch(template.format(q=quote(q)))
            row.update({"source":name,"kind":"search"})
            if row.get("ok"):
                snippet = " ".join(row.get("text","").split())[:5000]
                result["search_leads"].append({"source":name,"query":q,"url":row.get("url"),"snippet":snippet})
            result["sources"].append(row)
    for field, vals in all_fields.items():
        result["field_sources"][field] = vals
        unique = {v.strip().upper() for _,v in vals}
        if len(unique) > 1:
            result["conflicts"].append({"field":field,"values":[{"source":s,"value":v} for s,v in vals]})
        # Majority is only a display convenience; conflicts remain visible.
        counts = {}
        for s,v in vals: counts[v] = counts.get(v,0)+1
        result["fields"][field] = max(vals, key=lambda x: counts[x[1]])[1]
    # Jusbrasil: public process research for the company and identified partners.
    jb_queries = []
    if c:
        jb_queries.append(("CNPJ", c))
    for partner in result.get("partners", []):
        jb_queries.append(("Sócio/administrador", partner["name"]))
    for kind, query in jb_queries:
        jb = search_jusbrasil(query)
        jb["target_type"] = kind
        result["partner_judicial"].append(jb)
    result["successful_sources"] = sum(1 for x in result["sources"] if x.get("ok"))
    result["source_count"] = len(result["sources"])
    result["confidence"] = None
    return result


def search_person(name: str) -> List[Dict[str, Any]]:
    if not name or len(name.strip()) < 5:
        return []
    out=[]
    for label, template in [
        ("Jusbrasil — processos", JUSBRASIL_SEARCH),
        ("Google — nome + processos", "https://www.google.com/search?q={q}+processos"),
        ("DuckDuckGo — nome", "https://html.duckduckgo.com/html/?q={q}"),
        ("Google — nome + empresa", "https://www.google.com/search?q={q}+empresa"),
    ]:
        row=fetch(template.format(q=quote('"'+name.strip()+'"')))
        out.append({"source":label,"url":row.get("url"),"ok":row.get("ok"),"status":row.get("status"),"snippet":" ".join(row.get("text","").split())[:4000]})
    return out
