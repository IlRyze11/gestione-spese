import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
import uuid
import gspread
import os

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Finanze Pro Cloud", layout="wide", page_icon="💰")

# CSS Avanzato per Estetica e Mobile
st.markdown("""
    <style>
    /* Sfondo generale e font */
    .main { background-color: #f8f9fa; }
    
    /* Stile per le card delle metriche */
    [data-testid="stMetricValue"] { font-size: 1.6rem !important; font-weight: bold; }
    div[data-testid="metric-container"] {
        background-color: white;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        border-left: 5px solid #4e73df;
    }
    
    /* Padding per mobile */
    @media (max-width: 640px) {
        .main .block-container { padding: 1rem; }
        [data-testid="stMetricValue"] { font-size: 1.3rem !important; }
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

# --- LOGICA APP ---
df = carica_dati()
st.sidebar.title("💎 Finanze Pro")

# --- Form Inserimento ---
with st.sidebar.expander("➕ Nuova Operazione", expanded=False):
    with st.form("form_inserimento", clear_on_submit=True):
        data_i = st.date_input("Data", datetime.date.today())
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

# --- LAYOUT A SCHEDE ---
tab_dash, tab_banca, tab_dati = st.tabs(["📊 Dashboard", "🏦 La mia Banca", "📝 Gestione Dati"])

# --- CALCOLI TOTALI ---
accantonati = df[df["Tipo"] == "Accantonamento (-> Banca)"]["Importo"].sum()
prelevati = df[df["Tipo"] == "Prelievo (<- Banca)"]["Importo"].sum()
saldo_banca_totale = accantonati - prelevati

# --- TAB 1: DASHBOARD ---
with tab_dash:
    anno_sel = st.selectbox("Filtra Anno", sorted(list(set(df["Data"].dt.year.tolist() + [datetime.date.today().year])), reverse=True))
    df_anno = df[df["Data"].dt.year == anno_sel]
    
    entrate = df_anno[df_anno["Tipo"] == "Entrata"]["Importo"].sum()
    uscite = df_anno[df_anno["Tipo"] == "Uscita"]["Importo"].sum()
    
    col1, col2, col3 = st.columns(3)
    col1.metric("💰 Entrate Anno", f"€ {entrate:,.2f}")
    col2.metric("💸 Uscite Anno", f"€ {uscite:,.2f}")
    col3.metric("🏦 Saldo Banca Attuale", f"€ {saldo_banca_totale:,.2f}")

    st.subheader("Andamento Mensile")
    df_plot = df_anno[df_anno["Tipo"].isin(["Entrata", "Uscita"])]
    if not df_plot.empty:
        fig = px.bar(df_plot, x="Data", y="Importo", color="Tipo", barmode='group',
                     color_discrete_map={"Entrata": "#2ecc71", "Uscita": "#e74c3c"},
                     template="plotly_white")
        st.plotly_chart(fig, use_container_width=True)

# --- TAB 2: SEZIONE BANCA ---
with tab_banca:
    st.title("🏦 Gestione Risparmi")
    
    c1, c2 = st.columns([1, 1])
    
    with c1:
        st.subheader("Stato del Fondo")
        st.write(f"In questo momento hai messo da parte un totale di:")
        st.title(f"€ {saldo_banca_totale:,.2f}")
        
        # Breakdown per categoria banca
        df_banca = df[df["Tipo"].str.contains("Banca")]
        if not df_banca.empty:
            # Calcoliamo il netto per categoria banca
            breakdown = df_banca.groupby(["Categoria", "Tipo"])["Importo"].sum().unstack(fill_value=0)
            if "Accantonamento (-> Banca)" in breakdown.columns:
                if "Prelievo (<- Banca)" not in breakdown.columns: breakdown["Prelievo (<- Banca)"] = 0
                breakdown["Netto"] = breakdown["Accantonamento (-> Banca)"] - breakdown["Prelievo (<- Banca)"]
                
                fig_pie = px.pie(breakdown.reset_index(), values='Netto', names='Categoria', hole=.4,
                                 title="Distribuzione Risparmi", color_discrete_sequence=px.colors.qualitative.Pastel)
                st.plotly_chart(fig_pie, use_container_width=True)

    with c2:
        st.subheader("Ultime Operazioni Banca")
        df_mov_banca = df[df["Tipo"].str.contains("Banca")].head(10)
        if not df_mov_banca.empty:
            st.table(df_mov_banca[["Data", "Tipo", "Categoria", "Importo"]])
        else:
            st.info("Nessun movimento bancario registrato.")

# --- TAB 3: GESTIONE DATI ---
with tab_dati:
    st.subheader("Modifica o Elimina Record")
    df_edit = st.data_editor(df, num_rows="dynamic", hide_index=True, key="main_editor",
                            column_config={
                                "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                                "Importo": st.column_config.NumberColumn("Importo", format="€ %.2f"),
                                "Tipo": st.column_config.SelectboxColumn("Tipo", options=["Uscita", "Entrata", "Accantonamento (-> Banca)", "Prelievo (<- Banca)"])
                            })
    
    if st.button("💾 Salva Modifiche su Cloud"):
        df_edit["ID"] = df_edit["ID"].apply(lambda x: genera_id() if not x or pd.isna(x) else x)
        if salva_dati_su_cloud(df_edit):
            st.success("Sincronizzazione completata!")
            st.rerun()
