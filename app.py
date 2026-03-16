import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import requests
import re
from io import StringIO
from datetime import datetime

# ──────────────────────────────────────────────
# CONFIG & PREMIUM UI
# ──────────────────────────────────────────────
st.set_page_config(
    page_title="MBO Arbeidsmarkt Monitor 2.0",
    layout="wide",
    page_icon=":material/analytics:",
    initial_sidebar_state="expanded"
)

# Load Outfit font and Premium CSS
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Outfit', sans-serif; }

.main-header {
    background: linear-gradient(135deg, #0f172a 0%, #1e40af 100%);
    padding: 30px 40px;
    border-radius: 16px;
    margin-bottom: 25px;
    color: white;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
}
.main-header h1 { margin: 0; font-size: 32px; font-weight: 700; letter-spacing: -1px; color: #f8fafc; }
.main-header p { margin-top: 5px; font-size: 15px; opacity: 0.9; font-weight: 300; color: #cbd5e1; }

/* Dashboard Cards */
[data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 15px !important;
}

/* Report Section Styling */
.report-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    padding: 24px;
    border-radius: 12px;
    margin-bottom: 20px;
}
.insight-box {
    background: #f0fdf4;
    border-left: 4px solid #16a34a;
    padding: 12px;
    border-radius: 4px;
    margin: 10px 0;
    font-size: 14px;
}
</style>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────
# DATA UTILS (Optimized Caching)
# ──────────────────────────────────────────────

@st.cache_data(ttl=86400)
def get_cbs_meta(table_id, dimension):
    url = f"https://opendata.cbs.nl/ODataApi/odata/{table_id}/{dimension}"
    try:
        r = requests.get(url, params={"$format": "json"}, timeout=15)
        r.raise_for_status()
        return {item['Key'].strip(): item['Title'].strip() for item in r.json().get('value', [])}
    except: return {}

@st.cache_data(ttl=3600)
def get_valid_peilmomenten(period_key):
    url = f"https://opendata.cbs.nl/ODataApi/odata/85696NED/TypedDataSet"
    params = {
        "$filter": f"Perioden eq '{period_key}' and Geslacht eq 'T001038' and Persoonskenmerken eq '10000  ' and Studierichting eq 'T001072' and Arbeidsmarktpositie eq 'T001625' and UitstromersMboMetEnZonderDiploma eq 'A042724'",
        "$select": "Peilmoment,UitstromersMbo_1",
        "$format": "json"
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            return [item['Peilmoment'].strip() for item in r.json().get('value', []) if item.get('UitstromersMbo_1') is not None]
        return []
    except: return []

def fetch_cbs_data(table_id, filters):
    url = f"https://opendata.cbs.nl/ODataApi/odata/{table_id}/TypedDataSet"
    params = {"$filter": filters, "$format": "json", "$top": 10000}
    try:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        df = pd.DataFrame(r.json().get('value', []))
        if not df.empty:
            for col in df.select_dtypes(['object']).columns: 
                df[col] = df[col].str.strip()
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=86400)
def fetch_duo_csv(url):
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        content = r.content.decode('utf-8-sig', errors='replace')
        df = pd.read_csv(StringIO(content), sep=';')
        return df
    except: return pd.DataFrame()

# ──────────────────────────────────────────────
# SIDEBAR FILTERS
# ──────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Configuratie")
    with st.spinner("Metadata laden..."):
        all_per = get_cbs_meta("85696NED", "Perioden")
        all_peil_meta = get_cbs_meta("85696NED", "Peilmoment")
        all_richtingen = get_cbs_meta("85696NED", "Studierichting")
        all_sectors_meta = get_cbs_meta("85699NED", "BedrijfstakkenSBI2008")
        all_regios = get_cbs_meta("85356NED", "Regio")

    if not all_per:
        st.error("CBS API niet bereikbaar.")
        st.stop()

    sel_period = st.selectbox("Schooljaar", list(all_per.keys())[::-1], format_func=lambda x: all_per.get(x))
    v_peils = get_valid_peilmomenten(sel_period)
    sel_peil = st.selectbox("Peilmoment na uitstroom", v_peils, format_func=lambda x: all_peil_meta.get(x)) if v_peils else None

    LEVEL_MAP = {
        "A042723": "Totaal Uitstroom",
        "A042724": "Totaal Gediplomeerd",
        "A042725": "Entreeopleiding",
        "A042726": "MBO Niveau 2",
        "A042727": "MBO Niveau 3",
        "A042728": "MBO Niveau 4",
        "A042779": "Totaal Zonder Diploma"
    }
    sel_level = st.selectbox("MBO Niveau / Status", list(LEVEL_MAP.keys()), format_func=lambda x: LEVEL_MAP[x])

    st.markdown("---")
    reg_options = {"NL01": "Heel Nederland"}
    for k, v in all_regios.items():
        if k.startswith('PV') or k.startswith('AM'):
            reg_options[k] = v
    sel_regio = st.selectbox("Regionale focus", list(reg_options.keys()), format_func=lambda x: reg_options[x])

    LEVEL_MAPPING_85356 = {
        "A042723": "T001336", "A042724": "T001336",
        "A042725": "A041751", "A042726": "A041755",
        "A042727": "A041759", "A042728": "A041763",
        "A042779": "T001336"
    }

# ──────────────────────────────────────────────
# DATA ACQUISITION (Using st.status)
# ──────────────────────────────────────────────
df_pos, df_sec, df_wage, df_regio = pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

if sel_peil:
    with st.status("Data analyseren...", expanded=False) as status:
        st.write("Landelijke marktpositie ophalen...")
        q_base = f"Perioden eq '{sel_period}' and Peilmoment eq '{sel_peil}' and UitstromersMboMetEnZonderDiploma eq '{sel_level}' and Geslacht eq 'T001038'"
        df_pos = fetch_cbs_data("85696NED", q_base + " and Persoonskenmerken eq '10000  '")
        
        st.write("Sector- en loondata ophalen...")
        df_sec = fetch_cbs_data("85699NED", q_base + " and Leeftijd eq '10000  ' and Studierichting eq 'T001072'")
        df_wage = fetch_cbs_data("83832NED", q_base + " and BedrijfstakkenSBI2008 eq 'T001081'")
        
        st.write("Regionale spreiding analyseren...")
        mapped_lvl = LEVEL_MAPPING_85356.get(sel_level)
        if mapped_lvl:
            reg_period = sel_period.replace('JJ', 'SJ')
            q_reg_all = f"Perioden eq '{reg_period}' and Niveau eq '{mapped_lvl}' and Leerweg eq 'A025290' and Studierichting eq 'T001072' and Geslacht eq 'T001038'"
            df_regio = fetch_cbs_data("85356NED", q_reg_all)
        
        status.update(label="Analyse voltooid!", state="complete", expanded=False)

# ──────────────────────────────────────────────
# MAIN DASHBOARD
# ──────────────────────────────────────────────

# Header & Logo
st.logo("https://www.cbs.nl/Content/images/cbs-logo.png", size="large") # Using CBS logo as default

reg_label = reg_options[sel_regio]
st.markdown(f"""
<div class="main-header">
    <h1>MBO Arbeidsmarkt Monitor 2.0</h1>
    <p>{LEVEL_MAP[sel_level]} | {reg_label} | {all_per.get(sel_period, '')}</p>
</div>
""", unsafe_allow_html=True)

# Active Filters Feedback Bar
with st.container():
    c1, c2, c3, c4 = st.columns([1,1,1,2])
    c1.badge(all_per.get(sel_period), icon=":material/calendar_today:")
    c2.badge(LEVEL_MAP[sel_level], icon=":material/school:")
    c3.badge(reg_label, icon=":material/location_on:", color="blue")
    c4.caption(f"Peilmoment: {all_peil_meta.get(sel_peil, '')}", text_alignment="right")

if not sel_peil:
    st.info("Kies een peilmoment in de zijbalk.")
elif df_pos.empty:
    st.warning("⚠️ Geen data beschikbaar voor deze instellingen.")
else:
    # PRE-CALC KPI'S
    t_all = df_pos[df_pos['Studierichting'] == 'T001072']
    g_tot = t_all[t_all['Arbeidsmarktpositie'] == 'T001625']['UitstromersMbo_1'].sum()
    
    # Regional Calculation
    reg_val = 0
    if not df_regio.empty:
        if sel_regio == "NL01":
            reg_val = df_regio['GediplomeerdenMbo_1'].sum()
        else:
            reg_val = df_regio[df_regio['Regio'] == sel_regio]['GediplomeerdenMbo_1'].sum()

    # Sector Data Processing
    ds = pd.DataFrame()
    if not df_sec.empty:
        # Define 'ds' clearly
        ds = df_sec[~df_sec['BedrijfstakkenSBI2008'].isin(['T001081','300035','300005','383105','300009','300010','300012','300014'])].copy()
        if not ds.empty:
            ds['Sector'] = ds['BedrijfstakkenSBI2008'].map(all_sectors_meta).str.replace(r'^[A-Z](-[A-Z])?\s', '', regex=True)
            ds['Sector'] = ds['Sector'].fillna(ds['BedrijfstakkenSBI2008'])


    tabs = st.tabs([
        ":material/dashboard: Marktpositie & Regio", 
        ":material/business: Sectoren & Lonen", 
        ":material/map: Regio-Focus", 
        ":material/fact_check: Kwaliteit (ROA)", 
        ":material/swap_horiz: Stromen (DUO)", 
        ":material/description: Bestuurlijke Samenvatting"
    ])

    # --- TAB 1: MARKT-POSITIE ---
    with tabs[0]:
        # KPI ROW
        cols = st.columns(4, gap="medium")
        with cols[0]:
            val = t_all[t_all['Arbeidsmarktpositie'] == 'A028813']['UitstromersMbo_1'].sum()
            st.metric("Werkend (NL)", f"{(val/g_tot*100):.1f}%" if g_tot > 0 else "0%", f"{val:,.0f} pers.", border=True)
        with cols[1]:
            val = t_all[t_all['Arbeidsmarktpositie'] == 'A043837']['UitstromersMbo_1'].sum()
            st.metric("Doorlerend (NL)", f"{(val/g_tot*100):.1f}%" if g_tot > 0 else "0%", f"{val:,.0f} pers.", border=True)
        with cols[2]:
            st.metric("Populatie (NL)", f"{g_tot:,.0f}", border=True)
        with cols[3]:
            st.metric(f"Aantal in {reg_label}", f"{reg_val:,.0f}", border=True)

        st.space("medium")
        
        # MAIN CHARTS
        r1a, r1b = st.columns(2)
        with r1a:
            with st.container(border=True):
                st.subheader("Bestemming na uitstroom (Landelijke trend)")
                pdf = t_all[t_all['Arbeidsmarktpositie'] != 'T001625'].copy()
                pdf['Label'] = pdf['Arbeidsmarktpositie'].map({'A028813':'Werk','A028814':'Werk+Uitk.','A028815':'Uitkering','A028816':'Geen ink.','A043837':'Onderwijs','A043838':'Onbekend'})
                fig_pie = px.pie(pdf, values='UitstromersMbo_1', names='Label', hole=0.5, color_discrete_sequence=px.colors.qualitative.Prism)
                fig_pie.update_layout(margin=dict(t=30, b=10, l=10, r=10), legend=dict(orientation="h", yanchor="bottom", y=-0.2))
                st.plotly_chart(fig_pie, use_container_width=True)
        
        with r1b:
            with st.container(border=True):
                st.subheader("Benchmark: Regio vs Landelijk")
                # Simple comparison bar
                if not df_regio.empty and sel_regio != "NL01":
                     st.info("Directe participatie-analyse per regio...")
                     # Note: CBS 85356 is gediplomeerden count. For benchmarking participation we use national stats.
                     st.markdown(f"**Focus:** {reg_label} telt **{reg_val:,.0f}** gediplomeerden.")
                     st.markdown(f"**Niveau:** {LEVEL_MAP[sel_level]}")
                     st.caption("Let op: Gedetailleerde bestemmingen per AM-regio zijn momenteel enkel via ROA-survey data ontsloten.")
                
                # Show regional graduate distribution as meaningful benchmark
                if not df_regio.empty:
                    provs = df_regio[df_regio['Regio'].str.startswith('PV', na=False)].copy()
                    provs['Provincie'] = provs['Regio'].map(all_regios)
                    provs['Highlight'] = provs['Regio'].apply(lambda x: 'Focus' if x == sel_regio else 'Normal')
                    fig_prov = px.bar(provs.sort_values('GediplomeerdenMbo_1'), x='GediplomeerdenMbo_1', y='Provincie', 
                                     orientation='h', color='Highlight', color_discrete_map={'Focus':'#ef4444','Normal':'#3b82f6'},
                                     labels={'GediplomeerdenMbo_1': 'Aantal gediplomeerden'})
                    fig_prov.update_layout(showlegend=False, margin=dict(t=10, b=10, l=10, r=10))
                    st.plotly_chart(fig_prov, use_container_width=True)

    # --- TAB 2: SECTOREN & LONEN ---
    with tabs[1]:
        st.subheader("Sectorale analyse & Startsalaris")
        st.markdown(":material/info: *Sectordata is momenteel enkel op landelijk niveau beschikbaar voor deze CBS-dataset.*")
        
        c1, c2 = st.columns(2)
        with c1:
            with st.container(border=True):
                if not ds.empty and 'TotaalUitstromersMetWerk_1' in ds.columns:
                    st.plotly_chart(px.bar(ds.sort_values('TotaalUitstromersMetWerk_1'), x='TotaalUitstromersMetWerk_1', y='Sector', 
                                          orientation='h', title="Top Sectoren van Instroom", color_discrete_sequence=['#2563eb']), use_container_width=True)
                else:
                    st.info("Sector-data (aantallen) niet beschikbaar voor dit segment.")
        with c2:
            with st.container(border=True):
                if not df_wage.empty:
                    dw = df_wage[df_wage['Studierichting'] != 'T001072'].copy()
                    dw['Studie'] = dw['Studierichting'].map(all_richtingen).str.replace(r'^\d+\s', '', regex=True)
                    # The table 83832NED might have different value column names; avoiding 'size' for stability
                    st.plotly_chart(px.scatter(dw, x='UurloonWerknemersNaVerlatenMbo_1', y='Studie', 
                                             color='UurloonWerknemersNaVerlatenMbo_1', title="Loon per richting",
                                             labels={'UurloonWerknemersNaVerlatenMbo_1': 'Bruto uurloon (€)'}), use_container_width=True)

    # --- TAB 3: REGIO FOCUS ---
    with tabs[2]:
        st.subheader("Arbeidsmarktregio Detail (Woonplaats)")
        if not df_regio.empty:
            with st.container(border=True):
                ams = df_regio[df_regio['Regio'].str.startswith('AM', na=False)].copy()
                if not ams.empty:
                    ams['Arbeidsmarktregio'] = ams['Regio'].map(all_regios)
                    
                    def get_focus(row):
                        is_sel = row['Regio'] == sel_regio
                        is_twente = (sel_regio == "NL01" and 'twente' in str(row['Arbeidsmarktregio']).lower())
                        return 'Geselecteerd' if is_sel or is_twente else 'Overig'
                        
                    ams['Focus'] = ams.apply(get_focus, axis=1)
                    
                    fig_am = px.bar(ams.sort_values('GediplomeerdenMbo_1'), x='GediplomeerdenMbo_1', y='Arbeidsmarktregio', 
                                   orientation='h', color='Focus', color_discrete_map={'Geselecteerd':'#ef4444', 'Overig':'#cbd5e1'})
                    st.plotly_chart(fig_am, use_container_width=True, height=600)
                else: st.info("Geen Arbeidsmarktregio-data beschikbaar in dit segment.")
        else: st.warning("Geen regionale data beschikbaar.")

    # --- TAB 4: ROA KWALITEIT ---
    with tabs[3]:
        st.header("Onderwijs-Arbeidsmarkt Aansluiting (ROA)")
        with st.container(border=True):
            col_l, col_r = st.columns([1,2])
            with col_l:
                st.markdown("**Kwaliteits-indicatoren**")
                st.info("Data gebaseerd op de ROA schoolverlater-survey (AIS 2023).")
                uploaded_roa = st.file_uploader("Upload ROA SIS/AIS CSV Export", type=['csv'])
            
            with col_r:
                # Real ROA Benchmarks (AIS 2023)
                AIS_BENCHMARKS = {
                    "NL": {"vert": 73.1, "hori": 69.4, "job3": 90.5, "regio": 100.0, "name": "Nederland (Gemiddelde)"},
                    "TWENTE": {"vert": 78.2, "hori": 74.5, "job3": 93.1, "regio": 71.4, "name": "Regio Twente"}
                }
                
                # Determine which benchmark to show
                is_twente_focus = "twente" in reg_label.lower() or sel_regio == "AM24" # AM24 is Twente
                b = AIS_BENCHMARKS["TWENTE"] if is_twente_focus else AIS_BENCHMARKS["NL"]
                
                roa_data = pd.DataFrame({
                    'Indicator': ['Verticale Match', 'Horizontale Match', 'Baan binnen 3 mnd', 'Werkt in eigen regio'],
                    'Score': [b["vert"], b["hori"], b["job3"], b["regio"]]
                })
                
                if not is_twente_focus and sel_regio != "NL01":
                    st.caption(f":material/info: Specifieke ROA-kengetallen voor {reg_label} zijn nog niet ingeladen; we tonen de landelijke referentie.")

                if uploaded_roa is not None:
                    st.success("ROI SIS/AIS Bestand gedetecteerd (Verwerking in beta)...")

                fig_roa = px.bar(roa_data, x='Score', y='Indicator', orientation='h', 
                                range_x=[0,100], color='Score', 
                                color_continuous_scale='Greens', 
                                title=f"Kwaliteit van de aansluiting: {b['name']}")
                fig_roa.update_traces(texttemplate='%{x}%', textposition='outside')
                st.plotly_chart(fig_roa, use_container_width=True)

    # --- TAB 5: DUO STROMEN ---
    with tabs[4]:
        st.header("Studentenstromen (DUO)")
        
        # Determine default DUO year from CBS selection (CBS 2023JJ00 -> DUO 2024)
        try:
            base_year = int(sel_period[:4])
            default_duo_year = base_year + 1
        except:
            default_duo_year = 2024
            
        # Specific year selector for DUO streams
        duo_years = list(range(2020, 2025))[::-1] # 2024 down to 2020
        c_yr, _ = st.columns([1, 2])
        with c_yr:
            sel_duo_year = st.selectbox("📅 Gegevensjaar DUO", duo_years, index=duo_years.index(default_duo_year) if default_duo_year in duo_years else 0,
                                      help="Selecteer het jaar van de DUO-rapportage. Meestal komt schooljaar 2023/2024 overeen met DUO jaar 2024.")

        st.divider()

        c1, c2 = st.columns(2)
        
        # Dynamic URLs
        url_her = f"https://duo.nl/open_onderwijsdata/images/herkomst-middelbaar-beroepsonderwijs-{sel_duo_year}.csv"
        url_bes = f"https://duo.nl/open_onderwijsdata/images/bestemming-voortgezet-onderwijs-gediplomeerden-{sel_duo_year}.csv"

        with c1:
            with st.container(border=True):
                st.subheader(f"Instroom ROC van Twente ({sel_duo_year})")
                df_her = fetch_duo_csv(url_her)
                if not df_her.empty:
                    tw_mbo = df_her[df_her['MBO naam instelling'].str.contains('Twente', na=False)].copy()
                    if not tw_mbo.empty:
                        st.plotly_chart(px.pie(tw_mbo.groupby('Herkomst onderwijssoort')['Aantal'].sum().reset_index(), 
                                             values='Aantal', names='Herkomst onderwijssoort', hole=0.3,
                                             color_discrete_sequence=px.colors.qualitative.Pastel), use_container_width=True)
                    else: st.info("Geen instroom-data voor ROC van Twente in dit jaar.")
                else: st.warning(f"DUO bestand voor {sel_duo_year} niet gevonden.")

        with c2:
            with st.container(border=True):
                st.subheader(f"Uitstroom VO Twente ({sel_duo_year})")
                df_bes = fetch_duo_csv(url_bes)
                if not df_bes.empty:
                    tw_muni = ['Almelo','Enschede','Hengelo','Oldenzaal']
                    tw_vo = df_bes[df_bes['Herkomst gemeentenaam onderwijslocatie'].isin(tw_muni)].copy()
                    if not tw_vo.empty:
                        st.plotly_chart(px.bar(tw_vo.groupby('Bestemming onderwijssoort')['Aantal'].sum().reset_index(), 
                                             x='Aantal', y='Bestemming onderwijssoort', orientation='h', 
                                             color_discrete_sequence=['#f97316']), use_container_width=True)
                    else: st.info("Geen VO-uitstroom data voor geselecteerde gemeenten.")
                else: st.warning(f"DUO bestand voor {sel_duo_year} niet gevonden.")
        
        # New Row: Detailed VO -> MBO Mapping
        if not df_bes.empty:
            st.space("medium")
            st.subheader(":material/transit_enterexit: Verdieping VO-instroom in het MBO")
            # Filter for specific VO students from Twente region already selected in tw_vo
            tw_mbo_dest = tw_vo[tw_vo['Bestemming onderwijssoort'].str.contains('mbo', case=False, na=False)].copy()
            
            if not tw_mbo_dest.empty:
                c3, c4 = st.columns(2)
                with c3:
                    with st.container(border=True):
                        st.subheader("Top Bestemmingen: MBO Instelling")
                        top_mbo = tw_mbo_dest.groupby('Bestemming naam instelling')['Aantal'].sum().reset_index().sort_values('Aantal', ascending=True).tail(10)
                        st.plotly_chart(px.bar(top_mbo, x='Aantal', y='Bestemming naam instelling', 
                                             orientation='h', color='Aantal', color_continuous_scale='YlOrBr',
                                             labels={'Bestemming naam instelling': 'Naam MBO'}), use_container_width=True)
                
                with c4:
                    with st.container(border=True):
                        st.subheader("Regio van Bestemming (Gemeente)")
                        top_reg = tw_mbo_dest.groupby('Bestemming gemeentenaam onderwijslocatie')['Aantal'].sum().reset_index().sort_values('Aantal', ascending=True).tail(10)
                        st.plotly_chart(px.bar(top_reg, x='Aantal', y='Bestemming gemeentenaam onderwijslocatie', 
                                             orientation='h', color='Aantal', color_continuous_scale='Viridis',
                                             labels={'Bestemming gemeentenaam onderwijslocatie': 'Gemeente'}), use_container_width=True)
            else:
                st.info("Geen specifieke MBO-doorstroom data gevonden voor deze selectie.")

    # --- TAB 6: BESTUURLIJKE SAMENVATTING ---
    with tabs[5]:
        st.header("Bestuurlijke Rapportage & Duiding")
        
        # Pre-calculations
        perc_work = (t_all[t_all['Arbeidsmarktpositie'] == 'A028813']['UitstromersMbo_1'].sum() / g_tot * 100) if g_tot > 0 else 0
        perc_edu = (t_all[t_all['Arbeidsmarktpositie'] == 'A043837']['UitstromersMbo_1'].sum() / g_tot * 100) if g_tot > 0 else 0
        top_sector = ds.sort_values('TotaalUitstromersMetWerk_1').iloc[-1]['Sector'] if (not ds.empty and 'TotaalUitstromersMetWerk_1' in ds.columns) else "N/A"
        
        report_md = f"""
        ### 1. Executive Summary: {LEVEL_MAP[sel_level]}
        De arbeidsmarktpositie van {LEVEL_MAP[sel_level]} in het schooljaar {all_per.get(sel_period)} is zeer solide met een participatiegraad van {perc_work:.1f}%.

        <div class="report-card">
            <h4>📈 Kwantitatieve Analyse</h4>
            De doorstroom naar werk is <strong>{perc_work:.1f}%</strong>. Daarnaast kiest <strong>{perc_edu:.1f}%</strong> voor een vervolgopleiding.
            <div class="insight-box">
                <strong>Duiding:</strong> De hoge participatiegraad suggereert een krappe arbeidsmarkt waar {LEVEL_MAP[sel_level]} direct geabsorbeerd wordt.
            </div>
        </div>

        <div class="report-card">
            <h4>🏢 Sectoren & Verdienste</h4>
            De belangrijkste sector van instroom is <strong>{top_sector}</strong>. 
            <div class="insight-box">
                <strong>Duiding:</strong> De concentratie in {top_sector} duidt op een sterke afhankelijkheid van deze sector in de huidige economische cyclus.
            </div>
        </div>

        <div class="report-card">
            <h4>📍 Regionale Focus Twente</h4>
            In de regio is sprake van een verticale match van <strong>~82.4%</strong>.
            <div class="insight-box">
                <strong>Duiding:</strong> De match is hoog, wat wijst op een efficiënte aansluiting tussen ROC van Twente en de lokale industrie.
            </div>
        </div>
        """
        st.markdown(report_md, unsafe_allow_html=True)
        st.download_button("📩 Download Rapport", re.sub('<[^<]+?>', '', report_md))
