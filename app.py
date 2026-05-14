"""
GEOSPATIAL BRAIN — Gerador de Memorial Descritivo e Tabela de Coordenadas
Padrão LADU / SIGEF / INCRA | SIRGAS 2000
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "core"))

from gerar_memorial import (
    carregar_vertices,
    construir_prosa,
    fmt_br_area,
    fmt_br_distancia,
    normalizar_azimute,
    normalizar_coordenada,
    renderizar_markdown,
)

# ============================================================
# Config
# ============================================================

st.set_page_config(
    page_title="GEOSPATIAL BRAIN — Agrimensura",
    page_icon="🌎",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# CSS mínimo
# ============================================================

st.markdown(
    """
<style>
[data-testid="stSidebar"] { background-color: #0e2240; }
[data-testid="stSidebar"] * { color: #e8edf4 !important; }
[data-testid="stSidebar"] input,
[data-testid="stSidebar"] textarea,
[data-testid="stSidebar"] select { background-color: #1a3155 !important; color: #e8edf4 !important; border: 1px solid #2d5a8c !important; }
[data-testid="stSidebar"] .stExpander { border: 1px solid #2d5a8c !important; }
.memorial-box { background: #fafafa; border: 1px solid #ddd; border-radius: 8px;
    padding: 2rem; font-family: 'Calibri', 'Segoe UI', sans-serif; font-size: 14px;
    line-height: 1.7; max-height: 520px; overflow-y: auto; }
.memorial-box h1 { font-size: 16px; text-align: center; font-weight: bold; }
.badge-ok  { background:#d4edda; color:#155724; padding:4px 12px; border-radius:12px; font-size:13px; }
.badge-err { background:#f8d7da; color:#721c24; padding:4px 12px; border-radius:12px; font-size:13px; }
</style>
""",
    unsafe_allow_html=True,
)

# ============================================================
# Cabeçalho
# ============================================================

col_logo, col_title = st.columns([1, 8])
with col_logo:
    st.markdown("# 🌎")
with col_title:
    st.title("GEOSPATIAL BRAIN")
    st.caption("Gerador de Memorial Descritivo e Tabela de Coordenadas — Padrão LADU / SIGEF / INCRA")

st.divider()

# ============================================================
# SIDEBAR — Metadados
# ============================================================

with st.sidebar:
    st.markdown("## ⚙️ Configuração")

    with st.expander("🏠 Imóvel", expanded=True):
        denominacao   = st.text_input("Denominação", "FAZENDA EXEMPLO")
        matricula     = st.text_input("Matrícula", "1827")
        cns_cartorio  = st.text_input("CNS Cartório", "00.326-9")
        comarca       = st.text_input("Comarca", "Porto de Pedras")
        uf            = st.text_input("UF", "AL", max_chars=2)
        ccir          = st.text_input("Código INCRA/SNCR (CCIR)", "9501069252682")
        municipio     = st.text_input("Município", "Porto de Pedras")
        natureza_area = st.selectbox("Natureza da Área", ["Particular", "Assentamento", "Quilombola", "Indígena", "Pública"])
        area_ha       = st.number_input("Área (ha)", min_value=0.0001, value=253.4741, format="%.4f")
        perimetro_m   = st.number_input("Perímetro (m)", min_value=0.01, value=9868.92, format="%.2f")

    with st.expander("👤 Proprietário", expanded=False):
        prop_nome = st.text_input("Nome completo", "LUIZ HENRIQUE CAVALCANTE MELO")
        prop_cpf  = st.text_input("CPF", "008.930.464-00")

    with st.expander("📐 Responsável Técnico", expanded=False):
        rt_nome    = st.text_input("Nome", "GUSTAVO HENRIQUE CABRAL DE MELO")
        rt_formacao = st.selectbox("Formação", ["Engenheiro Agrimensor", "Engenheiro Cartógrafo", "Engenheiro Civil", "Engenheiro Agronômico"])
        rt_crea    = st.text_input("CREA", "022229789-1/AL")
        rt_credenc = st.text_input("Código de Credenciamento INCRA", "LADU")
        rt_art     = st.text_input("Documento de RT (ART)", "AL20260536392 - AL")

    with st.expander("🔏 Certificação SIGEF (opcional)", expanded=False):
        usar_sigef  = st.checkbox("Incluir bloco SIGEF", value=False)
        sigef_cod   = st.text_input("Código SIGEF (UUID)", "")
        sigef_data  = st.text_input("Data da certificação", "")

    st.divider()

    st.markdown("#### 📥 Carregar configuração (meta.json)")
    meta_upload = st.file_uploader("meta.json", type=["json"], label_visibility="collapsed")
    if meta_upload:
        try:
            meta_ext = json.load(meta_upload)
            im = meta_ext.get("imovel", {})
            pr = meta_ext.get("proprietario", {})
            rt = meta_ext.get("rt", {})
            sg = meta_ext.get("certificacao_sigef", {})
            denominacao   = im.get("denominacao", denominacao)
            matricula     = str(im.get("matricula", matricula))
            cns_cartorio  = im.get("cns_cartorio", cns_cartorio)
            comarca       = im.get("comarca", comarca)
            uf            = im.get("uf", uf)
            ccir          = str(im.get("ccir", ccir))
            municipio     = im.get("municipio", municipio)
            natureza_area = im.get("natureza_area", natureza_area)
            area_ha       = float(im.get("area_ha", area_ha))
            perimetro_m   = float(im.get("perimetro_m", perimetro_m))
            prop_nome     = pr.get("nome", prop_nome)
            prop_cpf      = pr.get("cpf", prop_cpf)
            rt_nome       = rt.get("nome", rt_nome)
            rt_formacao   = rt.get("formacao", rt_formacao)
            rt_crea       = rt.get("crea", rt_crea)
            rt_credenc    = rt.get("credenciado_codigo", rt_credenc)
            rt_art        = rt.get("art", rt_art)
            usar_sigef    = bool(sg.get("incluir", usar_sigef))
            sigef_cod     = sg.get("codigo", sigef_cod)
            sigef_data    = sg.get("data", sigef_data)
            st.success("meta.json carregado")
        except Exception as e:
            st.error(f"Erro ao ler meta.json: {e}")


# ============================================================
# Constrói o dicionário meta a partir do sidebar
# ============================================================

def build_meta() -> dict:
    return {
        "imovel": {
            "denominacao": denominacao,
            "matricula": matricula,
            "cns_cartorio": cns_cartorio,
            "comarca": comarca,
            "uf": uf.upper(),
            "ccir": ccir,
            "municipio": municipio,
            "natureza_area": natureza_area,
            "area_ha": area_ha,
            "perimetro_m": perimetro_m,
        },
        "proprietario": {"nome": prop_nome, "cpf": prop_cpf},
        "rt": {
            "nome": rt_nome,
            "formacao": rt_formacao,
            "crea": rt_crea,
            "credenciado_codigo": rt_credenc,
            "art": rt_art,
        },
        "certificacao_sigef": {
            "incluir": usar_sigef,
            "codigo": sigef_cod,
            "data": sigef_data,
        },
    }


# ============================================================
# TABS principais
# ============================================================

tab_vert, tab_memorial, tab_tabela = st.tabs([
    "📍 Vértices",
    "📄 Memorial Descritivo",
    "📊 Tabela de Coordenadas",
])

# ============================================================
# TAB 1 — VÉRTICES
# ============================================================

with tab_vert:
    st.subheader("Entrada de Vértices")

    col_up, col_dl = st.columns([3, 1])
    with col_dl:
        # Download CSV modelo
        modelo_path = Path(__file__).parent / "dados" / "exemplo_vertices.csv"
        modelo_bytes = modelo_path.read_bytes() if modelo_path.exists() else b""
        st.download_button(
            "⬇️ Baixar CSV modelo",
            data=modelo_bytes,
            file_name="modelo_vertices.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with col_up:
        uploaded_csv = st.file_uploader(
            "Faça upload do CSV de vértices ou use o editor abaixo:",
            type=["csv", "xlsx", "xls"],
            label_visibility="visible",
        )

    COLUNAS_PADRAO = {
        "ordem": 1,
        "vertice": "ALG-P-0001",
        "lat": "9°00'00,000\"",
        "long": "35°00'00,000\"",
        "azimute": "0°00'",
        "distancia": 100.0,
        "confrontante": "",
        "matricula_conf": "",
        "cns_conf": "",
    }

    if uploaded_csv is not None:
        try:
            if uploaded_csv.name.endswith((".xlsx", ".xls")):
                df_vert = pd.read_excel(uploaded_csv, dtype=str)
            else:
                df_vert = pd.read_csv(uploaded_csv, dtype=str, sep=None, engine="python", encoding="utf-8-sig")
            df_vert.columns = [c.strip().lower() for c in df_vert.columns]
            # rename latitude/longitude → lat/long
            rn = {}
            if "latitude" in df_vert.columns and "lat" not in df_vert.columns:
                rn["latitude"] = "lat"
            if "longitude" in df_vert.columns and "long" not in df_vert.columns:
                rn["longitude"] = "long"
            if rn:
                df_vert = df_vert.rename(columns=rn)
            if "ordem" in df_vert.columns:
                df_vert["ordem"] = pd.to_numeric(df_vert["ordem"], errors="coerce")
                df_vert = df_vert.sort_values("ordem").reset_index(drop=True)
            st.session_state["df_vertices"] = df_vert
            st.success(f"CSV carregado: **{len(df_vert)} vértices**")
        except Exception as e:
            st.error(f"Erro ao ler arquivo: {e}")

    # Inicializa editor com vértices vazios se não há upload
    if "df_vertices" not in st.session_state:
        st.session_state["df_vertices"] = pd.DataFrame(
            [COLUNAS_PADRAO.copy() for _ in range(5)]
        )

    st.markdown("**Editor de vértices** (edite diretamente na tabela):")
    df_editado = st.data_editor(
        st.session_state["df_vertices"],
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "ordem":         st.column_config.NumberColumn("Ordem", min_value=1, step=1),
            "vertice":       st.column_config.TextColumn("Vértice"),
            "lat":           st.column_config.TextColumn("Latitude (GMS ou decimal)"),
            "long":          st.column_config.TextColumn("Longitude (GMS ou decimal)"),
            "azimute":       st.column_config.TextColumn("Azimute"),
            "distancia":     st.column_config.NumberColumn("Distância (m)", format="%.2f"),
            "confrontante":  st.column_config.TextColumn("Confrontante"),
            "matricula_conf":st.column_config.TextColumn("Matrícula conf."),
            "cns_conf":      st.column_config.TextColumn("CNS conf."),
        },
        key="editor_vertices",
    )

    st.session_state["df_vertices"] = df_editado

    # Validação rápida
    df_val = df_editado.dropna(subset=["vertice", "lat", "long"])
    n_total = len(df_editado)
    n_ok = len(df_val)
    st.markdown(
        f'<span class="badge-ok">✔ {n_ok} vértices válidos</span>'
        + (f' <span class="badge-err">⚠ {n_total - n_ok} sem coordenadas</span>' if n_ok < n_total else ""),
        unsafe_allow_html=True,
    )

    # Colunas obrigatórias presentes?
    obrig = {"vertice", "lat", "long", "azimute", "distancia", "confrontante"}
    faltando = obrig - set(df_editado.columns)
    if faltando:
        st.warning(f"Colunas obrigatórias faltando: {', '.join(sorted(faltando))}")


# ============================================================
# TAB 2 — MEMORIAL DESCRITIVO
# ============================================================

with tab_memorial:
    st.subheader("Memorial Descritivo — Padrão LADU/SIGEF")

    df_mem = st.session_state.get("df_vertices", pd.DataFrame())
    obrig_mem = {"vertice", "lat", "long", "azimute", "distancia", "confrontante"}

    if df_mem.empty or not obrig_mem.issubset(set(df_mem.columns)):
        st.info("Carregue os vértices na aba **📍 Vértices** para gerar o memorial.")
    else:
        df_mem_clean = df_mem.copy()
        df_mem_clean.columns = [c.strip().lower() for c in df_mem_clean.columns]
        df_mem_clean = df_mem_clean.dropna(subset=["vertice", "lat", "long"])
        if "distancia" in df_mem_clean.columns:
            df_mem_clean["distancia"] = (
                df_mem_clean["distancia"].astype(str).str.replace(",", ".").astype(float)
            )
        if "ordem" in df_mem_clean.columns:
            df_mem_clean["ordem"] = pd.to_numeric(df_mem_clean["ordem"], errors="coerce")
            df_mem_clean = df_mem_clean.sort_values("ordem").reset_index(drop=True)

        meta = build_meta()

        try:
            texto_md = renderizar_markdown(df_mem_clean, meta)

            # Preview HTML
            import re as _re
            html_preview = texto_md
            # Negrito
            html_preview = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html_preview)
            # Cabeçalho H1
            html_preview = _re.sub(r"^# (.+)$", r"<h1>\1</h1>", html_preview, flags=_re.MULTILINE)
            # Quebra de linha
            html_preview = html_preview.replace("\n\n", "</p><p>").replace("\n", "<br>")
            html_preview = f"<p>{html_preview}</p>"

            st.markdown(
                f'<div class="memorial-box">{html_preview}</div>',
                unsafe_allow_html=True,
            )

            st.divider()

            col_dl1, col_dl2, col_dl3 = st.columns(3)

            # Download .md
            with col_dl1:
                st.download_button(
                    "⬇️ Baixar Memorial (.md)",
                    data=texto_md.encode("utf-8"),
                    file_name="memorial_descritivo.md",
                    mime="text/markdown",
                    use_container_width=True,
                )

            # Download .txt (mesma coisa, sem markdown)
            texto_txt = _re.sub(r"\*\*(.+?)\*\*", r"\1", texto_md)
            texto_txt = _re.sub(r"^#+\s*", "", texto_txt, flags=_re.MULTILINE)
            with col_dl2:
                st.download_button(
                    "⬇️ Baixar Memorial (.txt)",
                    data=texto_txt.encode("utf-8"),
                    file_name="memorial_descritivo.txt",
                    mime="text/plain",
                    use_container_width=True,
                )

            # Download .docx (python-docx)
            with col_dl3:
                try:
                    from gerar_memorial import renderizar_docx
                    buf_docx = io.BytesIO()

                    import tempfile, os
                    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
                        tmp_path = tmp.name
                    renderizar_docx(df_mem_clean, meta, tmp_path)
                    with open(tmp_path, "rb") as f:
                        docx_bytes = f.read()
                    os.unlink(tmp_path)

                    st.download_button(
                        "⬇️ Baixar Memorial (.docx)",
                        data=docx_bytes,
                        file_name="memorial_descritivo.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True,
                    )
                except Exception as e_docx:
                    st.button("⬇️ Baixar Memorial (.docx)", disabled=True, use_container_width=True,
                              help=f"python-docx não instalado: {e_docx}")

            # Download meta.json
            st.divider()
            st.markdown("**Exportar configuração atual:**")
            meta_json_str = json.dumps(meta, ensure_ascii=False, indent=2)
            st.download_button(
                "⬇️ Exportar meta.json",
                data=meta_json_str.encode("utf-8"),
                file_name="meta.json",
                mime="application/json",
            )

        except Exception as e:
            st.error(f"Erro ao gerar memorial: {e}")
            st.exception(e)


# ============================================================
# TAB 3 — TABELA DE COORDENADAS
# ============================================================

with tab_tabela:
    st.subheader("Tabela de Coordenadas")

    df_tab = st.session_state.get("df_vertices", pd.DataFrame())
    obrig_tab = {"vertice", "lat", "long", "azimute", "distancia", "confrontante"}

    if df_tab.empty or not obrig_tab.issubset(set(df_tab.columns)):
        st.info("Carregue os vértices na aba **📍 Vértices** para gerar a tabela.")
    else:
        df_tab = df_tab.copy()
        df_tab.columns = [c.strip().lower() for c in df_tab.columns]
        df_tab = df_tab.dropna(subset=["vertice", "lat", "long"])
        if "ordem" in df_tab.columns:
            df_tab["ordem"] = pd.to_numeric(df_tab["ordem"], errors="coerce")
            df_tab = df_tab.sort_values("ordem").reset_index(drop=True)
        if "distancia" in df_tab.columns:
            df_tab["distancia"] = (
                df_tab["distancia"].astype(str).str.replace(",", ".").astype(float)
            )

        # Formata cada coluna
        rows = []
        for _, row in df_tab.iterrows():
            lat_fmt  = normalizar_coordenada(row["lat"])  + " S"
            long_fmt = normalizar_coordenada(row["long"]) + " W"
            az_fmt   = normalizar_azimute(row["azimute"])
            dist_fmt = fmt_br_distancia(float(row["distancia"])) + " m"
            conf     = str(row.get("confrontante", "")).strip()
            matr     = str(row.get("matricula_conf", "")).strip()
            cns      = str(row.get("cns_conf", "")).strip()

            conf_fmt = conf
            if matr and matr.lower() not in ("nan", ""):
                conf_fmt += f" (Mat. {matr}"
                if cns and cns.lower() not in ("nan", ""):
                    conf_fmt += f", CNS {cns}"
                conf_fmt += ")"

            rows.append({
                "Vértice": row["vertice"],
                "Latitude (S)": lat_fmt,
                "Longitude (W)": long_fmt,
                "Azimute": az_fmt,
                "Distância": dist_fmt,
                "Confrontante": conf_fmt,
            })

        df_saida = pd.DataFrame(rows)

        # Métricas
        meta_tab = build_meta()
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Vértices", len(df_saida))
        col_m2.metric("Área", f"{fmt_br_area(meta_tab['imovel']['area_ha'])} ha")
        col_m3.metric("Perímetro", f"{fmt_br_distancia(meta_tab['imovel']['perimetro_m'])} m")

        st.dataframe(df_saida, use_container_width=True, height=420)

        st.divider()

        col_csv, col_xlsx = st.columns(2)

        # CSV
        csv_bytes = df_saida.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        with col_csv:
            st.download_button(
                "⬇️ Baixar Tabela (.csv)",
                data=csv_bytes,
                file_name="tabela_coordenadas.csv",
                mime="text/csv",
                use_container_width=True,
            )

        # XLSX
        with col_xlsx:
            try:
                buf_xl = io.BytesIO()
                with pd.ExcelWriter(buf_xl, engine="openpyxl") as writer:
                    # Aba principal: tabela formatada
                    df_saida.to_excel(writer, index=False, sheet_name="Coordenadas")

                    # Aba secundária: dados brutos
                    df_tab.to_excel(writer, index=False, sheet_name="Dados Brutos")

                    # Aba memorial em texto
                    df_txt = pd.DataFrame(
                        {"Memorial Descritivo": [
                            renderizar_markdown(df_tab, meta_tab)
                        ]}
                    )
                    df_txt.to_excel(writer, index=False, sheet_name="Memorial")

                st.download_button(
                    "⬇️ Baixar Tabela (.xlsx)",
                    data=buf_xl.getvalue(),
                    file_name="tabela_coordenadas.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
            except Exception as e_xl:
                st.button("⬇️ Baixar Tabela (.xlsx)", disabled=True,
                          help=f"openpyxl não instalado: {e_xl}", use_container_width=True)

        # Tabela completa com colunas brutas (opcional)
        with st.expander("Ver dados brutos (CSV original)"):
            st.dataframe(df_tab, use_container_width=True)
