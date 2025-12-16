import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
import uuid
import gspread
import os

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Gestore Finanze Cloud", layout="wide", page_icon="☁️")

@st.cache_resource(ttl=60)
def connetti_google_sheet():
    # CASO 1: Siamo sul Cloud (usiamo i Secrets)
    if "gcp_service_account" in st.secrets:
        try:
            # Creiamo le credenziali dal dizionario dei secrets
            creds_dict = dict(st.secrets["gcp_service_account"])
            client = gspread.service_account_from_dict(creds_dict)
            return client.open("GestioneSpese").sheet1
        except Exception as e:
            st.error(f"Errore Secrets: {e}")
            st.stop()

    # CASO 2: Siamo in locale (usiamo il file json)
    elif os.path.exists("credentials.json"):
        try:
            client = gspread.service_account(filename="credentials.json")
            return client.open("GestioneSpese").sheet1
        except Exception as e:
            st.error(f"Errore Locale: {e}")
            st.stop()
    
    else:
        st.error("⚠️ Nessuna credenziale trovata! Configura i Secrets su Streamlit Cloud o aggiungi credentials.json in locale.")
        st.stop()

def genera_id():
    return str(uuid.uuid4())[:8]

def carica_dati():
    cols = ["ID", "Data", "Tipo", "Categoria", "Importo", "Note"]
    df = pd.DataFrame(columns=cols)
    
    try:
        sheet = connetti_google_sheet()
        raw_data = sheet.get_all_values()

        # Se il foglio è vuoto, inizializziamo le intestazioni
        if not raw_data:
            sheet.append_row(cols)
            return df

        # Carichiamo i dati (saltando l'intestazione se usiamo get_all_records, ma qui usiamo DataFrame diretto)
        data = sheet.get_all_records()
        if data:
            df = pd.DataFrame(data)

            # --- PULIZIA DATI CRUCIALE ---
            # 1. Convertiamo la data
            if "Data" in df.columns:
                df["Data"] = pd.to_datetime(df["Data"], errors='coerce')
                df = df.dropna(subset=["Data"]) # Rimuove righe con date non valide

            # 2. Convertiamo l'importo (gestione virgole/punti)
            if "Importo" in df.columns:
                df["Importo"] = df["Importo"].astype(str).str.replace(',', '.', regex=False)
                df["Importo"] = pd.to_numeric(df["Importo"], errors='coerce').fillna(0.0)

            # 3. Ordiniamo per data
            df = df.sort_values(by="Data", ascending=False)

    except Exception as e:
        st.warning(f"Errore lettura dati o DB vuoto: {e}")
    
    return df

def salva_dati_su_cloud(df):
    try:
        sheet = connetti_google_sheet()
        df_export = df.copy()
        
        # Formattiamo la data come stringa per Google Sheets
        df_export["Data"] = df_export["Data"].dt.strftime('%Y-%m-%d')
        
        # Prepariamo la lista di liste [Intestazioni] + [Dati]
        dati_completi = [df_export.columns.values.tolist()] + df_export.values.tolist()
        
        sheet.clear()
        # Sintassi robusta per gspread recente
        sheet.update(values=dati_completi, range_name='A1') 
        return True
    except Exception as e:
        st.error(f"Errore salvataggio Cloud: {e}")
        return False

# --- 3. INTERFACCIA APP ---
df = carica_dati()

st.sidebar.title("☁️ Gestione Spese")

# --- Form Inserimento ---
with st.sidebar.expander("➕ Aggiungi Movimento", expanded=True):
    with st.form("form_inserimento", clear_on_submit=True):
        data_input = st.date_input("Data", datetime.date.today())
        tipo_input = st.selectbox("Tipo", ["Uscita", "Entrata"])
        
        if tipo_input == "Uscita":
            cat_list = ["Cibo", "Casa", "Trasporti", "Salute", "Svago", "Shopping", "Bollette", "Altro"]
        else:
            cat_list = ["Stipendio", "Bonus", "Vendite", "Rimborsi", "Investimenti", "Altro"]
            
        categoria_input = st.selectbox("Categoria", cat_list)
        importo_input = st.number_input("Importo (€)", min_value=0.0, format="%.2f", step=0.5)
        note_input = st.text_input("Note")
        
        if st.form_submit_button("💾 Salva nel Cloud"):
            nuovo_record = pd.DataFrame({
                "ID": [genera_id()],
                "Data": [pd.to_datetime(data_input)],
                "Tipo": [tipo_input],
                "Categoria": [categoria_input],
                "Importo": [float(importo_input)],
                "Note": [note_input]
            })
            
            df = pd.concat([df, nuovo_record], ignore_index=True)
            
            with st.spinner("Sincronizzazione con Google Sheets..."):
                if salva_dati_su_cloud(df):
                    st.success("Salvato!")
                    st.rerun()

st.sidebar.markdown("---")

# --- Filtri Anno ---
anno_corrente = datetime.date.today().year
anni_disponibili = [anno_corrente]

if not df.empty and "Data" in df.columns:
    anni_db = df["Data"].dt.year.unique().tolist()
    anni_disponibili = sorted(list(set(anni_db + [anno_corrente])), reverse=True)

anno_selezionato = st.sidebar.selectbox("📅 Filtra Anno", anni_disponibili)

# Filtraggio
if not df.empty:
    df_filtrato = df[df["Data"].dt.year == anno_selezionato]
else:
    df_filtrato = pd.DataFrame(columns=df.columns)

# --- DASHBOARD ---
st.title(f"📊 Dashboard {anno_selezionato}")

if not df_filtrato.empty:
    # Calcoli Totali
    entrate = df_filtrato[df_filtrato["Tipo"] == "Entrata"]["Importo"].sum()
    uscite = df_filtrato[df_filtrato["Tipo"] == "Uscita"]["Importo"].sum()
    saldo = entrate - uscite
    
    # KPI
    c1, c2, c3 = st.columns(3)
    c1.metric("💰 Entrate", f"€ {entrate:,.2f}")
    c2.metric("💸 Uscite", f"€ {uscite:,.2f}", delta_color="inverse")
    c3.metric("🏦 Saldo", f"€ {saldo:,.2f}", delta=saldo)
    
    st.divider()

    # Grafico
    fig = px.bar(
        df_filtrato, 
        x="Data", 
        y="Importo", 
        color="Tipo", 
        title="Andamento Entrate/Uscite", 
        color_discrete_map={"Entrata": "#00CC96", "Uscita": "#EF553B"},
        barmode='group'
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- Sezione Editor ---
    st.subheader("📝 Modifica Dati")
    st.info("Modifica le celle qui sotto e premi 'Salva Modifiche' per aggiornare Google Sheets.")
    
    # Editor dati
    df_modificato = st.data_editor(
        df_filtrato, 
        num_rows="dynamic", 
        hide_index=True, 
        key="editor",
        column_config={
            "Data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
            "Importo": st.column_config.NumberColumn("Importo", format="€ %.2f"),
        }
    )

    if st.button("🔄 Aggiorna Database Cloud"):
        # Logica di salvataggio modifiche
        # 1. Carichiamo tutto il DB originale
        df_db_completo = carica_dati()
        
        # 2. Rimuoviamo dal DB originale le righe che stiamo visualizzando (per sostituirle con quelle modificate)
        # Usiamo l'ID per capire quali righe sostituire
        ids_da_aggiornare = df_filtrato["ID"].tolist()
        df_rimanente = df_db_completo[~df_db_completo["ID"].isin(ids_da_aggiornare)]
        
        # 3. Gestiamo nuove righe aggiunte dall'editor (che non hanno ID)
        # Resettiamo l'indice per poter iterare
        df_modificato = df_modificato.reset_index(drop=True)
        for i, row in df_modificato.iterrows():
            if not row["ID"] or pd.isna(row["ID"]):
                df_modificato.at[i, "ID"] = genera_id()
                # Assicuriamoci che i tipi siano corretti per le nuove righe
                if isinstance(row["Data"], str):
                    df_modificato.at[i, "Data"] = pd.to_datetime(row["Data"])

        # 4. Uniamo tutto e salviamo
        df_finale = pd.concat([df_rimanente, df_modificato], ignore_index=True)
        df_finale = df_finale.sort_values(by="Data", ascending=False)
        
        if salva_dati_su_cloud(df_finale):
            st.success("Database aggiornato con successo!")
            st.rerun()

else:
    st.info("📭 Nessun dato presente per l'anno selezionato. Aggiungi una spesa dalla barra laterale!")
