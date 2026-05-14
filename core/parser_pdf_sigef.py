"""
parser_pdf_sigef.py — v2 — Extrai dados de um memorial descritivo SIGEF em PDF.

Robusto a variações de encoding que pdfplumber pode produzir:
  - º (U+00BA ordinal) vs ° (U+00B0 grau)
  - ' (aspas curvas) vs ' (apóstrofe)
  - " (aspas curvas) vs " (reta)
  - palavras com/sem acento (vértice/vertice, distância/distancia, etc.)
  - símbolo de segundos ausente
"""

from __future__ import annotations

import re
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


# ============================================================
# Regex — vértices na prosa
# ============================================================

# Após normalização, ° e ' estão canônicos. Mas deixamos [°º] e [''] como
# segunda camada de segurança caso a normalização não pegue alguma variante.

VERTEX_RE = re.compile(
    # "vértice" ou "vertice" (sem acento)
    r"v[eé]rtices?\s+"
    # código: começa com letra, aceita letras, dígitos, hífen, ponto
    r"([A-Za-z][A-Za-z0-9\-\.]*)"
    r"\s*[,;]\s*"
    # "de coordenadas geodésicas" (acento opcional)
    r"(?:de\s+)?coordenadas?\s+geod[eé]sicas?\s+"
    # latitude: GG°MM'SS,sss" — °/º, '/', segundos opcionais
    r"latitude\s+(\d+[°º]\s*\d+['''’′]\s*[\d.,]+[\"''”″]?\s*)"
    r"\s*[Ss]\s+"
    r"e\s+longitude\s+"
    r"(\d+[°º]\s*\d+['''’′]\s*[\d.,]+[\"''”″]?\s*)"
    r"\s*[Ww]",
    re.IGNORECASE,
)

# Leg: confrontante (opcional) + azimute + distância
LEG_RE = re.compile(
    # confrontante (opcional)
    r"(?:confrontando\s+(?:agora\s+)?com\s+"
    r"(.+?)"
    r"(?:\s*\(([^)]*)\))?"
    r"\s*,\s+)?"
    # azimute geodésico (acento e símbolo opcionais)
    r"com\s+azimute\s+geod[eé]sico\s+de\s+"
    r"(\d+[°º]\s*\d+['''’′])"
    r"\s+"
    # distância (acento opcional)
    r"e\s+dist[aâ]ncia\s+de\s+"
    r"([\d.,]+)\s*m",
    re.IGNORECASE | re.DOTALL,
)

MATRICULA_QUAL_RE = re.compile(r"Matr[íi]cula\s+([^,)]+)", re.IGNORECASE)
CNS_QUAL_RE = re.compile(r"CNS\s+([^,)]+)", re.IGNORECASE)


# ============================================================
# Cabeçalho — padrão SIGEF (labels em maiúsculas ou mistas)
# ============================================================

CABECALHO_PATTERNS = {
    "denominacao":    r"denomina[cç][aã]o\s*:\s*(.+?)\s*(?=propriet[aá]|$)",
    "proprietario":   r"propriet[aá]rio\(?[aA]?\)?\s*:\s*(.+?)\s*(?=CPF|$)",
    "cpf":            r"CPF\s*:\s*([\d.\-/]+)",
    "matricula":      r"matr[íi]cula\s+do\s+im[oó]vel\s*:\s*(.+?)\s*(?=cart[oó]rio|$)",
    "cartorio_raw":   r"cart[oó]rio\s+de\s+registro\s+de\s+im[oó]veis\s*:\s*(.+?)\s*(?=c[oó]digo\s+INCRA|$)",
    "ccir":           r"c[oó]digo\s+INCRA[/\/]SNCR\s*:\s*([\d/.\-]+)",
    "municipio_uf":   r"munic[íi]pio[/\/]UF\s*:\s*(.+?)\s*(?=natureza|$)",
    "natureza_area":  r"natureza\s+da\s+[aá]rea\s*:\s*(.+?)\s*(?=[aá]rea|$)",
    "area_ha":        r"[aá]rea\s*(?:total\s*)?:\s*([\d.,]+)\s*ha",
    "perimetro_m":    r"per[íi]metro\s*:\s*([\d.,]+)\s*m",
    "rt_nome":        r"respons[aá]vel\s+t[eé]cnico\(?[aA]?\)?\s*:\s*(.+?)\s*(?=forma[cç][aã]o|$)",
    "rt_formacao":    r"forma[cç][aã]o\s*:\s*(.+?)\s*(?=conselho\s+profissional|$)",
    "rt_crea":        r"conselho\s+profissional\s*:\s*(.+?)\s*(?=c[oó]digo\s+de\s+credenciamento|$)",
    "rt_credenciado": r"c[oó]digo\s+de\s+credenciamento\s*:\s*(.+?)\s*(?=documento\s+de\s+RT|$)",
    "rt_art":         r"documento\s+de\s+RT\s*:\s*(.+?)\s*(?=DESCRI[CÇ][AÃÃ]O|$)",
    "sigef_codigo":   r"certifica[cç][aã]o\s+SIGEF\s*:\s*([a-f0-9A-F\-]{20,})",
    "sigef_data":     r"data\s+da\s+certifica[cç][aã]o\s*:\s*([\d/:\s]+?)(?:\s*Em\s+atendimento|$)",
}


# ============================================================
# Extração de texto do PDF
# ============================================================

def extrair_texto_pdf(pdf_path: str | Path) -> str:
    """Extrai texto de um PDF página por página, com fallback robusto."""
    if pdfplumber is None:
        raise RuntimeError("pdfplumber não instalado. Execute: pip install pdfplumber")
    pages = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            # Tenta extração simples (melhor para PDFs de coluna única como o SIGEF)
            txt = page.extract_text() or ""
            if not txt.strip():
                # Fallback: extrai palavras e reconstrói
                words = page.extract_words(x_tolerance=3, y_tolerance=3)
                txt = " ".join(w["text"] for w in words)
            pages.append(txt)
    return "\n".join(pages)


# ============================================================
# Normalização
# ============================================================

def _normalizar(texto: str) -> str:
    """Normaliza o texto extraído do PDF para facilitar o parsing.

    Converte variantes de caracteres especiais para formas canônicas:
    º → °, aspas curvas → retas, hifenização de linha → sem hífen.
    """
    # Ordinal masculino → símbolo de grau
    texto = texto.replace("º", "°")  # º → °

    # Aspas simples tipográficas → apóstrofe reto
    texto = texto.replace("‘", "'").replace("’", "'")
    texto = texto.replace("′", "'")

    # Aspas duplas tipográficas → aspas retas
    texto = texto.replace("“", '"').replace("”", '"')
    texto = texto.replace("″", '"')

    # Hífen mole (soft hyphen) → remove
    texto = texto.replace("\xad", "")

    # Hifenização de quebra de linha: "exemp-\nlo" → "exemplo"
    texto = re.sub(r"-\s*\n\s*", "", texto)

    # Normaliza whitespace
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _limpar_valor(valor: str) -> str:
    return re.sub(r"\s+", " ", valor).strip()


def _parse_numero_br(s: str) -> float:
    """Converte número no padrão BR ('1.234,56') para float."""
    s = s.strip()
    return float(s.replace(".", "").replace(",", "."))


# ============================================================
# Parse do cabeçalho
# ============================================================

def parse_cabecalho(texto_normalizado: str) -> dict:
    """Extrai metadados do cabeçalho. Retorna dict compatível com meta.json."""
    raw = {}
    for chave, padrao in CABECALHO_PATTERNS.items():
        m = re.search(padrao, texto_normalizado, re.IGNORECASE | re.DOTALL)
        if m:
            raw[chave] = _limpar_valor(m.group(1))

    # Cartório: "(00.326-9) Porto de Pedras - AL" → CNS, comarca, UF
    cartorio_raw = raw.get("cartorio_raw", "")
    cns_cartorio = comarca = uf_cart = ""
    if cartorio_raw:
        m_cart = re.match(r"\(?([\d.\-]+)\)?\s*(.+?)\s*-\s*([A-Z]{2})\s*$", cartorio_raw)
        if m_cart:
            cns_cartorio = m_cart.group(1).strip()
            comarca      = m_cart.group(2).strip()
            uf_cart      = m_cart.group(3).strip()

    # Município/UF
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

    # Área e perímetro
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

    # SIGEF
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
# Parse dos vértices
# ============================================================

def parse_vertices(texto_normalizado: str) -> list[dict]:
    """Extrai a lista de vértices da prosa do memorial SIGEF.

    Estratégia:
      1. Localiza o trecho de prosa entre "Inicia-se" e "fechando assim".
      2. Coleta todos os vértices (código + lat + long) com suas posições.
      3. Coleta todas as legs (confrontante + azimute + distância).
      4. Casa cada vértice N com a leg mais próxima APÓS sua posição.
      5. Mantém o confrontante corrente — só muda quando a leg traz novo.
      6. Ignora o último vértice se for repetição do primeiro (retorno textual).
    """
    # Recorta a prosa
    m_inicio = re.search(r"Inicia-se\s+a\s+descri[cç][aã]o", texto_normalizado, re.IGNORECASE)
    prosa = texto_normalizado[m_inicio.start():] if m_inicio else texto_normalizado
    m_fim = re.search(r"fechando\s+assim", prosa, re.IGNORECASE)
    if m_fim:
        prosa = prosa[: m_fim.end() + 300]

    # 1) Vértices
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

    # 2) Legs
    legs_brutos = []
    for m in LEG_RE.finditer(prosa):
        confrontante = (m.group(1) or "").strip()
        qual         = (m.group(2) or "").strip()
        azimute      = m.group(3).strip()
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

    # 3) Casamento vértice → leg
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
# Funções públicas
# ============================================================

def parse_pdf_sigef(pdf_path: str | Path) -> dict:
    """Extrai dados de um PDF de memorial SIGEF. Retorna texto bruto, meta e vértices."""
    texto = extrair_texto_pdf(pdf_path)
    texto_norm = _normalizar(texto)
    return {
        "texto_bruto":       texto,
        "texto_normalizado": texto_norm,
        "meta":              parse_cabecalho(texto_norm),
        "vertices":          parse_vertices(texto_norm),
    }


def parse_texto_sigef(texto: str) -> dict:
    """Recebe texto já extraído (útil para testes e debug)."""
    texto_norm = _normalizar(texto)
    return {
        "texto_bruto":       texto,
        "texto_normalizado": texto_norm,
        "meta":              parse_cabecalho(texto_norm),
        "vertices":          parse_vertices(texto_norm),
    }
