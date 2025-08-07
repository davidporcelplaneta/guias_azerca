import streamlit as st
import pandas as pd
import os
from datetime import datetime
from io import BytesIO

st.set_page_config(page_title="Filtrado de Leads", layout="centered")

# --- Título ---
st.title("🎯 Carga y procesamiento de leads de empresas")

# --- Subida de archivos ---
st.subheader("1. Sube los archivos necesarios")
uploaded_xlsx = st.file_uploader("📂 Sube el archivo Excel con los leads", type="xlsx")
uploaded_csv = st.file_uploader("📂 Sube el archivo CSV de códigos postales", type="csv")

# Continuar si ambos archivos están cargados
if uploaded_xlsx and uploaded_csv:
    # Leer archivos
    empresas = pd.read_excel(uploaded_xlsx)
    df_cp = pd.read_csv(uploaded_csv, sep=';')

    # --- Selección de fecha ---
    st.subheader("2. Selecciona la fecha desde la cual conservar los datos")
    fecha_inicio = st.date_input("🗓️ Fecha desde la que filtrar", format="DD/MM/YYYY")

    if st.button("Aplicar filtrado y procesar"):
        # Formatear y convertir fecha
        empresas['fecha'] = pd.to_datetime(empresas['fecha'], errors='coerce')
        empresas['fecha'] = empresas['fecha'].dt.strftime('%d/%m/%Y %H:%M')
        empresas['fecha_dt'] = pd.to_datetime(empresas['fecha'], format='%d/%m/%Y %H:%M')

        # Filtrar
        fecha_filtro = datetime.combine(fecha_inicio, datetime.min.time())
        hoy = datetime.now()

        filas_antes = empresas.shape[0]
        empresas = empresas[(empresas['fecha_dt'] >= fecha_filtro) & (empresas['fecha_dt'] <= hoy)].drop(columns='fecha_dt')
        filas_despues = empresas.shape[0]
        filas_eliminadas = filas_antes - filas_despues

        st.success(f"✅ Filtrado completado.\n\nConservadas: {filas_despues} filas.\nEliminadas: {filas_eliminadas}.")

        # --- Procesamiento del DataFrame ---
        selected_columns = [
            'id','fecha',  'name', 'surname', 'email', 'phone',
            'utm_campaign', 'nombre_webinar', 'nombre_curso', 'locate_ciudad','locate_cp'
        ]
        empresas = empresas[selected_columns]

        # Filtrado por nombre_curso
        empresas = empresas[empresas['nombre_curso'] != 'Ninguno'].copy()
        empresas.drop(columns=['nombre_curso'], inplace=True)

        # CP y nombres
        empresas['cp'] = empresas['locate_cp'].astype(str).str.zfill(5)
        empresas['name'] = empresas['name'].astype(str)
        empresas['surname'] = empresas['surname'].astype(str)
        empresas['nombreapellidos'] = empresas['name'] + ' ' + empresas['surname']

        # Añadir columnas fijas
        empresas['tipo_registro'] = 'Inbound'
        empresas['subtipo_registro'] = 'Guias'
        empresas['marca'] = 'EAE'
        empresas['subcanal'] = 'Empresas'

        # Renombrar columnas
        empresas = empresas.rename(columns={
            'teléfono': 'telefono',
            'email': 'email',
            'fecha': 'fecha_captacion',
            'utm_campaign': 'origen_dato',
            'nombre_webinar': 'nombre_guia_master',
            'localte_ciudad': 'poblacion'
        })

        # Normalización de CP
        df_merged = pd.merge(empresas, df_cp[['plvd_name']], left_on='cp', right_on='plvd_name', how='left', indicator=True)
        df_merged['cp_normalizado'] = df_merged.apply(
            lambda row: row['cp'] if row['_merge'] == 'both' else f"{str(row['cp'])[:2]}000", axis=1
        )
        df_merged = df_merged.drop(columns=['plvd_name', '_merge'])
        df_final = df_merged.drop(columns=['nombreapellidos', 'locate_cp', 'cp'])

        # Mostrar muestra
        st.subheader("3. Vista previa del resultado")
        st.dataframe(df_final.head())

        # Descargar resultado
        output = BytesIO()
        df_final.to_excel(output, index=False, engine='openpyxl')
        output.seek(0)

        st.download_button(
            label="📥 Descargar Excel procesado",
            data=output,
            file_name="resultado_guias_azerca.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


