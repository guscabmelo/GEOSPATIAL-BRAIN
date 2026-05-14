"""
GEOSPATIAL BRAIN — Gerador de Memorial Descritivo e Tabela de Coordenadas
Padrão LADU / SIGEF / INCRA | SIRGAS 2000 | SGL

Baseado na skill engenheiro-agrimensor-analitico.
"""

from __future__ import annotations

import io
import json
import re as _re
import sys
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "core"))

from gerar_memorial import (
    construir_prosa,
    fmt_br_area,
    fmt_br_distancia,
    normalizar_azimute,
    normalizar_coordenada,
    renderizar_docx,
    renderizar_markdown,
)
from parser_pdf_sigef import parse_pdf_sigef, VERTEX_RE, LEG_RE

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
# RT padrão LADU (vindo do dados_rt_padrao.json da skill)
# ============================================================

RT_LADU = {
    "nome":               "GUSTAVO HENRIQUE CABRAL DE MELO",
    "formacao":           "Engenheiro Agrimensor",
    "crea":               "022229789-1/AL",
    "credenciado_codigo": "LADU",
    "art":                "AL20260536392 - AL",
}

# ============================================================
# Session state — defaults
# ============================================================

DEFAULTS = {
    # Imóvel
    "denominacao":   "FAZENDA EXEMPLO",
    "matricula":     "1827",
    "cns_cartorio":  "00.326-9",
    "comarca":       "Porto de Pedras",
    "uf":            "AL",
    "ccir":          "9501069252682",
    "municipio":     "Porto de Pedras",
    "natureza_area": "Particular",
    "area_ha":       253.4741,
    "perimetro_m":   9868.92,
    # Proprietário
    "prop_nome":     "LUIZ HENRIQUE CAVALCANTE MELO",
    "prop_cpf":      "008.930.464-00",
    # RT
    "rt_nome":       RT_LADU["nome"],
    "rt_formacao":   RT_LADU["formacao"],
    "rt_crea":       RT_LADU["crea"],
    "rt_credenc":    RT_LADU["credenciado_codigo"],
    "rt_art":        RT_LADU["art"],
    # SIGEF
    "usar_sigef":    False,
    "sigef_cod":     "",
    "sigef_data":    "",
    # Vértices
    "df_vertices":   None,
    # Estado de importação PDF
    "pdf_parsed":    None,    # resultado do último parse
}

for _k, _v in DEFAULTS.items():
    st.session_state.setdefault(_k, _v)

# Vértices iniciais vazios
if st.session_state["df_vertices"] is None:
    st.session_state["df_vertices"] = pd.DataFrame([{
        "ordem": 1,
        "vertice": "ALG-P-0001",
        "lat": "9°00'00,000\"",
        "long": "35°00'00,000\"",
        "azimute": "0°00'",
        "distancia": 100.0,
        "confrontante": "",
        "matricula_conf": "",
        "cns_conf": "",
    }])

# ============================================================
# CSS
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
.rt-warn {
  background: #fff3cd; border-left: 5px solid #ffc107; padding: 16px;
  border-radius: 4px; margin: 12px 0;
}
.rt-warn h4 { margin: 0 0 8px 0; color: #856404; }
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
# SIDEBAR — Metadados (usa session_state via key=)
# ============================================================

with st.sidebar:
    st.markdown("## ⚙️ Configuração")

    with st.expander("🏠 Imóvel", expanded=True):
        st.text_input("Denominação", key="denominacao")
        st.text_input("Matrícula", key="matricula")
        st.text_input("CNS Cartório", key="cns_cartorio")
        st.text_input("Comarca", key="comarca")
        st.text_input("UF", key="uf", max_chars=2)
        st.text_input("Código INCRA/SNCR (CCIR)", key="ccir")
        st.text_input("Município", key="municipio")
        st.selectbox(
            "Natureza da Área",
            ["Particular", "Assentamento", "Quilombola", "Indígena", "Pública"],
            key="natureza_area",
        )
        st.number_input("Área (ha)", min_value=0.0001, format="%.4f", key="area_ha")
        st.number_input("Perímetro (m)", min_value=0.01, format="%.2f", key="perimetro_m")

    with st.expander("👤 Proprietário"):
        st.text_input("Nome completo", key="prop_nome")
        st.text_input("CPF", key="prop_cpf")

    with st.expander("📐 Responsável Técnico"):
        st.text_input("Nome", key="rt_nome")
        st.selectbox(
            "Formação",
            ["Engenheiro Agrimensor", "Engenheiro Cartógrafo", "Engenheiro Civil", "Engenheiro Agronômico"],
            key="rt_formacao",
        )
        st.text_input("CREA", key="rt_crea")
        st.text_input("Código de Credenciamento INCRA", key="rt_credenc")
        st.text_input("Documento de RT (ART)", key="rt_art")

    with st.expander("🔏 Certificação SIGEF"):
        st.checkbox("Incluir bloco SIGEF", key="usar_sigef")
        st.text_input("Código SIGEF (UUID)", key="sigef_cod")
        st.text_input("Data da certificação", key="sigef_data")

    st.divider()

    st.markdown("#### 📥 Carregar meta.json")
    meta_upload = st.file_uploader("meta.json", type=["json"], label_visibility="collapsed", key="meta_uploader")
    if meta_upload:
        try:
            meta_ext = json.load(meta_upload)
            im = meta_ext.get("imovel", {})
            pr = meta_ext.get("proprietario", {})
            rt = meta_ext.get("rt", {})
            sg = meta_ext.get("certificacao_sigef", {})
            st.session_state["denominacao"]   = im.get("denominacao", st.session_state["denominacao"])
            st.session_state["matricula"]     = str(im.get("matricula", st.session_state["matricula"]))
            st.session_state["cns_cartorio"]  = im.get("cns_cartorio", st.session_state["cns_cartorio"])
            st.session_state["comarca"]       = im.get("comarca", st.session_state["comarca"])
            st.session_state["uf"]            = im.get("uf", st.session_state["uf"])
            st.session_state["ccir"]          = str(im.get("ccir", st.session_state["ccir"]))
            st.session_state["municipio"]     = im.get("municipio", st.session_state["municipio"])
            st.session_state["natureza_area"] = im.get("natureza_area", st.session_state["natureza_area"])
            st.session_state["area_ha"]       = float(im.get("area_ha", st.session_state["area_ha"]))
            st.session_state["perimetro_m"]   = float(im.get("perimetro_m", st.session_state["perimetro_m"]))
            st.session_state["prop_nome"]     = pr.get("nome", st.session_state["prop_nome"])
            st.session_state["prop_cpf"]      = pr.get("cpf", st.session_state["prop_cpf"])
            st.session_state["rt_nome"]       = rt.get("nome", st.session_state["rt_nome"])
            st.session_state["rt_formacao"]   = rt.get("formacao", st.session_state["rt_formacao"])
            st.session_state["rt_crea"]       = rt.get("crea", st.session_state["rt_crea"])
            st.session_state["rt_credenc"]    = rt.get("credenciado_codigo", st.session_state["rt_credenc"])
            st.session_state["rt_art"]        = rt.get("art", st.session_state["rt_art"])
            st.session_state["usar_sigef"]    = bool(sg.get("incluir", st.session_state["usar_sigef"]))
            st.session_state["sigef_cod"]     = sg.get("codigo", st.session_state["sigef_cod"])
            st.session_state["sigef_data"]    = sg.get("data", st.session_state["sigef_data"])
            st.success("meta.json carregado")
            st.rerun()
        except Exception as e:
            st.error(f"Erro ao ler meta.json: {e}")


# ============================================================
# Helpers
# ============================================================

def build_meta() -> dict:
    return {
        "imovel": {
            "denominacao":   st.session_state["denominacao"],
            "matricula":     st.session_state["matricula"],
            "cns_cartorio":  st.session_state["cns_cartorio"],
            "comarca":       st.session_state["comarca"],
            "uf":            st.session_state["uf"].upper(),
            "ccir":          st.session_state["ccir"],
            "municipio":     st.session_state["municipio"],
            "natureza_area": st.session_state["natureza_area"],
            "area_ha":       st.session_state["area_ha"],
            "perimetro_m":   st.session_state["perimetro_m"],
        },
        "proprietario": {
            "nome": st.session_state["prop_nome"],
            "cpf":  st.session_state["prop_cpf"],
        },
        "rt": {
            "nome":               st.session_state["rt_nome"],
            "formacao":           st.session_state["rt_formacao"],
            "crea":               st.session_state["rt_crea"],
            "credenciado_codigo": st.session_state["rt_credenc"],
            "art":                st.session_state["rt_art"],
        },
        "certificacao_sigef": {
            "incluir": st.session_state["usar_sigef"],
            "codigo":  st.session_state["sigef_cod"],
            "data":    st.session_state["sigef_data"],
        },
    }


def aplicar_meta_extraido(meta_extraido: dict, usar_ladu_como_rt: bool) -> None:
    """Copia meta extraído do PDF para o session_state. Respeita a regra de RT."""
    im = meta_extraido.get("imovel", {})
    pr = meta_extraido.get("proprietario", {})
    rt = meta_extraido.get("rt", {})
    sg = meta_extraido.get("certificacao_sigef", {})

    if im.get("denominacao"):   st.session_state["denominacao"]   = im["denominacao"]
    if im.get("matricula"):     st.session_state["matricula"]     = str(im["matricula"])
    if im.get("cns_cartorio"):  st.session_state["cns_cartorio"]  = im["cns_cartorio"]
    if im.get("comarca"):       st.session_state["comarca"]       = im["comarca"]
    if im.get("uf"):            st.session_state["uf"]            = im["uf"]
    if im.get("ccir"):          st.session_state["ccir"]          = str(im["ccir"])
    if im.get("municipio"):     st.session_state["municipio"]     = im["municipio"]
    if im.get("natureza_area"): st.session_state["natureza_area"] = im["natureza_area"]
    if im.get("area_ha"):       st.session_state["area_ha"]       = float(im["area_ha"])
    if im.get("perimetro_m"):   st.session_state["perimetro_m"]   = float(im["perimetro_m"])

    if pr.get("nome"): st.session_state["prop_nome"] = pr["nome"]
    if pr.get("cpf"):  st.session_state["prop_cpf"]  = pr["cpf"]

    # REGRA OBRIGATÓRIA DA SKILL: respeitar a escolha do usuário sobre o RT
    if usar_ladu_como_rt:
        st.session_state["rt_nome"]     = RT_LADU["nome"]
        st.session_state["rt_formacao"] = RT_LADU["formacao"]
        st.session_state["rt_crea"]     = RT_LADU["crea"]
        st.session_state["rt_credenc"]  = RT_LADU["credenciado_codigo"]
        # ART deve ser informada por projeto — não sobrescrevemos do PDF
        st.session_state["rt_art"]      = RT_LADU["art"]
    else:
        if rt.get("nome"):               st.session_state["rt_nome"]     = rt["nome"]
        if rt.get("formacao"):           st.session_state["rt_formacao"] = rt["formacao"]
        if rt.get("crea"):               st.session_state["rt_crea"]     = rt["crea"]
        if rt.get("credenciado_codigo"): st.session_state["rt_credenc"]  = rt["credenciado_codigo"]
        if rt.get("art"):                st.session_state["rt_art"]      = rt["art"]

    st.session_state["usar_sigef"] = bool(sg.get("incluir", False))
    if sg.get("codigo"): st.session_state["sigef_cod"]  = sg["codigo"]
    if sg.get("data"):   st.session_state["sigef_data"] = sg["data"]


# ============================================================
# TABS principais
# ============================================================

tab_pdf, tab_vert, tab_memorial, tab_tabela = st.tabs([
    "📥 Importar PDF SIGEF",
    "📍 Vértices",
    "📄 Memorial Descritivo",
    "📊 Tabela de Coordenadas",
])

# ============================================================
# TAB 0 — IMPORTAR PDF SIGEF
# ============================================================

with tab_pdf:
    st.subheader("Importar Memorial SIGEF (PDF)")
    st.markdown(
        "Upload do PDF do memorial descritivo certificado pelo SIGEF. "
        "O app extrai automaticamente cabeçalho, vértices, azimutes, distâncias e "
        "confrontantes — gerando o **memorial corrido no padrão LADU**."
    )

    pdf_file = st.file_uploader(
        "Arraste o PDF aqui ou clique para selecionar",
        type=["pdf"],
        key="pdf_uploader",
    )

    if pdf_file is not None:
        # Salva temporariamente e parseia
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(pdf_file.read())
                tmp_path = tmp.name

            with st.spinner("Extraindo dados do PDF..."):
                resultado = parse_pdf_sigef(tmp_path)
            st.session_state["pdf_parsed"] = resultado
            Path(tmp_path).unlink(missing_ok=True)
            st.success(f"PDF processado: {len(resultado['vertices'])} vértices identificados.")
        except Exception as e:
            st.error(f"Erro ao processar PDF: {e}")
            st.session_state["pdf_parsed"] = None

    parsed = st.session_state.get("pdf_parsed")

    if parsed:
        meta_ext = parsed["meta"]
        verts_ext = parsed["vertices"]

        # ===== PREVIEW DE DADOS EXTRAÍDOS =====
        st.markdown("#### Dados extraídos")

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**🏠 Imóvel**")
            im = meta_ext["imovel"]
            st.markdown(
                f"""
- Denominação: `{im['denominacao'] or '—'}`
- Matrícula: `{im['matricula'] or '—'}`
- CNS Cartório: `{im['cns_cartorio'] or '—'}`
- Comarca/UF: `{im['comarca']} - {im['uf']}`
- CCIR: `{im['ccir'] or '—'}`
- Município: `{im['municipio'] or '—'}`
- Natureza: `{im['natureza_area']}`
- Área: `{fmt_br_area(im['area_ha'])} ha`
- Perímetro: `{fmt_br_distancia(im['perimetro_m'])} m`
"""
            )

            sg = meta_ext["certificacao_sigef"]
            if sg["incluir"]:
                st.markdown(
                    f"""
**🔏 SIGEF**
- Código: `{sg['codigo']}`
- Data: `{sg['data']}`
"""
                )

        with col_b:
            st.markdown("**👤 Proprietário**")
            pr = meta_ext["proprietario"]
            st.markdown(
                f"""
- Nome: `{pr['nome'] or '—'}`
- CPF: `{pr['cpf'] or '—'}`
"""
            )
            st.markdown("**📐 RT identificado no PDF**")
            rt = meta_ext["rt"]
            st.markdown(
                f"""
- Nome: `{rt['nome'] or '—'}`
- Formação: `{rt['formacao']}`
- CREA: `{rt['crea'] or '—'}`
- Credenciado: `{rt['credenciado_codigo'] or '—'}`
- ART: `{rt['art'] or '—'}`
"""
            )

        st.divider()

        # ===== REGRA OBRIGATÓRIA DA SKILL: PERGUNTA SOBRE O RT =====
        rt_original_nome = meta_ext["rt"].get("nome") or "(não identificado)"
        rt_original_cred = meta_ext["rt"].get("credenciado_codigo") or "—"

        st.markdown(
            f"""
<div class="rt-warn">
<h4>⚠️ Pergunta obrigatória — Responsável Técnico do memorial final</h4>
<p>Quem deve constar como <strong>RT do memorial gerado</strong>?</p>
</div>
""",
            unsafe_allow_html=True,
        )

        rt_choice = st.radio(
            "Selecione:",
            options=[
                f"🅰️ Manter o RT original do documento — **{rt_original_nome}** (credenciado {rt_original_cred})",
                f"🅱️ Você, **{RT_LADU['nome']}** (credenciado {RT_LADU['credenciado_codigo']})",
            ],
            index=0,
            label_visibility="collapsed",
            key="rt_radio_choice",
        )
        usar_ladu = rt_choice.startswith("🅱️")

        st.divider()

        # ===== VÉRTICES PREVIEW =====
        st.markdown(f"#### Vértices extraídos ({len(verts_ext)})")

        df_preview = pd.DataFrame(verts_ext)
        if not df_preview.empty:
            st.dataframe(
                df_preview.head(10),
                use_container_width=True,
                height=320,
            )
            if len(verts_ext) > 10:
                st.caption(f"Exibindo 10 de {len(verts_ext)} vértices. Após aplicar, edite na aba **📍 Vértices**.")

        st.divider()

        # ===== BOTÃO APLICAR =====
        col_aplica1, col_aplica2 = st.columns([2, 1])
        with col_aplica1:
            st.info(
                "Ao aplicar, os dados extraídos vão para o sidebar (configuração) "
                "e para a tabela de vértices. Você poderá ajustar antes de gerar o memorial."
            )
        with col_aplica2:
            if st.button("✅ Aplicar dados ao app", type="primary", use_container_width=True):
                aplicar_meta_extraido(meta_ext, usar_ladu_como_rt=usar_ladu)
                st.session_state["df_vertices"] = pd.DataFrame(verts_ext)
                st.success("Dados aplicados! Vá para a aba **📄 Memorial Descritivo** para baixar o DOCX.")
                st.rerun()

        # Debug — texto extraído e diagnóstico
        with st.expander("🔍 Diagnóstico / texto extraído do PDF"):
            tab_bruto, tab_norm, tab_diag = st.tabs(["Texto bruto", "Texto normalizado", "Diagnóstico"])
            with tab_bruto:
                st.caption("Texto como o pdfplumber extraiu do PDF (antes de qualquer tratamento).")
                st.text_area("Bruto", parsed["texto_bruto"], height=300, label_visibility="collapsed")
            with tab_norm:
                st.caption("Texto após normalização de encoding (°, ', \", espaços). É sobre este texto que os regex operam.")
                st.text_area("Norm", parsed["texto_normalizado"], height=300, label_visibility="collapsed")
            with tab_diag:
                tn = parsed["texto_normalizado"]
                n_vert = len(list(VERTEX_RE.finditer(tn)))
                n_leg  = len(list(LEG_RE.finditer(tn)))
                tem_inicio = bool(_re.search(r"Inicia-se\s+a\s+descri[cç][aã]o", tn, _re.IGNORECASE))
                tem_fecha  = bool(_re.search(r"fechando\s+assim", tn, _re.IGNORECASE))
                st.markdown(f"""
| Verificação | Resultado |
|---|---|
| Phrase "Inicia-se a descrição" encontrada | {'✅ sim' if tem_inicio else '❌ NÃO'} |
| Phrase "fechando assim" encontrada | {'✅ sim' if tem_fecha else '❌ NÃO'} |
| Correspondências de vértice (regex) | **{n_vert}** |
| Correspondências de leg (azimute/distância) | **{n_leg}** |
| Vértices retornados após parse | **{len(verts_ext)}** |
""")
                if n_vert == 0:
                    st.warning(
                        "Nenhum vértice encontrado. Verifique no texto normalizado se o formato das "
                        "coordenadas está no padrão `9°11'50,695\" S`. Casos não suportados: grau "
                        "representado pela letra `o` minúscula (ex: `9o11'`)."
                    )
                st.markdown("**Primeiros 500 caracteres do texto normalizado:**")
                st.code(tn[:500])

    else:
        st.info("Faça upload de um PDF de memorial SIGEF para começar.")
        with st.expander("ℹ️ Formato esperado"):
            st.markdown(
                """
O parser reconhece o memorial descritivo SIGEF em **prosa única** (padrão LADU),
com cabeçalho rotulado de 18 campos e descrição da parcela seguindo o formato:

> Inicia-se a descrição deste perímetro no vértice **X**, de coordenadas geodésicas
> latitude **Y S** e longitude **Z W**; deste, segue confrontando com **NOME**
> (Matrícula M, CNS C), com azimute geodésico de A e distância de D m, até o
> vértice **W**...

Extrai automaticamente:
- 18 campos do cabeçalho (denominação, proprietário, CPF, matrícula, CNS, comarca, UF,
  CCIR, município, natureza, área, perímetro, RT, formação, CREA, credenciado, ART)
- Bloco SIGEF (hash + data) quando presente
- Todos os vértices com lat/long em GMS, azimute, distância
- Trocas de confrontante (incluindo matrícula e CNS quando explicitados)
"""
            )


# ============================================================
# TAB 1 — VÉRTICES
# ============================================================

with tab_vert:
    st.subheader("Entrada de Vértices")

    col_up, col_dl = st.columns([3, 1])
    with col_dl:
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
            "Faça upload do CSV/XLSX de vértices ou use o editor abaixo:",
            type=["csv", "xlsx", "xls"],
            key="csv_uploader",
        )

    if uploaded_csv is not None:
        try:
            if uploaded_csv.name.endswith((".xlsx", ".xls")):
                df_vert = pd.read_excel(uploaded_csv, dtype=str)
            else:
                df_vert = pd.read_csv(uploaded_csv, dtype=str, sep=None, engine="python", encoding="utf-8-sig")
            df_vert.columns = [c.strip().lower() for c in df_vert.columns]
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

    st.markdown("**Editor de vértices** (edite diretamente na tabela):")
    df_editado = st.data_editor(
        st.session_state["df_vertices"],
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "ordem":          st.column_config.NumberColumn("Ordem", min_value=1, step=1),
            "vertice":        st.column_config.TextColumn("Vértice"),
            "lat":            st.column_config.TextColumn("Latitude (GMS)"),
            "long":           st.column_config.TextColumn("Longitude (GMS)"),
            "azimute":        st.column_config.TextColumn("Azimute"),
            "distancia":      st.column_config.NumberColumn("Distância (m)", format="%.2f"),
            "confrontante":   st.column_config.TextColumn("Confrontante"),
            "matricula_conf": st.column_config.TextColumn("Matrícula conf."),
            "cns_conf":       st.column_config.TextColumn("CNS conf."),
        },
        key="editor_vertices",
    )
    st.session_state["df_vertices"] = df_editado

    df_val = df_editado.dropna(subset=["vertice", "lat", "long"])
    n_total = len(df_editado)
    n_ok = len(df_val)
    st.markdown(
        f'<span class="badge-ok">✔ {n_ok} vértices válidos</span>'
        + (f' <span class="badge-err">⚠ {n_total - n_ok} sem coordenadas</span>' if n_ok < n_total else ""),
        unsafe_allow_html=True,
    )

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
        st.info("Carregue os vértices na aba **📍 Vértices** (ou importe um PDF) para gerar o memorial.")
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
            html_preview = texto_md
            html_preview = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html_preview)
            html_preview = _re.sub(r"^# (.+)$", r"<h1>\1</h1>", html_preview, flags=_re.MULTILINE)
            html_preview = html_preview.replace("\n\n", "</p><p>").replace("\n", "<br>")
            html_preview = f"<p>{html_preview}</p>"

            st.markdown(
                f'<div class="memorial-box">{html_preview}</div>',
                unsafe_allow_html=True,
            )

            st.divider()

            # Padrão da skill: SAÍDA APENAS EM DOCX (regra obrigatória).
            # Markdown disponível como rascunho secundário.
            col_dl1, col_dl2 = st.columns([2, 1])

            with col_dl1:
                try:
                    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
                        tmp_path = tmp.name
                    renderizar_docx(df_mem_clean, meta, tmp_path)
                    docx_bytes = Path(tmp_path).read_bytes()
                    Path(tmp_path).unlink(missing_ok=True)

                    st.download_button(
                        "⬇️ Baixar Memorial Descritivo (.docx) — entregável final",
                        data=docx_bytes,
                        file_name=f"memorial_{st.session_state['denominacao'].replace(' ', '_')}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        type="primary",
                        use_container_width=True,
                    )
                except Exception as e_docx:
                    st.error(f"Erro ao gerar DOCX: {e_docx}")

            with col_dl2:
                st.download_button(
                    "⬇️ Rascunho (.md)",
                    data=texto_md.encode("utf-8"),
                    file_name="memorial_rascunho.md",
                    mime="text/markdown",
                    use_container_width=True,
                )

            st.caption(
                "📌 Conforme padrão LADU: **entregável final é DOCX**. "
                "PDF apenas quando solicitado explicitamente."
            )

            # Exportar meta.json
            st.divider()
            with st.expander("⚙️ Exportar configuração atual (meta.json)"):
                meta_json_str = json.dumps(meta, ensure_ascii=False, indent=2)
                st.code(meta_json_str, language="json")
                st.download_button(
                    "⬇️ meta.json",
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

        meta_tab = build_meta()
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Vértices", len(df_saida))
        col_m2.metric("Área", f"{fmt_br_area(meta_tab['imovel']['area_ha'])} ha")
        col_m3.metric("Perímetro", f"{fmt_br_distancia(meta_tab['imovel']['perimetro_m'])} m")

        st.dataframe(df_saida, use_container_width=True, height=420)

        st.divider()

        col_csv, col_xlsx = st.columns(2)

        csv_bytes = df_saida.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
        with col_csv:
            st.download_button(
                "⬇️ Baixar Tabela (.csv)",
                data=csv_bytes,
                file_name="tabela_coordenadas.csv",
                mime="text/csv",
                use_container_width=True,
            )

        with col_xlsx:
            try:
                buf_xl = io.BytesIO()
                with pd.ExcelWriter(buf_xl, engine="openpyxl") as writer:
                    df_saida.to_excel(writer, index=False, sheet_name="Coordenadas")
                    df_tab.to_excel(writer, index=False, sheet_name="Dados Brutos")

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

        with st.expander("Ver dados brutos (CSV original)"):
            st.dataframe(df_tab, use_container_width=True)
