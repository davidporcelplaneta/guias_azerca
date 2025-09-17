import streamlit as st
import pandas as pd
import os
from datetime import datetime, time
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

    # Normaliza nombres de columnas a minúsculas y sin espacios
    empresas.columns = [c.strip().lower() for c in empresas.columns]
    df_cp.columns = [c.strip() for c in df_cp.columns]

    # --- Mapeo de columnas origen -> destino estandarizadas ---
    rename_map_posibles = {
        'phone': 'telefono',
        'teléfono': 'telefono',  # por si viene con acento
        'fecha': 'fecha_captacion',
        'utm_campaign': 'origen_dato',
        'nombre_webinar': 'nombre_guia_master',
        'locate_ciudad': 'poblacion',   # corrige el typo del código original
    }
    # Aplica solo las que existan en el archivo
    rename_map = {k: v for k, v in rename_map_posibles.items() if k in empresas.columns}
    empresas = empresas.rename(columns=rename_map)

    # --- Selección de fecha ---
    st.subheader("2. Selecciona la fecha desde la cual conservar los datos")
    fecha_inicio = st.date_input("🗓️ Fecha desde la que filtrar", format="DD/MM/YYYY")

    if st.button("Aplicar filtrado y procesar"):
        # Asegura columna de fecha
        if 'fecha_captacion' not in empresas.columns:
            st.error("❌ No se encuentra la columna de fecha ('fecha' o 'fecha_captacion').")
            st.stop()

        # Parseo robusto de fechas (día/mes/año)
        empresas['fecha_captacion'] = pd.to_datetime(
            empresas['fecha_captacion'], errors='coerce', dayfirst=True
        )

        # Filtrar por rango [fecha_inicio, hoy]
        start_dt = datetime.combine(fecha_inicio, time.min)
        end_dt = datetime.now()
        filas_antes = len(empresas)
        empresas = empresas[empresas['fecha_captacion'].between(start_dt, end_dt)]
        filas_despues = len(empresas)
        filas_eliminadas = filas_antes - filas_despues

        st.success(
            f"✅ Filtrado completado.\n\nConservadas: {filas_despues} filas.\nEliminadas: {filas_eliminadas}."
        )

        # --- Añade prefijo a id (si existe) ---
        if 'id' in empresas.columns:
            empresas['id'] = 'azercaguias-' + empresas['id'].astype(str)
        else:
            st.warning("⚠️ No se encontró la columna 'id'. Se continuará sin prefijo.")

        # --- Borrar locate_cp si el país no es Spain ---
        if 'locate_pais' in empresas.columns and 'locate_cp' in empresas.columns:
            mask = empresas['locate_pais'].astype(str).str.strip().str.lower() != 'spain'
            empresas.loc[mask, 'locate_cp'] = pd.NA

        # --- Columnas mínimas esperadas tras renombrar ---
        # Nota: 'telefono' ya puede venir de 'phone' o 'teléfono'
        columnas_necesarias = [
            'id', 'fecha_captacion', 'name', 'surname', 'email', 'telefono',
            'origen_dato', 'nombre_guia_master', 'nombre_curso', 'poblacion', 'locate_cp'
        ]
        # Mantén solo las que existan (evita errores por ausencias)
        columnas_presentes = [c for c in columnas_necesarias if c in empresas.columns]
        empresas = empresas[columnas_presentes].copy()

        # Filtrado por nombre_curso (si existe)
        if 'nombre_curso' in empresas.columns:
            empresas = empresas[empresas['nombre_curso'] != 'Ninguno'].copy()
            empresas.drop(columns=['nombre_curso'], inplace=True)

        # CP y nombres
        # Intenta usar locate_cp si existe; si no, intenta 'cp'
        if 'locate_cp' in empresas.columns:
            cp_src = 'locate_cp'
        elif 'cp' in empresas.columns:
            cp_src = 'cp'
        else:
            cp_src = None

        if cp_src:
            empresas['cp'] = (
                empresas[cp_src]
                .astype(str)
                .str.replace(r'\D+', '', regex=True)  # quita no-dígitos
                .str.zfill(5)
            )
        else:
            empresas['cp'] = pd.NA
            st.warning("⚠️ No se encontró 'locate_cp' ni 'cp'. Se creará 'cp' vacío.")

        empresas['name'] = empresas.get('name', pd.Series(dtype=str)).astype(str)
        empresas['surname'] = empresas.get('surname', pd.Series(dtype=str)).astype(str)
        empresas['nombreapellidos'] = (empresas['name'].fillna('') + ' ' + empresas['surname'].fillna('')).str.strip()

        # Añadir columnas fijas
        empresas['tipo_registro'] = 'Inbound'
        empresas['subtipo_registro'] = 'Guias'
        empresas['marca'] = 'EAE'
        empresas['subcanal'] = 'Empresas'

        # --- Normalización de CP con catálogo ---
        if 'plvd_name' not in df_cp.columns:
            st.error("❌ El CSV de códigos postales debe contener la columna 'plvd_name'.")
            st.stop()

        df_cp['plvd_name'] = (
            df_cp['plvd_name'].astype(str).str.replace(r'\D+', '', regex=True).str.zfill(5)
        )

        df_merged = pd.merge(
            empresas,
            df_cp[['plvd_name']],
            left_on='cp',
            right_on='plvd_name',
            how='left',
            indicator=True
        )

        df_merged['cp_normalizado'] = df_merged.apply(
            lambda row: row['cp'] if row['_merge'] == 'both' and pd.notna(row['cp'])
            else (str(row['cp'])[:2] + "000") if pd.notna(row['cp']) and len(str(row['cp'])) >= 2
            else pd.NA,
            axis=1
        )

        # Limpieza de columnas auxiliares
        cols_drop = [c for c in ['plvd_name', '_merge', 'nombreapellidos', 'locate_cp', 'cp'] if c in df_merged.columns]
        df_final = df_merged.drop(columns=cols_drop)

        # Mostrar muestra
        st.subheader("3. Vista previa del resultado")
        st.dataframe(df_final.head(50))

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
