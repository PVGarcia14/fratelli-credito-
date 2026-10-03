from __future__ import annotations
import base64
import json
import sqlite3
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

st.set_page_config(page_title="Fratelli B2B Crédito 6.0.2", page_icon=str(LOGO) if LOGO.exists() else "💳", layout="wide")


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
st.sidebar.markdown("# Fratelli 6.0.2")
menu=st.sidebar.radio("Menu", ["Nova análise","Histórico","Auditoria","Metodologia"])

c=db()

if menu=="Nova análise":
    st.title("Nova análise — 6.0.2")
    st.caption("Motor B2B genérico de análise de crédito 6.0.2 — pesquisa pública, evidências, score, limite, caixas, unidades e simulação explicável.")
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
        names=st.text_area("Nomes encontrados ou informados (um por linha)", value="")
        if st.button("Pesquisar nomes publicamente"):
            people=[]
            for n in names.splitlines():
                people.append({"name":n,"results":search_person(n)})
            st.session_state["people"]=people
        for p in st.session_state.get("people",[]):
            with st.expander(p["name"]):
                for r in p["results"]:
                    st.write(f"**{r['source']}** — {'OK' if r['ok'] else 'sem resposta'}")
                    if r.get("url"): st.write(r["url"])
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

    st.subheader("Simulador comercial — configuração genérica")
    st.caption("6.0.2: converte o limite aprovado em caixas e unidades. Produtos e descontos são configuráveis e não fazem parte do motor de risco.")

    p1, p2, p3 = st.columns(3)
    with p1:
        product_name = st.text_input("Produto", value="Produto A", key="product_602")
    with p2:
        unit_price = float(st.number_input("Preço unitário (R$)", min_value=0.0, step=1.0, key="price_602"))
    with p3:
        units_per_box = int(st.number_input("Unidades por caixa", min_value=1, value=9, step=1, key="units_box_602"))

    st.markdown("**Faixas de desconto**")
    t1, t2, t3 = st.columns(3)
    with t1:
        min1 = int(st.number_input("Faixa 1 — a partir de (unid.)", min_value=0, value=1, step=1, key="min1_602"))
        max1 = int(st.number_input("Faixa 1 — até (unid.)", min_value=0, value=18, step=1, key="max1_602"))
        pct1 = float(st.number_input("Desconto faixa 1 (%)", min_value=0.0, max_value=100.0, step=1.0, key="pct1_602"))
    with t2:
        min2 = int(st.number_input("Faixa 2 — a partir de (unid.)", min_value=0, value=19, step=1, key="min2_602"))
        max2 = int(st.number_input("Faixa 2 — até (unid.)", min_value=0, value=34, step=1, key="max2_602"))
        pct2 = float(st.number_input("Desconto faixa 2 (%)", min_value=0.0, max_value=100.0, step=1.0, key="pct2_602"))
    with t3:
        min3 = int(st.number_input("Faixa 3 — a partir de (unid.)", min_value=0, value=35, step=1, key="min3_602"))
        pct3 = float(st.number_input("Desconto faixa 3 (%)", min_value=0.0, max_value=100.0, step=1.0, key="pct3_602"))

    tiers = [
        {"min_units": min1, "max_units": max1, "discount_pct": pct1},
        {"min_units": min2, "max_units": max2, "discount_pct": pct2},
        {"min_units": min3, "max_units": None, "discount_pct": pct3},
    ]
    box_value = calculate_box_value(unit_price, units_per_box)
    max_allowed = max_boxes_by_approved_limit(dec["approved"], unit_price, units_per_box, tiers)

    st.markdown("**Limite convertido em quantidade**")
    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Limite aprovado", money(dec["approved"]))
    q2.metric("Valor da caixa", money(box_value))
    q3.metric("Máximo de caixas", f"{max_allowed['boxes']} caixas")
    q4.metric("Máximo de unidades", f"{max_allowed['units']} unidades")

    st.caption(
        f"{product_name}: {units_per_box} unidade(s) por caixa. "
        "O cálculo considera caixas inteiras e nunca ultrapassa o limite aprovado."
    )

    st.markdown("**Simular pedido por caixas**")
    requested_boxes = int(st.number_input("Quantidade de caixas solicitada", min_value=0, step=1, key="boxes_602"))
    order = simulate_order(unit_price, requested_boxes, units_per_box, tiers)
    excess = round(max(0.0, order["net"] - dec["approved"]), 2)
    accepted = excess <= 0 and dec["approved"] > 0 and requested_boxes > 0
    r1, r2, r3, r4, r5 = st.columns(5)
    r1.metric("Caixas", str(order["boxes"]))
    r2.metric("Unidades", str(order["units"]))
    r3.metric("Valor bruto", money(order["gross"]))
    r4.metric(f"Desconto ({order['discount_pct']:.1f}%)", money(order["discount"]))
    r5.metric("Valor líquido", money(order["net"]))

    if requested_boxes == 0:
        st.info("Informe a quantidade de caixas para simular o pedido.")
    elif accepted:
        st.success(f"Pedido dentro do limite aprovado: {money(order['net'])}.")
    else:
        st.warning(
            f"Pedido excede o limite aprovado em {money(excess)}. "
            f"Máximo calculado: {max_allowed['boxes']} caixa(s) / {max_allowed['units']} unidade(s)."
        )

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
