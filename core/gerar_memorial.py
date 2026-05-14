"""
gerar_memorial.py — Gera memorial descritivo no padrão LADU (Engenheiro
Gustavo Henrique Cabral de Melo), apropriado tanto para imóveis rurais
(certificação SIGEF / retificação / matrícula) quanto urbanos
(NBR 17047 / REURB).

O padrão do memorial:
  - Cabeçalho com 19 campos rotulados.
  - Descrição corrida em prosa única, no padrão SIGEF/INCRA, com troca de
    confrontante detectada automaticamente.
  - Bloco de certificação SIGEF (opcional — só se o imóvel já estiver
    certificado).
  - Bloco duplo de assinaturas (RT + Proprietário).

Saídas: .md ou .docx. Para .docx, preserva negrito em vértices,
coordenadas e confrontantes.

Uso:
  python gerar_memorial.py \\
        --vertices vertices.csv \\
        --meta meta.json \\
        --saida memorial.docx

Estrutura do CSV de vértices (colunas obrigatórias marcadas com *):
  *ordem            inteiro 1,2,3... define o sentido de percurso
  *vertice          código CCC-T-NNNN (string)
  *lat              latitude geodésica em formato `9°11'50,695"` (sem hemisfério)
                    ou decimal negativo
  *long             longitude geodésica em formato `35°22'10,663"` (sem hemisfério)
                    ou decimal negativo
  *azimute          azimute geodésico para o próximo vértice, formato `138°24'`
                    ou decimal (ex.: 138.4)
  *distancia        distância em metros (decimal com ponto, ex.: 304.44)
  *confrontante     nome do confrontante (string)
   matricula_conf   matrícula do imóvel confrontante (opcional)
   cns_conf         CNS do cartório do confrontante (opcional)

Estrutura do meta.json — ver `templates/exemplo_meta.json`.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
RT_PADRAO_PATH = SCRIPT_DIR.parent / "dados" / "dados_rt_padrao.json"


# ============================================================
# Formatação de números (padrão brasileiro)
# ============================================================

def fmt_br_distancia(d: float) -> str:
    """Formata distância em metros com 2 decimais, padrão BR (vírgula
    decimal, ponto de milhar para valores >= 1000)."""
    return f"{d:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_br_area(ha: float) -> str:
    """Formata área em hectares com 4 decimais, padrão BR."""
    return f"{ha:,.4f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ============================================================
# Parsing e formatação de coordenadas
# ============================================================

GMS_RE = re.compile(
    r"""^\s*
    (?P<sinal>[-+]?)
    (?P<g>\d+)\s*[°dD]\s*
    (?:(?P<m>\d+)\s*['mM]\s*)?
    (?:(?P<s>\d+(?:[.,]\d+)?)\s*["sS]?\s*)?
    \s*(?P<hemi>[NSEWOnsew])?\s*$""",
    re.VERBOSE,
)


def gms_para_decimal(s) -> float:
    """Converte string GMS para grau decimal. Aceita também número."""
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip().replace(",", ".")
    try:
        return float(s)
    except ValueError:
        pass
    m = GMS_RE.match(s)
    if not m:
        raise ValueError(f"Formato de coordenada inválido: {s!r}")
    g = int(m.group("g"))
    mn = int(m.group("m") or 0)
    sc = float(m.group("s") or 0)
    sinal = -1.0 if m.group("sinal") == "-" else 1.0
    hemi = (m.group("hemi") or "").upper()
    if hemi in ("S", "W", "O"):
        sinal = -1.0
    return sinal * (g + mn / 60.0 + sc / 3600.0)


def decimal_para_gms_coord(d: float, decimais_seg: int = 3) -> str:
    """Converte decimal para `G°MM'SS,sss\"` (padrão de coordenada SIGEF,
    sem hemisfério; vírgula decimal). Sempre devolve em valor absoluto."""
    d = abs(d)
    g = int(d)
    mn_full = (d - g) * 60.0
    mn = int(mn_full)
    sc = (mn_full - mn) * 60.0
    sc_str = f"{sc:0{3 + decimais_seg}.{decimais_seg}f}".replace(".", ",")
    return f"{g}°{mn:02d}'{sc_str}\""


def normalizar_coordenada(v) -> str:
    """Recebe coordenada (string GMS ou decimal) e devolve `G°MM'SS,sss\"`."""
    if isinstance(v, str) and ("°" in v or "'" in v):
        d = gms_para_decimal(v)
    else:
        d = float(v)
    return decimal_para_gms_coord(d, decimais_seg=3)


# ============================================================
# Azimutes
# ============================================================

def normalizar_azimute(v) -> str:
    """Recebe azimute (string `GG°MM'` ou decimal) e devolve `GG°MM'`
    (graus e minutos, sem segundos — padrão SIGEF)."""
    if isinstance(v, str) and "°" in v:
        m = re.match(r"\s*(\d+)\s*°\s*(\d+)?\s*'?", v)
        if m:
            g = int(m.group(1))
            mn = int(m.group(2) or 0)
            return f"{g:02d}°{mn:02d}'"
    d = float(v)
    if d < 0:
        d += 360.0
    g = int(d)
    mn = int(round((d - g) * 60.0))
    if mn >= 60:
        mn = 0
        g += 1
    return f"{g:02d}°{mn:02d}'"


# ============================================================
# Carregamento de dados
# ============================================================

def carregar_vertices(path: str) -> pd.DataFrame:
    """Carrega vértices de CSV, TSV ou XLSX. Detecta separador automaticamente.

    Aceita as duas formas de nomenclatura de colunas:
      - Padrão antigo: `lat, long`
      - Padrão SIGEF (preferido): `latitude, longitude`
    """
    p = Path(path)
    suf = p.suffix.lower()
    if suf == ".xlsx":
        df = pd.read_excel(path, dtype=str)
    else:
        # detecta separador automaticamente (tab, ;, ,)
        df = pd.read_csv(path, dtype=str, sep=None, engine='python', encoding='utf-8-sig')

    df.columns = [c.strip().lower() for c in df.columns]

    # Normalizar nomes de colunas: aceitar latitude/longitude OU lat/long
    rename_map = {}
    if "latitude" in df.columns and "lat" not in df.columns:
        rename_map["latitude"] = "lat"
    if "longitude" in df.columns and "long" not in df.columns:
        rename_map["longitude"] = "long"
    if "matricula_conf" not in df.columns:
        for alt in ["matricula_confrontante", "matricula"]:
            if alt in df.columns:
                rename_map[alt] = "matricula_conf"
                break
    if "cns_conf" not in df.columns:
        for alt in ["cns_confrontante", "cns"]:
            if alt in df.columns:
                rename_map[alt] = "cns_conf"
                break
    if rename_map:
        df = df.rename(columns=rename_map)

    if "ordem" in df.columns:
        df["ordem"] = df["ordem"].astype(int)
        df = df.sort_values("ordem").reset_index(drop=True)

    # distância pode vir com vírgula decimal (padrão BR)
    df["distancia"] = df["distancia"].astype(str).str.replace(",", ".").astype(float)
    return df


def carregar_meta(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def mesclar_rt_padrao(meta: dict) -> dict:
    """Se meta.rt estiver ausente, carrega dados padrão (Gustavo)."""
    rt_atual = meta.get("rt", {}) or {}
    if rt_atual.get("nome"):
        return meta
    padrao_path = RT_PADRAO_PATH
    if padrao_path.exists():
        padrao = json.loads(padrao_path.read_text(encoding="utf-8"))
        padrao_limpo = {k: v for k, v in padrao.items() if not k.startswith("_")}
        if "art" not in rt_atual and "art_padrao" in padrao_limpo:
            padrao_limpo["art"] = padrao_limpo.pop("art_padrao")
        rt_mesclado = {**padrao_limpo, **rt_atual}
        meta["rt"] = rt_mesclado
    return meta


# ============================================================
# Construção da prosa
# ============================================================

def qualificacao_confrontante(row) -> str:
    """Devolve ` (Matrícula X, CNS Y)` se houver, ou string vazia."""
    matricula = row.get("matricula_conf", "")
    cns = row.get("cns_conf", "")
    matricula = str(matricula).strip() if matricula is not None else ""
    cns = str(cns).strip() if cns is not None else ""
    if matricula and matricula.lower() != "nan":
        s = f" (Matrícula {matricula}"
        if cns and cns.lower() != "nan":
            s += f", CNS {cns}"
        s += ")"
        return s
    return ""


def construir_prosa(df: pd.DataFrame) -> list[dict]:
    """Constrói tokens [{'texto':..., 'negrito':bool}, ...] da prosa."""
    n = len(df)
    tokens: list[dict] = []

    def add(texto, negrito=False):
        if texto:
            tokens.append({"texto": texto, "negrito": negrito})

    primeiro = df.iloc[0]
    add("Inicia-se a descrição deste perímetro no vértice ")
    add(primeiro["vertice"], negrito=True)
    add(", de coordenadas geodésicas latitude ")
    add(f"{normalizar_coordenada(primeiro['lat'])} S", negrito=True)
    add(" e longitude ")
    add(f"{normalizar_coordenada(primeiro['long'])} W", negrito=True)
    add("; deste, segue confrontando com ")
    add(primeiro["confrontante"], negrito=True)
    add(qualificacao_confrontante(primeiro))
    add(", com azimute geodésico de ")
    add(normalizar_azimute(primeiro["azimute"]))
    add(" e distância de ")
    add(fmt_br_distancia(primeiro["distancia"]))
    add(" m, até o vértice ")

    confrontante_anterior = primeiro["confrontante"]

    for i in range(1, n):
        atual = df.iloc[i]
        add(atual["vertice"], negrito=True)
        add(", de coordenadas geodésicas latitude ")
        add(f"{normalizar_coordenada(atual['lat'])} S", negrito=True)
        add(" e longitude ")
        add(f"{normalizar_coordenada(atual['long'])} W", negrito=True)
        add("; ")

        confrontante_atual = atual["confrontante"]

        if i < n - 1:
            if confrontante_atual != confrontante_anterior:
                add("Deste, segue confrontando agora com ")
                add(confrontante_atual, negrito=True)
                add(qualificacao_confrontante(atual))
                add(", com azimute geodésico de ")
            else:
                add("Deste, segue com azimute geodésico de ")
            add(normalizar_azimute(atual["azimute"]))
            add(" e distância de ")
            add(fmt_br_distancia(atual["distancia"]))
            add(" m, até o vértice ")
            confrontante_anterior = confrontante_atual
        else:
            # último vértice: fecha no primeiro
            if confrontante_atual != confrontante_anterior:
                add("Deste, segue confrontando agora com ")
                add(confrontante_atual, negrito=True)
                add(qualificacao_confrontante(atual))
                add(", com azimute geodésico de ")
            else:
                add("Deste, segue com azimute geodésico de ")
            add(normalizar_azimute(atual["azimute"]))
            add(" e distância de ")
            add(fmt_br_distancia(atual["distancia"]))
            add(" m, até o vértice ")
            add(primeiro["vertice"], negrito=True)
            add(", ponto inicial da descrição deste perímetro")

    return tokens


# ============================================================
# Renderização — Markdown
# ============================================================

def renderizar_markdown(df: pd.DataFrame, meta: dict) -> str:
    im = meta["imovel"]
    pr = meta["proprietario"]
    rt = meta["rt"]
    sigef = meta.get("certificacao_sigef", {})
    incluir_sigef = bool(sigef and sigef.get("incluir", False))

    area_str = fmt_br_area(im["area_ha"])
    perim_str = fmt_br_distancia(im["perimetro_m"])

    L = []
    L.append("# MEMORIAL DESCRITIVO\n")
    L.append(f"**Denominação:** {im['denominacao']}\n")
    L.append(f"**Proprietário(a):** {pr['nome']}\n")
    L.append(f"**CPF:** {pr['cpf']}\n")
    L.append(f"**Matrícula do imóvel:** {im['matricula']}\n")
    L.append(f"**Cartório de Registro de Imóveis:** ({im['cns_cartorio']}) {im['comarca']} - {im['uf']}\n")
    L.append(f"**Código INCRA/SNCR:** {im['ccir']}\n")
    L.append(f"**Município/UF:** {im['municipio']} - {im['uf']}\n")
    L.append(f"**Natureza da Área:** {im.get('natureza_area', 'Particular')}\n")
    L.append(f"**Área (Sistema Geodésico Local):** {area_str} ha\n")
    L.append(f"**Perímetro:** {perim_str} m\n")
    L.append(f"**Sistema Geodésico de Referência:** SIRGAS 2000\n")
    L.append(f"**Coordenadas:** Latitude, longitude e altitude geodésicas\n")
    L.append(f"**Azimutes:** Azimutes geodésicos\n")
    L.append(f"**Responsável Técnico(a):** {rt['nome']}\n")
    L.append(f"**Formação:** {rt.get('formacao', 'Engenheiro Agrimensor')}\n")
    L.append(f"**Conselho Profissional:** {rt['crea']}\n")
    L.append(f"**Código de Credenciamento:** {rt['credenciado_codigo']}\n")
    L.append(f"**Documento de RT:** {rt['art']}\n")

    L.append("\n**DESCRIÇÃO DA PARCELA**\n")

    tokens = construir_prosa(df)
    prosa = ""
    for t in tokens:
        if t["negrito"]:
            prosa += f"**{t['texto']}**"
        else:
            prosa += t["texto"]
    prosa += f", fechando assim a poligonal acima descrita com área de {area_str} ha e perímetro de {perim_str} m."
    L.append(prosa + "\n")

    L.append(
        "\nTodas as coordenadas aqui descritas estão georreferenciadas ao Sistema "
        "Geodésico Brasileiro (SIRGAS 2000) e encontram-se representadas no Sistema "
        "Geodésico Local.\n"
    )

    if incluir_sigef:
        L.append(f"\n**CERTIFICAÇÃO SIGEF:** {sigef.get('codigo', '')}\n")
        L.append(f"**Data da Certificação:** {sigef.get('data', '')}\n")
        L.append(
            "\nEm atendimento ao § 5º do art. 176 da Lei nº 6.015/73, certifica-se "
            "que a poligonal objeto deste memorial descritivo não se sobrepõe, nesta "
            "data, a nenhuma outra poligonal constante do cadastro georreferenciado "
            "do INCRA.\n"
        )

    L.append("\n**Responsável Técnico:**\n\n_____________________________________________\n")
    L.append(f"\n**{rt['nome']}**\n\nEngenheiro Agrimensor\n\nCREA nº {rt['crea']}\n\nCredenciado(a) INCRA: {rt['credenciado_codigo']}\n")
    L.append("\n**Proprietário:**\n\n_____________________________________________\n")
    L.append(f"\n**{pr['nome']}**\n\nCPF: {pr['cpf']}\n")

    return "\n".join(L)


# ============================================================
# Renderização — DOCX
# ============================================================

def renderizar_docx(df: pd.DataFrame, meta: dict, saida: str) -> None:
    try:
        from docx import Document
        from docx.shared import Pt, Cm
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except ImportError:
        raise RuntimeError("python-docx não instalado. `pip install python-docx`.")

    im = meta["imovel"]
    pr = meta["proprietario"]
    rt = meta["rt"]
    sigef = meta.get("certificacao_sigef", {})
    incluir_sigef = bool(sigef and sigef.get("incluir", False))

    area_str = fmt_br_area(im["area_ha"])
    perim_str = fmt_br_distancia(im["perimetro_m"])

    doc = Document()

    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    for section in doc.sections:
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)
        section.left_margin = Cm(3.0)
        section.right_margin = Cm(2.0)

    # Título
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("MEMORIAL DESCRITIVO")
    r.bold = True
    r.font.size = Pt(14)

    doc.add_paragraph("")

    campos = [
        ("Denominação:", im["denominacao"]),
        ("Proprietário(a):", pr["nome"]),
        ("CPF:", pr["cpf"]),
        ("Matrícula do imóvel:", str(im["matricula"])),
        ("Cartório de Registro de Imóveis:", f"({im['cns_cartorio']}) {im['comarca']} - {im['uf']}"),
        ("Código INCRA/SNCR:", str(im["ccir"])),
        ("Município/UF:", f"{im['municipio']} - {im['uf']}"),
        ("Natureza da Área:", im.get("natureza_area", "Particular")),
        ("Área (Sistema Geodésico Local):", f"{area_str} ha"),
        ("Perímetro:", f"{perim_str} m"),
        ("Sistema Geodésico de Referência:", "SIRGAS 2000"),
        ("Coordenadas:", "Latitude, longitude e altitude geodésicas"),
        ("Azimutes:", "Azimutes geodésicos"),
        ("Responsável Técnico(a):", rt["nome"]),
        ("Formação:", rt.get("formacao", "Engenheiro Agrimensor")),
        ("Conselho Profissional:", rt["crea"]),
        ("Código de Credenciamento:", rt["credenciado_codigo"]),
        ("Documento de RT:", rt["art"]),
    ]
    for label, valor in campos:
        p = doc.add_paragraph()
        r1 = p.add_run(label + " ")
        r1.bold = True
        p.add_run(valor)

    doc.add_paragraph("")

    p = doc.add_paragraph()
    r = p.add_run("DESCRIÇÃO DA PARCELA")
    r.bold = True

    p_prosa = doc.add_paragraph()
    p_prosa.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    tokens = construir_prosa(df)
    for t in tokens:
        run = p_prosa.add_run(t["texto"])
        if t["negrito"]:
            run.bold = True
    p_prosa.add_run(
        f", fechando assim a poligonal acima descrita com área de {area_str} ha "
        f"e perímetro de {perim_str} m."
    )

    doc.add_paragraph("")
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.add_run(
        "Todas as coordenadas aqui descritas estão georreferenciadas ao "
        "Sistema Geodésico Brasileiro (SIRGAS 2000) e encontram-se representadas "
        "no Sistema Geodésico Local."
    )

    if incluir_sigef:
        doc.add_paragraph("")
        p = doc.add_paragraph()
        r1 = p.add_run("CERTIFICAÇÃO SIGEF: ")
        r1.bold = True
        p.add_run(sigef.get("codigo", ""))

        p = doc.add_paragraph()
        r1 = p.add_run("Data da Certificação: ")
        r1.bold = True
        p.add_run(sigef.get("data", ""))

        doc.add_paragraph("")
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        p.add_run(
            "Em atendimento ao § 5º do art. 176 da Lei nº 6.015/73, certifica-se "
            "que a poligonal objeto deste memorial descritivo não se sobrepõe, "
            "nesta data, a nenhuma outra poligonal constante do cadastro "
            "georreferenciado do INCRA."
        )

    # Assinaturas
    doc.add_paragraph("")
    p = doc.add_paragraph()
    r = p.add_run("Responsável Técnico:")
    r.bold = True

    doc.add_paragraph("")
    p = doc.add_paragraph("_____________________________________________")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(rt["nome"])
    r.bold = True

    p = doc.add_paragraph(rt.get("formacao", "Engenheiro Agrimensor"))
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    p = doc.add_paragraph(f"CREA nº {rt['crea']}")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    p = doc.add_paragraph(f"Credenciado(a) INCRA: {rt['credenciado_codigo']}")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph("")
    p = doc.add_paragraph()
    r = p.add_run("Proprietário:")
    r.bold = True

    doc.add_paragraph("")
    p = doc.add_paragraph("_____________________________________________")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(pr["nome"])
    r.bold = True

    p = doc.add_paragraph(f"CPF: {pr['cpf']}")
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.save(saida)


# ============================================================
# Main
# ============================================================

def main():
    p = argparse.ArgumentParser(description="Gera memorial descritivo no padrão LADU.")
    p.add_argument("--vertices", required=True)
    p.add_argument("--meta", required=True)
    p.add_argument("--saida", required=True)
    args = p.parse_args()

    df = carregar_vertices(args.vertices)
    meta = carregar_meta(args.meta)
    meta = mesclar_rt_padrao(meta)

    if args.saida.endswith(".docx"):
        renderizar_docx(df, meta, args.saida)
    else:
        texto = renderizar_markdown(df, meta)
        Path(args.saida).write_text(texto, encoding="utf-8")

    print(f"Memorial gerado em: {args.saida}")


if __name__ == "__main__":
    main()
