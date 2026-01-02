import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
import uuid
import gspread
import os

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Finanze Pro Cloud", layout="wide", page_icon="💰")

# CSS Migliorato per Mobile e Desktop
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    [data-testid="stMetricValue"] { font-size: 1.6rem !important; font-weight: bold; }
    div[data-testid="metric-container"] {
        background-color: white;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        border-left: 5px solid #4e73df;
    }
    @media (max-width: 640px) {
        .main .block-container { padding: 1rem; }
    }
    </style>
    """, unsafe_allow_html=True)

@st.cache_resource(ttl=60)
def connetti_google_sheet():
    if "gcp_service_account" in st.secrets:
        try:
            creds_dict = dict(st.secrets["gcp_service_account"])
            client = gspread.service_account_from_dict(creds_dict)
            return client.open("GestioneSpese").sheet1
        except Exception as e:
            st.error(f"Errore Secrets: {e}"); st.stop()
    elif os.path.exists("credentials.json"):
        try:
            client = gspread.service_account(filename="credentials.json")
            return client.open("GestioneSpese").sheet1
        except Exception as e:
            st.error(f"Errore Locale: {e}"); st.stop()
    else:
        st.error("⚠️ Credenziali mancanti!"); st.stop()

def genera_id(): return str(uuid.uuid4())[:8]

def carica_dati():
    cols = ["ID", "Data", "Tipo", "Categoria", "Importo", "Note"]
    df = pd.DataFrame(columns=cols)
    try:
        sheet = connetti_google_sheet()
        data = sheet.get_all_records()
        if data:
            df = pd.DataFrame(data)
            df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
            df["Importo"] = pd.to_numeric(df["Importo"].astype(str).str.replace(',', '.'), errors='coerce').fillna(0.0)
            df = df.dropna(subset=["Data"]).sort_values(by="Data", ascending=False)
    except: pass
    return df

def salva_dati_su_cloud(df):
    try:
        sheet = connetti_google_sheet()
        df_export = df.copy()
        df_export["Data"] = df_export["Data"].dt.strftime('%Y-%m-%d')
        sheet.clear()
        sheet.update(values=[df_export.columns.values.tolist()] + df_export.values.tolist(), range_name='A1')
        return True
    except Exception as e:
        st.error(f"Errore: {e}"); return False

# --- LOGICA DATI ---
df = carica_dati()
oggi = datetime.date.today()
nomi_mesi = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno", 
             "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]

# --- SIDEBAR ---
st.sidebar.title("💎 Finanze & Banca")

# Filtro Anno (Spostato qui)
anni_disponibili = sorted(list(set(df["Data"].dt.year.tolist() + [oggi.year])), reverse=True)
anno_selezionato = st.sidebar.selectbox("📅 Seleziona Anno", anni_disponibili)

# Form Inserimento
with st.sidebar.expander("➕ Nuova Operazione", expanded=False):
    with st.form("form_inserimento", clear_on_submit=True):
        data_i = st.date_input("Data", oggi)
        tipo_i = st.selectbox("Tipo", ["Uscita", "Entrata", "Accantonamento (-> Banca)", "Prelievo (<- Banca)"])
        
        if "Uscita" in tipo_i: cat_list = ["Cibo", "Casa", "Trasporti", "Salute", "Svago", "Shopping", "Bollette", "Altro"]
        elif "Entrata" in tipo_i: cat_list = ["Stipendio", "Bonus", "Vendite", "Rimborsi", "Investimenti", "Altro"]
        else: cat_list = ["Risparmio", "Fondo Emergenza", "Investimento", "Obbiettivo"]
            
        cat_i = st.selectbox("Categoria", cat_list)
        imp_i = st.number_input("Importo (€)", min_value=0.0, step=10.0)
        note_i = st.text_input("Note")
        
        if st.form_submit_button("Conferma"):
            nuovo = pd.DataFrame({"ID":[genera_id()], "Data":[pd.to_datetime(data_i)], "Tipo":[tipo_i], "Categoria":[cat_i], "Importo":[imp_i], "Note":[note_i]})
            df = pd.concat([df, nuovo], ignore_index=True)
            if salva_dati_su_cloud(df): st.rerun()

# --- CALCOLI TOTALI BANCA (Sempre globali) ---
accantonati = df[df["Tipo"] == "Accantonamento (-> Banca)"]["Importo"].sum()
prelevati = df[df["Tipo"] == "Prelievo (<- Banca)"]["Importo"].sum()
saldo_banca_totale = accantonati - prelevati

# --- LAYOUT A SCHEDE ---
tab_dash, tab_banca, tab_dati = st.tabs(["📊 Dashboard", "🏦 La mia Banca", "📝 Gestione Dati"])

# --- TAB 1: DASHBOARD ---
with tab_dash:
    st.subheader(f"Analisi Periodo {anno_selezionato}")
    
    # Filtro Mese (Nuovo, Default Mese Corrente)
    mese_selezionato_nome = st.selectbox("📆 Seleziona Mese", nomi_mesi, index=oggi.month - 1)
    mese_selezionato_num = nomi_mesi.index(mese_selezionato_nome) + 1
    
    # Filtraggio dati per Anno e Mese
    df_filtrato = df[(df["Data"].dt.year == anno_selezionato) & (df["Data"].dt.month == mese_selezionato_num)]
    
    entrate = df_filtrato[df_filtrato["Tipo"] == "Entrata"]["Importo"].sum()
    uscite = df_filtrato[df_filtrato["Tipo"] == "Uscita"]["Importo"].sum()
    differenza = entrate - uscite

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("💰 Entrate Mese", f"€ {entrate:,.2f}")
    col2.metric("💸 Uscite Mese", f"€ {uscite:,.2f}")
    col3.metric("⚖️ Cashflow", f"€ {differenza:,.2f}", delta=differenza)
    col4.metric("🏦 Saldo Banca", f"€ {saldo_banca_totale:,.2f}")

    st.divider()
    st.subheader(f"📈 Andamento Giornaliero: {mese_selezionato_nome}")
    
    df_plot = df_filtrato[df_filtrato["Tipo"].isin(["Entrata", "Uscita"])]
    if not df_plot.empty:
        fig = px.bar(df_plot, x="Data", y="Importo", color="Tipo", barmode='group',
                     color_discrete_map={"Entrata": "#2ecc71", "Uscita": "#e74c3c"},
                     template="plotly_white", text_auto='.2f')
        fig.update_xaxes(dtick="D1", tickformat="%d") # Mostra ogni giorno sul grafico
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info(f"Nessun dato di spesa/entrata per {mese_selezionato_nome} {anno_selezionato}")

# --- TAB 2: SEZIONE BANCA ---
with tab_banca:
    st.title("🏦 Gestione Risparmi & Banca")
    c1, c2 = st.columns([1, 1])
    with c1:
        st.metric("Disponibilità Totale in Banca", f"€ {saldo_banca_totale:,.2f}")
        df_banca = df[df["Tipo"].str.contains("Banca")]
        if not df_banca.empty:
            breakdown = df_banca.groupby(["Categoria", "Tipo"])["Importo"].sum().unstack(fill_value=0)
            if "Accantonamento (-> Banca)" in breakdown.columns:
                if "Prelievo (<- Banca)" not in breakdown.columns: breakdown["Prelievo (<- Banca)"] = 0
                breakdown["Netto"] = breakdown["Accantonamento (-> Banca)"] - breakdown["Prelievo (<- Banca)"]
                fig_pie = px.pie(breakdown.reset_index(), values='Netto', names='Categoria', hole=.4,
                                 title="Distribuzione Risparmi", color_discrete_sequence=px.colors.qualitative.Safe)
                st.plotly_chart(fig_pie, use_container_width=True)
    with c2:
        st.subheader("Storico Movimenti Banca")
        st.dataframe(df_banca[["Data", "Tipo", "Categoria", "Importo", "Note"]].head(15), use_container_width=True)

# --- TAB 3: GESTIONE DATI ---
with tab_dati:
    st.subheader("Database Completo")
    df_edit = st.data_editor(df, num_rows="dynamic", hide_index=True, key="main_editor",
                            column_config={
                                "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                                "Importo": st.column_config.NumberColumn("Importo", format="€ %.2f"),
                                "Tipo": st.column_config.SelectboxColumn("Tipo", options=["Uscita", "Entrata", "Accantonamento (-> Banca)", "Prelievo (<- Banca)"])
                            })
    if st.button("💾 Salva e Sincronizza Cloud"):
        df_edit["ID"] = df_edit["ID"].apply(lambda x: genera_id() if not x or pd.isna(x) else x)
        if salva_dati_su_cloud(df_edit):
            st.success("Dati sincronizzati!"); st.rerun()
