from __future__ import annotations
import base64
import json
import sqlite3
import random
from datetime import datetime
from pathlib import Path
import pandas as pd
import streamlit as st
from engine import (
    WEIGHTS, clean_cnpj, validate_cnpj, score_from_evidence, risk_band, decision,
    public_confidence, calculate_box_value, discount_for_quantity,
    simulate_order, max_boxes_by_approved_limit
)
from public_research import research_company, search_person

APP_DIR=Path(__file__).parent
DB=APP_DIR/"fratelli.db"
LOGO=APP_DIR/"assets"/"fratelli_logo.png"

# 6.0.6 — configuração comercial genérica.
# Altere SOMENTE estes valores para cadastrar seus produtos no seu ambiente.
PRODUCT_CONFIG = [
    {"name": "Produto A", "unit_price": 0.0, "units_per_box": 9},
    {"name": "Produto B", "unit_price": 0.0, "units_per_box": 9},
    {"name": "Produto C", "unit_price": 0.0, "units_per_box": 9},
]
COMMERCIAL_TIERS = [
    {"label": "Condição 1", "min_units": 1, "max_units": 18, "discount_pct": 0.0},
    {"label": "Condição 2", "min_units": 19, "max_units": 34, "discount_pct": 0.0},
    {"label": "Condição 3", "min_units": 35, "max_units": None, "discount_pct": 0.0},
]

st.set_page_config(page_title="Fratelli B2B Crédito 6.0.7", page_icon=str(LOGO) if LOGO.exists() else "💳", layout="wide")


def money(v):
    return f"R$ {float(v or 0):,.2f}".replace(",","X").replace(".",",").replace("X",".")


def db():
    c=sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS analyses(
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, cnpj TEXT, company TEXT,
        score REAL, confidence REAL, coverage REAL, requested REAL, approved REAL,
        decision TEXT, data_json TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS audit(
        id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT, action TEXT, cnpj TEXT, details TEXT)""")
    c.commit(); return c


def audit(c, action, cnpj, details):
    c.execute("INSERT INTO audit(created_at,action,cnpj,details) VALUES(?,?,?,?)", (datetime.now().isoformat(timespec="seconds"),action,cnpj,json.dumps(details,ensure_ascii=False)))
    c.commit()


def logo_html():
    if not LOGO.exists(): return ""
    b=base64.b64encode(LOGO.read_bytes()).decode()
    return f'<img src="data:image/png;base64,{b}" style="width:180px;max-height:90px;object-fit:contain;display:block;margin:0 auto 18px;">'

st.markdown("""
<style>
.block-container{padding-top:1.4rem}
.decision{padding:22px;border-radius:14px;border:1px solid rgba(0,0,0,.08);margin-bottom:18px}
.decision h2{margin:0 0 8px 0}
.small{color:#737780;font-size:.9rem}
</style>
""", unsafe_allow_html=True)
st.sidebar.markdown(logo_html(), unsafe_allow_html=True)
st.sidebar.markdown("# Fratelli 6.0.7")
menu=st.sidebar.radio("Menu", ["Nova análise","Histórico","Auditoria","Metodologia"])

c=db()

if menu=="Nova análise":
    st.title("Nova análise — 6.0.7")
    st.caption("Motor B2B genérico de análise de crédito 6.0.7 — pesquisa pública, evidências, score, limite, caixas, unidades, composição automática e simulação explicável.")
    cnpj=st.text_input("CNPJ", placeholder="00.000.000/0000-00")
    col1,col2=st.columns([1,1])
    with col1:
        if st.button("Analisar empresa", type="primary", use_container_width=True):
            ok,msg=validate_cnpj(cnpj)
            if not ok: st.error(msg)
            else:
                with st.spinner("Pesquisando fontes públicas disponíveis..."):
                    d=research_company(cnpj)
                st.session_state["dossier"]=d
                st.session_state["cnpj"]=clean_cnpj(cnpj)
                audit(c,"PESQUISA_PUBLICA",clean_cnpj(cnpj),{"sources":d.get("source_count",0),"successful":d.get("successful_sources",0),"conflicts":len(d.get("conflicts",[]))})
    with col2:
        st.info("A pesquisa pública não acessa bases privadas, não contorna autenticação e não transforma ausência de resultado em ausência de dívida/processo.")

    d=st.session_state.get("dossier")
    if d:
        fields=d.get("fields",{})
        st.subheader("Resumo da empresa")
        if fields:
            st.dataframe(pd.DataFrame([{"Campo":k,"Valor":v,"Fonte(s)":"; ".join(s for s,_ in d.get("field_sources",{}).get(k,[]))} for k,v in fields.items()]), use_container_width=True, hide_index=True)
        else:
            st.warning("Nenhum dado cadastral foi extraído automaticamente das fontes que responderam.")
        if d.get("conflicts"):
            st.error(f"⚠️ {len(d['conflicts'])} divergência(s) entre fontes")
            for x in d["conflicts"]:
                st.markdown(f"**{x['field']}**")
                st.dataframe(pd.DataFrame(x["values"]), use_container_width=True, hide_index=True)
        ok_sources=d.get("successful_sources",0); total_sources=d.get("source_count",0)
        conf=public_confidence(total_sources,ok_sources,len(d.get("conflicts",[])),len(fields))
        d["confidence"]=conf
        st.metric("Confiança da pesquisa pública", f"{conf*100:.0f}%")

        st.subheader("Sócios / administradores")
        partners = d.get("partners", [])
        if partners:
            st.success(f"{len(partners)} sócio(s)/administrador(es) identificado(s) nas fontes públicas.")
            st.dataframe(
                pd.DataFrame([
                    {
                        "Nome": p.get("name"),
                        "Qualificação": p.get("role", "Não identificada"),
                        "Fonte(s)": "; ".join(d.get("partner_sources", {}).get(p.get("name"), [])),
                    }
                    for p in partners
                ]),
                use_container_width=True, hide_index=True
            )
        else:
            st.warning("Nenhum sócio/administrador foi extraído automaticamente das fontes que responderam. Isso não significa ausência de sócios; significa apenas que o QSA não foi localizado/extraído nesta pesquisa.")

        st.subheader("Pesquisa judicial — Jusbrasil")
        st.caption("A pesquisa usa o CNPJ e os nomes identificados no QSA. O resultado é apresentado como evidência pública, sem concluir que uma ocorrência seja prejudicial sem analisar o processo, partes, assunto, situação e decisões.")
        judicial = d.get("partner_judicial", [])
        if judicial:
            for r in judicial:
                target = f"{r.get('target_type')}: {r.get('query')}"
                with st.expander(target, expanded=True):
                    if r.get("available_publicly"):
                        st.write(f"**Jusbrasil:** acesso público respondeu (HTTP {r.get('status')}).")
                        if r.get("snippet"):
                            st.caption(r["snippet"][:2500])
                    else:
                        st.warning(r.get("note", "Fonte não disponível publicamente neste acesso."))
                    if r.get("url"):
                        st.markdown(f"[Abrir consulta no Jusbrasil]({r['url']})")
        else:
            st.info("Nenhuma consulta judicial foi gerada porque o QSA não foi identificado ou a análise ainda não foi executada.")

        st.divider()
        st.subheader("Pesquisa manual adicional de sócios / administradores")
        names=st.text_area("Nome(s) adicional(is), um por linha", value="")
        if st.button("Pesquisar nomes publicamente"):
            people=[]
            for n in names.splitlines():
                people.append({"name":n,"results":search_person(n)})
            st.session_state["people"]=people
        for p in st.session_state.get("people",[]):
            with st.expander(p["name"]):
                for r in p["results"]:
                    st.write(f"**{r['source']}** — {'OK' if r['ok'] else 'sem resposta'}")
                    if r.get("url"): st.markdown(f"[Abrir fonte]({r['url']})")
                    if r.get("snippet"): st.caption(r["snippet"][:1000])
                st.caption("Resultados por nome são pistas públicas e exigem confirmação de identidade antes de atribuir qualquer ocorrência à pessoa.")

    st.subheader("Dados internos e solicitação")
    a,b,c1,c2=st.columns(4)
    with a: monthly=float(st.number_input("Faturamento mensal comprovado (R$)",min_value=0.0,step=1000.0))
    with b: exposure=float(st.number_input("Exposição atual em aberto (R$)",min_value=0.0,step=500.0))
    with c1: requested=float(st.number_input("Valor solicitado pelo cliente (R$)",min_value=0.0,step=500.0))
    with c2: current_limit=float(st.number_input("Limite atual informado (R$)",min_value=0.0,step=500.0))
    st.caption("O limite atual é informativo; não é somado à exposição. A exposição em aberto é o que reduz o limite disponível.")
    source=st.selectbox("Fonte do faturamento", ["Não informado","Documento financeiro","Fonte financeira autorizada","Declaração do cliente"])
    active_restriction=st.checkbox("Existe restrição crítica confirmada em fonte/documento?", value=False)
    years=st.number_input("Anos de atividade confirmados", min_value=0.0,step=1.0)
    status=st.selectbox("Situação cadastral confirmada", ["Não informado","ATIVA/REGULAR","SUSPENSA/INAPTA","BAIXADA/OUTRA"])
    docs=st.checkbox("Dados cadastrais/documentação conferidos", value=False)

    st.subheader("Composição do score")
    st.caption("Cada critério sem evidência recebe somente 25% da pontuação máxima. Não há renormalização para favorecer análises com poucos dados.")
    items={}
    items["Cadastro e estabilidade"]=95 if status=="ATIVA/REGULAR" and years>=5 else 75 if status=="ATIVA/REGULAR" and years>=2 else 45 if status=="ATIVA/REGULAR" else None
    items["Estrutura empresarial"]=85 if docs else None
    items["Histórico público"]=20 if active_restriction else (75 if d and d.get("successful_sources",0)>=2 and not d.get("conflicts") else None)
    if monthly>0:
        items["Capacidade empresarial"]=90 if source in ("Documento financeiro","Fonte financeira autorizada") else 60 if source=="Declaração do cliente" else None
    else: items["Capacidade empresarial"]=None
    items["Confiabilidade das informações"]=(d.get("confidence",0)*100 if d else None)
    items["Histórico comercial identificado"]=None
    score,coverage,missing=score_from_evidence(items)
    risk=risk_band(score)
    financial_available=max(0.0, monthly*0.05-exposure) if monthly>0 else 0.0
    dec=decision(score,requested,financial_available,coverage,active_restriction)

    st.subheader("DECISÃO DE CRÉDITO")
    if dec["status"]=="APROVAR": cls="success"
    elif dec["status"]=="APROVAR COM LIMITE": cls="warning"
    elif dec["status"]=="REVISÃO MANUAL": cls="warning"
    else: cls="error"
    getattr(st,cls)(f"### {dec['status']}\n\n**Score:** {score}/100 · **Risco:** {risk} · **Cobertura:** {coverage}%\n\n**Limite pela política:** {money(dec['ceiling'])}\n\n**Limite financeiro disponível:** {money(financial_available)}\n\n**Solicitação:** {money(requested)}\n\n**Valor aprovado:** {money(dec['approved'])}\n\n**Motivo:** {dec['reason']}")
    if missing:
        st.warning("Dados sem evidência — contribuição limitada a 25%: " + ", ".join(missing))
    if requested>dec["approved"]:
        st.write(f"**Excedente não aprovado:** {money(requested-dec['approved'])}")

    st.subheader("Simulação financeira do pedido")
    sim=float(st.number_input("Valor a simular (R$)",min_value=0.0,value=float(requested),step=500.0,key="sim"))
    simdec=decision(score,sim,financial_available,coverage,active_restriction)
    s1,s2,s3=st.columns(3)
    s1.metric("Pedido simulado",money(sim)); s2.metric("Aprovável",money(simdec["approved"])); s3.metric("Excesso",money(max(0,sim-simdec["approved"])))
    st.write(f"**Resultado:** {simdec['status']} — {simdec['reason']}")

    # 6.0.5 — status comercial explícito e solicitação de aprovação manual.
    # Os contatos são configuráveis no código e os links somente preenchem
    # email/WhatsApp; nenhum envio é realizado automaticamente.
    APPROVER_NAME = "Paulo Garcia"
    APPROVER_EMAIL = "teixeira1218@gmail.com"
    APPROVER_WA = "5585985552343"

    if sim > 0 and simdec["approved"] >= sim and simdec["status"] in ("APROVAR", "APROVAR COM LIMITE"):
        st.success(f"### CRÉDITO APROVADO\n\nPedido de {money(sim)} está dentro do valor aprovado pela análise.")
    else:
        st.error("### CRÉDITO NÃO APROVADO AUTOMATICAMENTE\n\nEste pedido precisa de aprovação manual antes de ser liberado.")
        reason = simdec.get("reason", "Pedido fora dos parâmetros automáticos")
        excess_manual = max(0.0, sim - float(simdec.get("approved", 0) or 0))
        company_name = fields.get("Razão social", "Empresa não identificada") if d else "Empresa não identificada"
        cnpj_value = st.session_state.get("cnpj", clean_cnpj(cnpj))
        email_subject = f"Solicitação de aprovação de crédito — {company_name} — {cnpj_value}"
        email_body = (
            f"Olá {APPROVER_NAME},\n\n"
            f"Solicito aprovação manual de crédito para a empresa {company_name} (CNPJ {cnpj_value}).\n\n"
            f"Score: {score:.1f}/100\n"
            f"Risco: {risk}\n"
            f"Cobertura: {coverage:.1f}%\n"
            f"Limite pela política: {money(dec['ceiling'])}\n"
            f"Valor aprovado automaticamente: {money(simdec.get('approved', 0))}\n"
            f"Valor solicitado: {money(sim)}\n"
            f"Excesso: {money(excess_manual)}\n"
            f"Resultado: {simdec['status']}\n"
            f"Motivo: {reason}\n\n"
            "Favor analisar e informar a decisão manual.\n"
        )
        import urllib.parse
        email_url = "mailto:" + APPROVER_EMAIL + "?" + urllib.parse.urlencode({"subject": email_subject, "body": email_body})
        wa_text = (
            f"Solicitação de aprovação de crédito\n"
            f"Empresa: {company_name}\n"
            f"CNPJ: {cnpj_value}\n"
            f"Score: {score:.1f}/100\n"
            f"Limite pela política: {money(dec['ceiling'])}\n"
            f"Aprovado automaticamente: {money(simdec.get('approved', 0))}\n"
            f"Solicitado: {money(sim)}\n"
            f"Excesso: {money(excess_manual)}\n"
            f"Motivo: {reason}\n\n"
            "Favor analisar e autorizar ou recusar o crédito."
        )
        wa_url = "https://wa.me/" + APPROVER_WA + "?" + urllib.parse.urlencode({"text": wa_text})
        b1, b2 = st.columns(2)
        with b1:
            st.link_button(f"✉️ Solicitar aprovação por e-mail — {APPROVER_NAME}", email_url, use_container_width=True)
        with b2:
            st.link_button(f"💬 Solicitar aprovação via WhatsApp — {APPROVER_NAME}", wa_url, use_container_width=True)
        st.caption("Os botões abrem uma mensagem pré-preenchida. O envio depende da confirmação do usuário no aplicativo de e-mail/WhatsApp.")
        if st.button("Registrar solicitação de aprovação manual", key="register_manual_approval", use_container_width=True):
            audit(c, "SOLICITACAO_APROVACAO_MANUAL", cnpj_value, {
                "approver": APPROVER_NAME, "email": APPROVER_EMAIL, "whatsapp": APPROVER_WA,
                "score": score, "coverage": coverage, "policy_ceiling": dec["ceiling"],
                "approved_automatically": simdec.get("approved", 0), "requested": sim,
                "excess": excess_manual, "reason": reason
            })
            st.success("Solicitação de aprovação manual registrada na auditoria.")

    st.subheader("Simulador comercial — configuração genérica")
    st.caption("6.0.6: sugere automaticamente uma composição de produtos dentro do crédito efetivamente aprovado. A composição é apenas uma sugestão operacional; nunca ultrapassa o limite liberado.")

    st.markdown("**Produtos cadastrados**")
    pc1, pc2, pc3 = st.columns(3)
    edited_products = []
    for col, cfg, idx in zip((pc1, pc2, pc3), PRODUCT_CONFIG, range(3)):
        with col:
            name = st.text_input(f"Produto {chr(65+idx)}", value=cfg["name"], key=f"prod_name_606_{idx}")
            price = float(st.number_input("Preço unitário (R$)", min_value=0.0, value=float(cfg["unit_price"]), step=1.0, key=f"prod_price_606_{idx}"))
            units_box = int(st.number_input("Unidades por caixa", min_value=1, value=int(cfg["units_per_box"]), step=1, key=f"prod_box_606_{idx}"))
            edited_products.append({"name": name, "unit_price": price, "units_per_box": units_box})

    st.markdown("**Condição comercial — selecione somente uma**")
    tier_labels = [t["label"] for t in COMMERCIAL_TIERS]
    selected_label = st.selectbox("Condição", tier_labels, index=0, key="tier_selected_606")
    selected_tier = next(t for t in COMMERCIAL_TIERS if t["label"] == selected_label)
    tc1, tc2, tc3 = st.columns(3)
    with tc1:
        tier_min = int(st.number_input("A partir de (unid.)", min_value=0, value=int(selected_tier["min_units"]), step=1, key="tier_min_606"))
    with tc2:
        max_default = int(selected_tier["max_units"] or 999999)
        tier_max = int(st.number_input("Até (unid.) — 0 = sem limite", min_value=0, value=(0 if selected_tier["max_units"] is None else max_default), step=1, key="tier_max_606"))
    with tc3:
        tier_discount = float(st.number_input("Desconto (%)", min_value=0.0, max_value=100.0, value=float(selected_tier["discount_pct"]), step=1.0, key="tier_discount_606"))
    active_tier = [{"min_units": tier_min, "max_units": (None if tier_max == 0 else tier_max), "discount_pct": tier_discount}]

    # O teto abaixo é apenas informativo; a sugestão usa exclusivamente o valor efetivamente aprovado.
    approved_limit = max(0.0, float(dec.get("approved", 0) or 0))
    policy_limit = max(0.0, float(dec.get("ceiling", 0) or 0))

    st.markdown("**Limite convertido em quantidade**")
    q1, q2, q3 = st.columns(3)
    q1.metric("Crédito efetivamente liberado", money(approved_limit))
    q2.metric("Teto pela política", money(policy_limit))
    q3.metric("Produtos disponíveis", str(sum(1 for x in edited_products if x["unit_price"] > 0)))

    def suggest_mix(products, limit, tier, seed=None):
        """Gera uma composição aleatória, porém sempre limitada ao crédito aprovado."""
        valid = [x for x in products if x["unit_price"] > 0 and x["units_per_box"] > 0]
        if limit <= 0 or not valid:
            return []
        rng = random.Random(seed)
        rng.shuffle(valid)
        # Tenta 1, 2 ou 3 produtos, priorizando diversidade sem ultrapassar o limite.
        count = rng.randint(1, min(3, len(valid)))
        chosen = valid[:count]
        boxes = {x["name"]: 0 for x in chosen}
        # Primeiro distribui uma caixa para cada produto quando couber.
        for x in chosen:
            sim = simulate_order(x["unit_price"], 1, x["units_per_box"], tier)
            if sim["net"] <= limit - sum(simulate_order(y["unit_price"], boxes[y["name"]], y["units_per_box"], tier)["net"] for y in chosen):
                boxes[x["name"]] = 1
        # Depois preenche aleatoriamente até não caber mais uma caixa.
        changed = True
        while changed:
            changed = False
            order = list(chosen)
            rng.shuffle(order)
            for x in order:
                current = boxes[x["name"]]
                trial = dict(boxes); trial[x["name"]] = current + 1
                total = 0.0
                for y in chosen:
                    total += simulate_order(y["unit_price"], trial[y["name"]], y["units_per_box"], tier)["net"]
                if total <= limit + 1e-9:
                    boxes = trial
                    changed = True
        result=[]; total=0.0
        for x in chosen:
            b=boxes[x["name"]]
            if b:
                sim=simulate_order(x["unit_price"], b, x["units_per_box"], tier)
                total += sim["net"]
                result.append({**x, **sim})
        return result

    if "mix_seed_606" not in st.session_state:
        st.session_state["mix_seed_606"] = random.randrange(1, 10**9)
    if st.button("🎲 Gerar sugestão automática", type="primary", use_container_width=True, key="generate_mix_606"):
        st.session_state["mix_seed_606"] = random.randrange(1, 10**9)

    mix = suggest_mix(edited_products, approved_limit, active_tier, st.session_state["mix_seed_606"])
    if approved_limit <= 0:
        st.warning("Não há crédito efetivamente liberado para gerar uma composição. O teto pela política não é tratado como autorização.")
    elif not mix:
        st.warning("Não foi possível gerar uma composição com os produtos/preços configurados dentro do crédito liberado.")
    else:
        rows=[]; total=0.0
        for x in mix:
            total += x["net"]
            rows.append({"Produto":x["name"], "Caixas":x["boxes"], "Unidades":x["units"], "Valor bruto":money(x["gross"]), "Desconto":money(x["discount"]), "Valor líquido":money(x["net"])})
        st.markdown("### Sugestão de composição")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.success(f"Total sugerido: {money(total)} · Saldo do crédito: {money(max(0, approved_limit-total))}")
        st.caption("A composição é recalculada ao solicitar nova sugestão e nunca ultrapassa o crédito efetivamente liberado.")

    st.markdown("**Simulação manual por caixas**")
    st.caption("O cálculo é feito imediatamente a partir do produto, preço, unidades por caixa, condição selecionada e quantidade de caixas. O cálculo do pedido funciona mesmo quando o crédito aprovado é R$ 0; nesse caso, a comparação apenas informa que o pedido não está autorizado.")
    product_options = [x["name"] for x in edited_products]
    selected_product = st.selectbox("Produto", product_options, key="manual_product_607")
    selected_cfg = next(x for x in edited_products if x["name"] == selected_product)
    mc1, mc2, mc3 = st.columns(3)
    with mc1:
        requested_boxes = int(st.number_input("Quantidade de caixas", min_value=0, value=1, step=1, key="boxes_607"))
    with mc2:
        st.metric("Preço unitário", money(selected_cfg["unit_price"]))
    with mc3:
        st.metric("Valor de 1 caixa", money(calculate_box_value(selected_cfg["unit_price"], selected_cfg["units_per_box"])))

    order = simulate_order(selected_cfg["unit_price"], requested_boxes, selected_cfg["units_per_box"], active_tier)
    excess = round(max(0.0, order["net"] - approved_limit), 2)
    accepted = requested_boxes > 0 and approved_limit > 0 and order["net"] <= approved_limit + 1e-9
    r1, r2, r3, r4, r5 = st.columns(5)
    r1.metric("Caixas", str(order["boxes"]))
    r2.metric("Unidades", str(order["units"]))
    r3.metric("Valor bruto", money(order["gross"]))
    r4.metric(f"Desconto ({order['discount_pct']:.1f}%)", money(order["discount"]))
    r5.metric("Valor líquido", money(order["net"]))

    if requested_boxes == 0:
        st.info("Informe pelo menos 1 caixa para simular o pedido.")
    elif selected_cfg["unit_price"] <= 0:
        st.error("Configure um preço unitário maior que R$ 0,00 para este produto.")
    elif accepted:
        st.success(f"Pedido dentro do crédito efetivamente liberado: {money(order['net'])}. Saldo: {money(approved_limit - order['net'])}.")
    elif approved_limit <= 0:
        st.error(f"Pedido calculado: {money(order['net'])}. Não há crédito efetivamente liberado para autorizar este pedido.")
    else:
        st.warning(f"Pedido calculado: {money(order['net'])}. Excede o crédito efetivamente liberado em {money(excess)}.")
    st.subheader("Fontes consultadas")
    if d:
        rows=[]
        for x in d.get("sources",[]):
            rows.append({"Fonte":x.get("source"),"Tipo":x.get("kind"),"Status":"OK" if x.get("ok") else "Sem resposta","URL":x.get("url"),"Horário":x.get("started")})
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
        st.info("Quando uma fonte privada/paga ou protegida não está disponível publicamente, o sistema informa a indisponibilidade; ele não inventa o resultado.")
    else:
        st.info("Execute a análise da empresa para preencher as fontes.")

    if st.button("Salvar análise"):
        payload={"fields":d.get("fields",{}) if d else {},"conflicts":d.get("conflicts",[]) if d else [],"items":items,"missing":missing}
        c.execute("INSERT INTO analyses(created_at,cnpj,company,score,confidence,coverage,requested,approved,decision,data_json) VALUES(?,?,?,?,?,?,?,?,?,?)",(datetime.now().isoformat(timespec="seconds"),st.session_state.get("cnpj",clean_cnpj(cnpj)),fields.get("Razão social","") if d else "",score,d.get("confidence",0) if d else 0,coverage,requested,dec["approved"],dec["status"],json.dumps(payload,ensure_ascii=False)))
        c.commit(); audit(c,"SALVAR_ANALISE",st.session_state.get("cnpj",clean_cnpj(cnpj)),payload); st.success("Análise salva.")

elif menu=="Histórico":
    st.title("Histórico")
    df=pd.read_sql_query("SELECT id,created_at,cnpj,company,score,confidence,coverage,requested,approved,decision FROM analyses ORDER BY id DESC",c)
    if df.empty: st.info("Nenhuma análise salva.")
    else: st.dataframe(df,use_container_width=True,hide_index=True)

elif menu=="Auditoria":
    st.title("Auditoria")
    df=pd.read_sql_query("SELECT * FROM audit ORDER BY id DESC",c)
    st.dataframe(df,use_container_width=True,hide_index=True) if not df.empty else st.info("Nenhum evento registrado.")

else:
    st.title("Metodologia")
    st.markdown("### Regras centrais")
    st.write("Sem informação suficiente = 25% da pontuação máxima do critério.")
    st.write("Score <25 = recusar; 25–<35 = teto R$1.500; 35–<45 = R$5.000; 45–<55 = R$10.000; 55–70 = R$20.000; >70 = analisar o pedido solicitado.")
    st.write("Cobertura, confiança e score são métricas diferentes. Divergências e bloqueios críticos são controles, não bônus/penalidades arbitrárias.")
    st.write("Ausência de resultado público nunca é tratada como ausência do fato.")
    st.write("Toda evidência externa deve conservar fonte e horário da consulta.")
