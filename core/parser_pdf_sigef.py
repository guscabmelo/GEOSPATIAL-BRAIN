"""
parser_pdf_sigef.py - v2 - Extrai dados de um memorial descritivo SIGEF em PDF.

Robusto a variacoes de encoding que pdfplumber pode produzir:
  - ordinal (U+00BA) vs grau (U+00B0)
  - aspas curvas como apóstrofe ou segundo
  - palavras com/sem acento (vertice/vertice, distancia/distancia, etc.)
  - simbolo de segundos ausente
  - virgula após codigo do vertice ausente
"""

from __future__ import annotations

import re
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


# ============================================================
# Regex - vertices na prosa
# ============================================================

VERTEX_RE = re.compile(
    r"v[e\xe9]rtices?\s+"
    r"([A-Za-z][A-Za-z0-9\-\.]*)"
    r"\s*[,;]?\s*"
    r"(?:de\s+)?coordenadas?\s+geod[e\xe9]sicas?\s+"
    r"latitude\s+(\d+[\xb0\xba]\s*\d+['’‘′]\s*[\d.,]+[\"'”″]?\s*)"
    r"\s*[Ss]\s*"
    r"e\s+longitude\s+"
    r"(\d+[\xb0\xba]\s*\d+['’‘′]\s*[\d.,]+[\"'”″]?\s*)"
    r"\s*[Ww]",
    re.IGNORECASE,
)

LEG_RE = re.compile(
    r"(?:confrontando\s+(?:agora\s+)?com\s+"
    r"(.+?)"
    r"(?:\s*\(([^)]*)\))?"
    r"\s*,\s+)?"
    r"com\s+azimute\s+geod[e\xe9]sico\s+de\s+"
    r"(\d+[\xb0\xba]\s*\d+['’‘′])"
    r"\s+"
    r"e\s+dist[a\xe2]ncia\s+de\s+"
    r"([\d.,]+)\s*m",
    re.IGNORECASE | re.DOTALL,
)

MATRICULA_QUAL_RE = re.compile(r"Matr[i\xed]cula\s+([^,)]+)", re.IGNORECASE)
CNS_QUAL_RE = re.compile(r"CNS\s+([^,)]+)", re.IGNORECASE)


# ============================================================
# Cabecalho - padrao SIGEF (labels maiusculas ou mistas)
# ============================================================

CABECALHO_PATTERNS = {
    "denominacao":    r"denomina[c\xe7][a\xe3]o\s*:\s*(.+?)\s*(?=propriet[a\xe1]|$)",
    "proprietario":   r"propriet[a\xe1]rio\(?[aA]?\)?\s*:\s*(.+?)\s*(?=CPF|$)",
    "cpf":            r"CPF\s*:\s*([\d.\-/]+)",
    "matricula":      r"matr[i\xed]cula\s+do\s+im[o\xf3]vel\s*:\s*(.+?)\s*(?=cart[o\xf3]rio|$)",
    "cartorio_raw":   r"cart[o\xf3]rio\s+de\s+registro\s+de\s+im[o\xf3]veis\s*:\s*(.+?)\s*(?=c[o\xf3]digo\s+INCRA|$)",
    "ccir":           r"c[o\xf3]digo\s+INCRA[/]SNCR\s*:\s*([\d/.\-]+)",
    "municipio_uf":   r"munic[i\xed]pio[/]UF\s*:\s*(.+?)\s*(?=natureza|$)",
    "natureza_area":  r"natureza\s+da\s+[a\xe1]rea\s*:\s*(.+?)\s*(?=[a\xe1]rea|$)",
    "area_ha":        r"[a\xe1]rea\s*(?:total\s*)?:\s*([\d.,]+)\s*ha",
    "perimetro_m":    r"per[i\xed]metro\s*:\s*([\d.,]+)\s*m",
    "rt_nome":        r"respons[a\xe1]vel\s+t[e\xe9]cnico\(?[aA]?\)?\s*:\s*(.+?)\s*(?=forma[c\xe7][a\xe3]o|$)",
    "rt_formacao":    r"forma[c\xe7][a\xe3]o\s*:\s*(.+?)\s*(?=conselho\s+profissional|$)",
    "rt_crea":        r"conselho\s+profissional\s*:\s*(.+?)\s*(?=c[o\xf3]digo\s+de\s+credenciamento|$)",
    "rt_credenciado": r"c[o\xf3]digo\s+de\s+credenciamento\s*:\s*(.+?)\s*(?=documento\s+de\s+RT|$)",
    "rt_art":         r"documento\s+de\s+RT\s*:\s*(.+?)\s*(?=DESCRI|$)",
    "sigef_codigo":   r"certifica[c\xe7][a\xe3]o\s+SIGEF\s*:\s*([a-f0-9A-F\-]{20,})",
    "sigef_data":     r"data\s+da\s+certifica[c\xe7][a\xe3]o\s*:\s*([\d/:\s]+?)(?:\s*Em\s+atendimento|$)",
}


# ============================================================
# Extracao de texto do PDF
# ============================================================

def _parece_fragmentado(txt: str) -> bool:
    linhas = [l for l in txt.splitlines() if l.strip()]
    if not linhas:
        return False
    curtas = sum(1 for l in linhas if len(l.strip()) <= 3)
    return curtas / len(linhas) > 0.4


def extrair_texto_pdf(pdf_path: str | Path) -> str:
    """Extrai texto de um PDF com multiplas estrategias de fallback."""
    if pdfplumber is None:
        raise RuntimeError("pdfplumber nao instalado. Execute: pip install pdfplumber")

    pages = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""

            if not txt.strip() or _parece_fragmentado(txt):
                try:
                    alt = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
                    if len(alt) > len(txt):
                        txt = alt
                except Exception:
                    pass

            if not txt.strip():
                words = page.extract_words(x_tolerance=3, y_tolerance=3)
                txt = " ".join(w["text"] for w in words)

            pages.append(txt)

    return "\n".join(pages)


# ============================================================
# Normalizacao
# ============================================================

def _normalizar(texto: str) -> str:
    """Normaliza o texto extraido do PDF."""
    # Ordinal masculino -> simbolo de grau
    texto = texto.replace("º", "°")

    # Aspas simples tipograficas -> apostrofe reto
    texto = texto.replace("’", "'").replace("‘", "'")
    texto = texto.replace("′", "'")

    # Aspas duplas tipograficas -> aspas retas
    texto = texto.replace("”", '"').replace("“", '"')
    texto = texto.replace("″", '"')

    # Hifen mole (soft hyphen) -> remove
    texto = texto.replace("­", "")

    # Hifenizacao de quebra de linha
    texto = re.sub(r"-\s*\n\s*", "", texto)

    # Normaliza whitespace
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _limpar_valor(valor: str) -> str:
    return re.sub(r"\s+", " ", valor).strip()


def _parse_numero_br(s: str) -> float:
    s = s.strip()
    return float(s.replace(".", "").replace(",", "."))


# ============================================================
# Parse do cabecalho
# ============================================================

def parse_cabecalho(texto_normalizado: str) -> dict:
    raw = {}
    for chave, padrao in CABECALHO_PATTERNS.items():
        m = re.search(padrao, texto_normalizado, re.IGNORECASE | re.DOTALL)
        if m:
            raw[chave] = _limpar_valor(m.group(1))

    cartorio_raw = raw.get("cartorio_raw", "")
    cns_cartorio = comarca = uf_cart = ""
    if cartorio_raw:
        m_cart = re.match(r"\(?([\d.\-]+)\)?\s*(.+?)\s*-\s*([A-Z]{2})\s*$", cartorio_raw)
        if m_cart:
            cns_cartorio = m_cart.group(1).strip()
            comarca      = m_cart.group(2).strip()
            uf_cart      = m_cart.group(3).strip()

    municipio = uf = ""
    if uf_cart:
        uf = uf_cart
    mun_raw = raw.get("municipio_uf", "")
    if mun_raw:
        m_mun = re.match(r"(.+?)\s*[-/]\s*([A-Z]{2})\s*$", mun_raw)
        if m_mun:
            municipio = m_mun.group(1).strip()
            uf        = m_mun.group(2).strip()
        else:
            municipio = mun_raw

    area_ha = perim_m = None
    if "area_ha" in raw:
        try:
            area_ha = _parse_numero_br(raw["area_ha"])
        except ValueError:
            pass
    if "perimetro_m" in raw:
        try:
            perim_m = _parse_numero_br(raw["perimetro_m"])
        except ValueError:
            pass

    sigef_codigo = raw.get("sigef_codigo", "")
    sigef_data   = raw.get("sigef_data", "").strip()

    return {
        "imovel": {
            "denominacao":   raw.get("denominacao", ""),
            "matricula":     raw.get("matricula", ""),
            "cns_cartorio":  cns_cartorio,
            "comarca":       comarca,
            "uf":            uf,
            "ccir":          raw.get("ccir", ""),
            "municipio":     municipio,
            "natureza_area": raw.get("natureza_area", "Particular"),
            "area_ha":       area_ha if area_ha is not None else 0.0,
            "perimetro_m":   perim_m if perim_m is not None else 0.0,
        },
        "proprietario": {
            "nome": raw.get("proprietario", ""),
            "cpf":  raw.get("cpf", ""),
        },
        "rt": {
            "nome":               raw.get("rt_nome", ""),
            "formacao":           raw.get("rt_formacao", "Engenheiro Agrimensor"),
            "crea":               raw.get("rt_crea", ""),
            "credenciado_codigo": raw.get("rt_credenciado", ""),
            "art":                raw.get("rt_art", ""),
        },
        "certificacao_sigef": {
            "incluir": bool(sigef_codigo),
            "codigo":  sigef_codigo,
            "data":    sigef_data,
        },
    }


# ============================================================
# Parse dos vertices
# ============================================================

def parse_vertices(texto_normalizado: str) -> list:
    """Extrai vertices da prosa do memorial SIGEF."""
    m_inicio = re.search(r"Inicia-se\s+a\s+descri[c\xe7][a\xe3]o", texto_normalizado, re.IGNORECASE)
    prosa = texto_normalizado[m_inicio.start():] if m_inicio else texto_normalizado
    m_fim = re.search(r"fechando\s+assim", prosa, re.IGNORECASE)
    if m_fim:
        prosa = prosa[: m_fim.end() + 300]

    vertices_brutos = [
        {
            "pos":    m.start(),
            "codigo": m.group(1).strip(),
            "lat":    m.group(2).strip(),
            "long":   m.group(3).strip(),
        }
        for m in VERTEX_RE.finditer(prosa)
    ]

    if not vertices_brutos:
        return []

    legs_brutos = []
    for m in LEG_RE.finditer(prosa):
        confrontante  = (m.group(1) or "").strip()
        qual          = (m.group(2) or "").strip()
        azimute       = m.group(3).strip()
        distancia_str = m.group(4).strip()
        try:
            distancia = _parse_numero_br(distancia_str)
        except ValueError:
            distancia = 0.0

        mat = cns = ""
        if qual:
            m_mat = MATRICULA_QUAL_RE.search(qual)
            m_cns = CNS_QUAL_RE.search(qual)
            if m_mat:
                mat = m_mat.group(1).strip()
            if m_cns:
                cns = m_cns.group(1).strip()

        legs_brutos.append({
            "pos":          m.start(),
            "confrontante": confrontante,
            "matricula":    mat,
            "cns":          cns,
            "azimute":      azimute,
            "distancia":    distancia,
        })

    n = len(vertices_brutos)
    primeiro_codigo = vertices_brutos[0]["codigo"]
    ultimo_eh_repeticao = n > 1 and vertices_brutos[-1]["codigo"] == primeiro_codigo
    n_efetivo = n - 1 if ultimo_eh_repeticao else n

    rows = []
    confrontante_atual = matricula_atual = cns_atual = ""

    for i in range(n_efetivo):
        v = vertices_brutos[i]
        pos_proximo = vertices_brutos[i + 1]["pos"] if i + 1 < n else len(prosa)
        leg = next(
            (l for l in legs_brutos if v["pos"] < l["pos"] < pos_proximo),
            None,
        )
        if leg is None:
            rows.append({
                "ordem":          i + 1,
                "vertice":        v["codigo"],
                "lat":            v["lat"],
                "long":           v["long"],
                "azimute":        "",
                "distancia":      0.0,
                "confrontante":   confrontante_atual,
                "matricula_conf": matricula_atual,
                "cns_conf":       cns_atual,
            })
            continue

        if leg["confrontante"]:
            confrontante_atual = leg["confrontante"]
            matricula_atual    = leg["matricula"]
            cns_atual          = leg["cns"]

        rows.append({
            "ordem":          i + 1,
            "vertice":        v["codigo"],
            "lat":            v["lat"],
            "long":           v["long"],
            "azimute":        leg["azimute"],
            "distancia":      leg["distancia"],
            "confrontante":   confrontante_atual,
            "matricula_conf": matricula_atual,
            "cns_conf":       cns_atual,
        })

    return rows


# ============================================================
# Funcoes publicas
# ============================================================

def parse_pdf_sigef(pdf_path: str | Path) -> dict:
    """Extrai dados de um PDF de memorial SIGEF."""
    texto = extrair_texto_pdf(pdf_path)
    texto_norm = _normalizar(texto)
    return {
        "texto_bruto":       texto,
        "texto_normalizado": texto_norm,
        "meta":              parse_cabecalho(texto_norm),
        "vertices":          parse_vertices(texto_norm),
    }


def parse_texto_sigef(texto: str) -> dict:
    """Recebe texto ja extraido (util para testes e debug)."""
    texto_norm = _normalizar(texto)
    return {
        "texto_bruto":       texto,
        "texto_normalizado": texto_norm,
        "meta":              parse_cabecalho(texto_norm),
        "vertices":          parse_vertices(texto_norm),
    }
