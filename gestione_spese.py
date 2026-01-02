import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
import uuid
import gspread
import os

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Gestore Finanze Cloud", layout="wide", page_icon="☁️")

# CSS per migliorare la visualizzazione su Mobile
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.8rem; }
    @media (max-width: 640px) {
        .main .block-container { padding: 1rem; }
    }
    </style>
    """, unsafe_allow_html=True) # <--- Sostituito con unsafe_allow_html

@st.cache_resource(ttl=60)
def connetti_google_sheet():
    if "gcp_service_account" in st.secrets:
        try:
            creds_dict = dict(st.secrets["gcp_service_account"])
            client = gspread.service_account_from_dict(creds_dict)
            return client.open("GestioneSpese").sheet1
        except Exception as e:
            st.error(f"Errore Secrets: {e}")
            st.stop()
    elif os.path.exists("credentials.json"):
        try:
            client = gspread.service_account(filename="credentials.json")
            return client.open("GestioneSpese").sheet1
        except Exception as e:
            st.error(f"Errore Locale: {e}")
            st.stop()
    else:
        st.error("⚠️ Nessuna credenziale trovata!")
        st.stop()

def genera_id():
    return str(uuid.uuid4())[:8]

def carica_dati():
    cols = ["ID", "Data", "Tipo", "Categoria", "Importo", "Note"]
    df = pd.DataFrame(columns=cols)
    try:
        sheet = connetti_google_sheet()
        data = sheet.get_all_records()
        if data:
            df = pd.DataFrame(data)
            if "Data" in df.columns:
                df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
                df = df.dropna(subset=["Data"])
            if "Importo" in df.columns:
                df["Importo"] = df["Importo"].astype(str).str.replace(',', '.', regex=False)
                df["Importo"] = pd.to_numeric(df["Importo"], errors='coerce').fillna(0.0)
            df = df.sort_values(by="Data", ascending=False)
    except Exception as e:
        st.warning(f"Dati non ancora presenti o errore: {e}")
    return df

def salva_dati_su_cloud(df):
    try:
        sheet = connetti_google_sheet()
        df_export = df.copy()
        df_export["Data"] = df_export["Data"].dt.strftime('%Y-%m-%d')
        dati_completi = [df_export.columns.values.tolist()] + df_export.values.tolist()
        sheet.clear()
        sheet.update(values=dati_completi, range_name='A1') 
        return True
    except Exception as e:
        st.error(f"Errore salvataggio Cloud: {e}")
        return False

# --- 3. LOGICA APP ---
df = carica_dati()

st.sidebar.title("☁️ Finanze & Banca")

# --- Form Inserimento ---
with st.sidebar.expander("➕ Operazione", expanded=True):
    with st.form("form_inserimento", clear_on_submit=True):
        data_input = st.date_input("Data", datetime.date.today())
        # Aggiunti tipi "Accantonamento" e "Prelievo"
        tipo_input = st.selectbox("Tipo", ["Uscita", "Entrata", "Accantonamento (-> Banca)", "Prelievo (<- Banca)"])
        
        if "Uscita" in tipo_input:
            cat_list = ["Cibo", "Casa", "Trasporti", "Salute", "Svago", "Shopping", "Bollette", "Altro"]
        elif "Entrata" in tipo_input:
            cat_list = ["Stipendio", "Bonus", "Vendite", "Rimborsi", "Investimenti", "Altro"]
        else:
            cat_list = ["Risparmio", "Fondo Emergenza", "Obiettivo"] # Categorie per Banca
            
        categoria_input = st.selectbox("Categoria", cat_list)
        importo_input = st.number_input("Importo (€)", min_value=0.0, format="%.2f", step=10.0)
        note_input = st.text_input("Note")
        
        if st.form_submit_button("💾 Registra"):
            nuovo_record = pd.DataFrame({
                "ID": [genera_id()],
                "Data": [pd.to_datetime(data_input)],
                "Tipo": [tipo_input],
                "Categoria": [categoria_input],
                "Importo": [float(importo_input)],
                "Note": [note_input]
            })
            df = pd.concat([df, nuovo_record], ignore_index=True)
            if salva_dati_su_cloud(df):
                st.success("Registrato!")
                st.rerun()

# --- DASHBOARD ---
anno_corrente = datetime.date.today().year
anni_disponibili = sorted(list(set(df["Data"].dt.year.tolist() + [anno_corrente])), reverse=True) if not df.empty else [anno_corrente]
anno_selezionato = st.sidebar.selectbox("📅 Anno", anni_disponibili)

st.title(f"📊 Dashboard {anno_selezionato}")

if not df.empty:
    # Calcolo Logica Banca (Su tutto lo storico, non solo l'anno filtrato, per avere il saldo reale)
    accantonati = df[df["Tipo"] == "Accantonamento (-> Banca)"]["Importo"].sum()
    prelevati = df[df["Tipo"] == "Prelievo (<- Banca)"]["Importo"].sum()
    saldo_banca = accantonati - prelevati

    # Filtraggio per l'anno corrente per i grafici
    df_filtrato = df[df["Data"].dt.year == anno_selezionato]
    entrate = df_filtrato[df_filtrato["Tipo"] == "Entrata"]["Importo"].sum()
    uscite = df_filtrato[df_filtrato["Tipo"] == "Uscita"]["Importo"].sum()
    saldo_anno = entrate - uscite

    # KPI - Organizzati in 4 colonne (su mobile diventeranno 1 sopra l'altra)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💰 Entrate", f"€ {entrate:,.2f}")
    c2.metric("💸 Uscite", f"€ {uscite:,.2f}")
    c3.metric("⚖️ Saldo Anno", f"€ {saldo_anno:,.2f}")
    c4.metric("🏦 In Banca (Tot)", f"€ {saldo_banca:,.2f}", help="Soldi totali messi da parte nello storico")
    
    st.divider()

    # Grafico (escludiamo i movimenti banca dal grafico entrate/uscite per non falsare il cashflow)
    df_plot = df_filtrato[df_filtrato["Tipo"].isin(["Entrata", "Uscita"])]
    if not df_plot.empty:
        fig = px.bar(
            df_plot, x="Data", y="Importo", color="Tipo",
            title="Cashflow Mensile",
            color_discrete_map={"Entrata": "#00CC96", "Uscita": "#EF553B"},
            barmode='group'
        )
        st.plotly_chart(fig, use_container_width=True)

    # --- Sezione Editor ---
    with st.expander("📝 Gestione e Modifica Dati"):
        df_modificato = st.data_editor(
            df_filtrato, num_rows="dynamic", hide_index=True, key="editor_v2",
            column_config={
                "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                "Importo": st.column_config.NumberColumn("Importo", format="€ %.2f"),
                "Tipo": st.column_config.SelectboxColumn("Tipo", options=["Uscita", "Entrata", "Accantonamento (-> Banca)", "Prelievo (<- Banca)"])
            }
        )

        if st.button("🔄 Conferma Modifiche Cloud"):
            ids_da_aggiornare = df_filtrato["ID"].tolist()
            df_rimanente = df[~df["ID"].isin(ids_da_aggiornare)]
            
            # Gestione ID per nuove righe nell'editor
            df_modificato["ID"] = df_modificato["ID"].apply(lambda x: genera_id() if not x or pd.isna(x) else x)
            
            df_finale = pd.concat([df_rimanente, df_modificato], ignore_index=True).sort_values(by="Data", ascending=False)
            if salva_dati_su_cloud(df_finale):
                st.success("Database aggiornato!")
                st.rerun()
else:
    st.info("Aggiungi il tuo primo movimento dalla barra laterale!")

