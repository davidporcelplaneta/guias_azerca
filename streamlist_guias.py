import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO
import re

# --- Configuración de la página ---
st.set_page_config(page_title="Filtrado de Leads", layout="centered")

# --- Título ---
st.title("🎯 Carga y procesamiento de leads de empresas")

# --- Subida de archivos ---
st.subheader("1. Sube los archivos necesarios")
uploaded_xlsx = st.file_uploader("📂 Sube el archivo Excel con los leads", type="xlsx")
uploaded_csv = st.file_uploader("📂 Sube el archivo CSV de códigos postales", type="csv")

# ----------------- Helpers -----------------
def normaliza_telefono(val):
    """Deja solo dígitos y quita ceros a la izquierda (salvo que se quede vacío)."""
    if pd.isna(val):
        return pd.NA
    digits = re.sub(r"\D+", "", str(val))
    return digits if digits else pd.NA

def normaliza_email(val):
    """Minúsculas, trim y vacío -> NA. No valida formato estricto para no perder casos."""
    if pd.isna(val):
        return pd.NA
    s = str(val).strip().lower()
    return s if s else pd.NA

def deduplicar_por(df, key_col, date_col):
    """Conserva el registro más reciente por key_col según date_col."""
    df[date_col] = pd.to_datetime(df[date_col], errors='coerce', format='%d/%m/%Y %H:%M')
    df = df.sort_values(by=[key_col, date_col], ascending=[True, False])
    df = df.drop_duplicates(subset=[key_col], keep='first')
    return df

# ---------------------------------------------------------

# Continuar si ambos archivos están cargados
if uploaded_xlsx and uploaded_csv:
    # Leer archivos
    empresas = pd.read_excel(uploaded_xlsx)
    df_cp = pd.read_csv(uploaded_csv, sep=';')

    # --- Selección de fecha ---
    st.subheader("2. Selecciona la fecha desde la cual conservar los datos")
    fecha_inicio = st.date_input("🗓️ Fecha desde la que filtrar", format="DD/MM/YYYY")

    # --- Controles de deduplicación (dos pasos) ---
    st.subheader("2.b Deduplicación en dos pasos")
    col1, col2 = st.columns(2)
    with col1:
        drop_null_phone = st.checkbox("Eliminar filas sin teléfono", value=True)
    with col2:
        drop_null_email = st.checkbox("Eliminar filas sin email", value=True)

    if st.button("Aplicar filtrado, deduplicar (teléfono ➜ email) y procesar"):
        # --- Fechas ---
        empresas['fecha'] = pd.to_datetime(empresas['fecha'], errors='coerce')
        empresas['fecha'] = empresas['fecha'].dt.strftime('%d/%m/%Y %H:%M')
        empresas['fecha_dt'] = pd.to_datetime(empresas['fecha'], format='%d/%m/%Y %H:%M')

        # --- Filtrar por rango de fechas ---
        fecha_filtro = datetime.combine(fecha_inicio, datetime.min.time())
        hoy = datetime.now()

        filas_antes = empresas.shape[0]
        empresas = empresas[
            (empresas['fecha_dt'] >= fecha_filtro) & (empresas['fecha_dt'] <= hoy)
        ].drop(columns='fecha_dt')
        filas_despues = empresas.shape[0]
        filas_eliminadas = filas_antes - filas_despues

        st.success(
            f"✅ Filtrado por fecha completado.\n\n"
            f"Conservadas: {filas_despues} filas.\n"
            f"Eliminadas: {filas_eliminadas}."
        )

        # --- Procesamiento del DataFrame ---
        selected_columns = [
            'id', 'fecha', 'name', 'surname', 'email', 'phone',
            'utm_campaign', 'nombre_webinar', 'nombre_curso',
            'locate_ciudad', 'locate_cp', 'locate_pais', 'teléfono', 'telefono'
        ]
        selected_columns = [c for c in selected_columns if c in empresas.columns]
        empresas = empresas[selected_columns].copy()

        # Prefijo a 'id'
        empresas['id'] = 'azercaguias-' + empresas['id'].astype(str)

        # --- Rellenar con 0 a la izquierda si el CP tiene 4 dígitos ---
        if 'locate_cp' in empresas.columns:
            empresas['locate_cp'] = empresas['locate_cp'].astype(str).str.strip()
            empresas['locate_cp'] = empresas['locate_cp'].apply(
                lambda x: x.zfill(5) if x.isdigit() and len(x) == 4 else x
            )

        # --- Borrar contenido de locate_cp si el país no es Spain ---
        if 'locate_pais' in empresas.columns and 'locate_cp' in empresas.columns:
            empresas.loc[
                empresas['locate_pais'].astype(str).str.strip().str.lower() != 'spain',
                'locate_cp'
            ] = pd.NA

        # Filtrar registros inválidos
        if 'nombre_curso' in empresas.columns:
            empresas = empresas[empresas['nombre_curso'] != 'Ninguno'].copy()
            empresas.drop(columns=['nombre_curso'], inplace=True, errors='ignore')

        # Normalizar CP y nombres
        if 'locate_cp' in empresas.columns:
            empresas['cp'] = empresas['locate_cp'].astype(str).str.zfill(5)
        else:
            empresas['cp'] = pd.NA

        empresas['name'] = empresas.get('name', pd.Series(dtype='object')).astype(str)
        empresas['surname'] = empresas.get('surname', pd.Series(dtype='object')).astype(str)
        empresas['nombreapellidos'] = empresas['name'] + ' ' + empresas['surname']

        # Añadir columnas fijas
        empresas['tipo_registro'] = 'Inbound'
        empresas['subtipo_registro'] = 'Guias'
        empresas['marca'] = 'EAE'
        empresas['subcanal'] = 'Empresas'

        # Renombrados y estandarización de columnas
        if 'teléfono' in empresas.columns and 'telefono' not in empresas.columns:
            empresas = empresas.rename(columns={'teléfono': 'telefono'})
        if 'telefono' not in empresas.columns and 'phone' in empresas.columns:
            empresas['telefono'] = empresas['phone']
        if 'localte_ciudad' in empresas.columns and 'locate_ciudad' not in empresas.columns:
            empresas = empresas.rename(columns={'localte_ciudad': 'locate_ciudad'})

        empresas = empresas.rename(columns={
            'fecha': 'fecha_captacion',
            'utm_campaign': 'origen_dato',
            'nombre_webinar': 'nombre_guia_master',
            'locate_ciudad': 'poblacion'
        })

        # --- Normalización previas para claves ---
        if 'telefono' in empresas.columns:
            empresas['telefono'] = empresas['telefono'].map(normaliza_telefono)
        if 'email' in empresas.columns:
            empresas['email'] = empresas['email'].map(normaliza_email)

        # --- Paso 1: Deduplicación por teléfono ---
        elim_tel_prev = empresas.shape[0]
        if 'telefono' in empresas.columns:
            if drop_null_phone:
                empresas = empresas[empresas['telefono'].notna() & (empresas['telefono'].astype(str).str.len() > 0)]
            # Solo deduplicar si queda la columna y hay valores
            if empresas.shape[0] > 0:
                empresas = deduplicar_por(empresas, key_col='telefono', date_col='fecha_captacion')
        elim_tel_post = empresas.shape[0]
        st.info(f"📱 Paso 1 (teléfono): filas tras el paso = {elim_tel_post} (eliminadas en el paso: {elim_tel_prev - elim_tel_post}).")

        # --- Paso 2: Deduplicación por email ---
        elim_mail_prev = empresas.shape[0]
        if 'email' in empresas.columns:
            if drop_null_email:
                empresas = empresas[empresas['email'].notna() & (empresas['email'].astype(str).str.len() > 0)]
            if empresas.shape[0] > 0:
                empresas = deduplicar_por(empresas, key_col='email', date_col='fecha_captacion')
        elim_mail_post = empresas.shape[0]
        st.info(f"✉️ Paso 2 (email): filas tras el paso = {elim_mail_post} (eliminadas en el paso: {elim_mail_prev - elim_mail_post}).")

        # --- Normalización de CP con tabla de referencia ---
        if 'plvd_name' in df_cp.columns:
            df_merged = pd.merge(
                empresas,
                df_cp[['plvd_name']],
                left_on='cp',
                right_on='plvd_name',
                how='left',
                indicator=True
            )

            df_merged['cp_normalizado'] = df_merged.apply(
                lambda row: row['cp'] if row['_merge'] == 'both'
                else f"{str(row['cp'])[:2]}000" if pd.notna(row['cp']) else pd.NA,
                axis=1
            )

            df_merged = df_merged.drop(columns=['plvd_name', '_merge'])
        else:
            empresas['cp_normalizado'] = empresas['cp'].apply(
                lambda x: x if pd.isna(x) else f"{str(x)[:2]}000"
            )
            df_merged = empresas

        # --- Columnas finales / limpieza ---
        df_final = df_merged.drop(columns=['nombreapellidos', 'locate_cp', 'cp','locate_pais'], errors='ignore')

        # --- Vista previa ---
        st.subheader("3. Vista previa del resultado")
        st.dataframe(df_final.head())

        # --- Descargar resultado ---
        output = BytesIO()
        df_final.to_excel(output, index=False, engine='openpyxl')
        output.seek(0)

        st.download_button(
            label="📥 Descargar Excel procesado (dedupe por teléfono ➜ email)",
            data=output,
            file_name="resultado_guias_azerca.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


