"""
parser_pdf_sigef.py — Extrai dados de um memorial descritivo SIGEF em PDF.

Suporta:
- Memorial em prosa única (padrão LADU/SIGEF certificado)
- Cabeçalho rotulado com até 18 campos
- Bloco de certificação SIGEF (hash + data)

Retorna estrutura compatível com `gerar_memorial.py` da skill
`engenheiro-agrimensor-analitico`.
"""

from __future__ import annotations

import re
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


# ============================================================
# Regex — cabeçalho
# ============================================================

# As patterns abaixo trabalham sobre o texto bruto extraído do PDF,
# com whitespace normalizado para um único espaço.

CABECALHO_PATTERNS = {
    "denominacao":    r"Denominação:\s*(.+?)\s*(?:Proprietário|$)",
    "proprietario":   r"Proprietário\(a\):\s*(.+?)\s*(?:CPF|$)",
    "cpf":            r"CPF:\s*([\d.\-/]+)",
    "matricula":      r"Matrícula do imóvel:\s*(.+?)\s*(?:Cartório|$)",
    "cartorio_raw":   r"Cartório de Registro de Imóveis:\s*(.+?)\s*(?:Código INCRA|$)",
    "ccir":           r"Código INCRA/SNCR:\s*([\d/.\-]+)",
    "municipio_uf":   r"Município/UF:\s*(.+?)\s*(?:Natureza|$)",
    "natureza_area":  r"Natureza da Área:\s*(.+?)\s*(?:Área|$)",
    "area_ha":        r"Área.*?:\s*([\d.,]+)\s*ha",
    "perimetro_m":    r"Perímetro:\s*([\d.,]+)\s*m",
    "rt_nome":        r"Responsável Técnico\(a\):\s*(.+?)\s*(?:Formação|$)",
    "rt_formacao":    r"Formação:\s*(.+?)\s*(?:Conselho|$)",
    "rt_crea":        r"Conselho Profissional:\s*(.+?)\s*(?:Código de Credenciamento|$)",
    "rt_credenciado": r"Código de Credenciamento:\s*(.+?)\s*(?:Documento de RT|$)",
    "rt_art":         r"Documento de RT:\s*(.+?)\s*(?:DESCRIÇÃO|$)",
    "sigef_codigo":   r"CERTIFICAÇÃO SIGEF:\s*([a-f0-9\-]{20,})",
    "sigef_data":     r"Data da Certificação:\s*([\d/:\s]+?)(?:\s*Em atendimento|$)",
}


# ============================================================
# Regex — vértices na prosa
# ============================================================

# Vértice com coordenadas: "vértice CODE, de coordenadas geodésicas latitude LAT S e longitude LONG W"
VERTEX_RE = re.compile(
    r"vértice\s+([A-Z0-9I\-]+)\s*,\s*"
    r"de\s+coordenadas\s+geodésicas\s+"
    r"latitude\s+(\d+°\d+'[\d.,]+\")\s*S\s+"
    r"e\s+longitude\s+(\d+°\d+'[\d.,]+\")\s*W",
    re.IGNORECASE,
)

# Leg: (opcional confrontante novo) + azimute + distância
# Captura: confrontante (opcional), qualificação (Matrícula X, CNS Y) (opcional), azimute, distância
LEG_RE = re.compile(
    r"(?:confrontando\s+(?:agora\s+)?com\s+(.+?)(?:\s*\(([^)]*)\))?\s*,\s+)?"
    r"com\s+azimute\s+geodésico\s+de\s+(\d+°\d+')\s+"
    r"e\s+distância\s+de\s+([\d.,]+)\s*m",
    re.IGNORECASE | re.DOTALL,
)

# Qualificação dentro de parênteses
MATRICULA_QUAL_RE = re.compile(r"Matrícula\s+([^,)]+)", re.IGNORECASE)
CNS_QUAL_RE = re.compile(r"CNS\s+([^,)]+)", re.IGNORECASE)


# ============================================================
# Função principal
# ============================================================

def extrair_texto_pdf(pdf_path: str | Path) -> str:
    """Extrai todo o texto de um PDF, página por página."""
    if pdfplumber is None:
        raise RuntimeError("pdfplumber não instalado. `pip install pdfplumber`.")
    pages = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            pages.append(txt)
    return "\n".join(pages)


def _normalizar(texto: str) -> str:
    """Normaliza whitespace: substitui sequências por espaço único."""
    # remove hifenização de quebra de linha do PDF: "exemp-\nlo" → "exemplo"
    texto = re.sub(r"-\s*\n\s*", "", texto)
    # normaliza espaços
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _limpar_valor(valor: str) -> str:
    """Limpa um valor extraído: remove espaços e quebras de linha extras."""
    return re.sub(r"\s+", " ", valor).strip()


def _parse_numero_br(s: str) -> float:
    """Converte número no padrão BR ('1.234,56') para float."""
    s = s.strip()
    # remove pontos de milhar e troca vírgula por ponto
    return float(s.replace(".", "").replace(",", "."))


def parse_cabecalho(texto_normalizado: str) -> dict:
    """Extrai metadados do cabeçalho. Retorna dict pronto para meta.json."""
    raw = {}
    for chave, padrao in CABECALHO_PATTERNS.items():
        m = re.search(padrao, texto_normalizado, re.IGNORECASE | re.DOTALL)
        if m:
            raw[chave] = _limpar_valor(m.group(1))

    # Pós-processamento

    # Cartório: "(00.326-9) Porto de Pedras - AL" → CNS, comarca, UF
    cartorio_raw = raw.get("cartorio_raw", "")
    cns_cartorio = ""
    comarca = ""
    uf_cart = ""
    if cartorio_raw:
        m_cart = re.match(
            r"\(?([\d.\-]+)\)?\s*(.+?)\s*-\s*([A-Z]{2})",
            cartorio_raw,
        )
        if m_cart:
            cns_cartorio = m_cart.group(1).strip()
            comarca = m_cart.group(2).strip()
            uf_cart = m_cart.group(3).strip()

    # Município/UF
    municipio = ""
    uf = uf_cart
    mun_raw = raw.get("municipio_uf", "")
    if mun_raw:
        m_mun = re.match(r"(.+?)\s*-\s*([A-Z]{2})", mun_raw)
        if m_mun:
            municipio = m_mun.group(1).strip()
            uf = m_mun.group(2).strip()
        else:
            municipio = mun_raw

    # Área e perímetro
    area_ha = None
    if "area_ha" in raw:
        try:
            area_ha = _parse_numero_br(raw["area_ha"])
        except ValueError:
            pass
    perim_m = None
    if "perimetro_m" in raw:
        try:
            perim_m = _parse_numero_br(raw["perimetro_m"])
        except ValueError:
            pass

    # SIGEF
    sigef_codigo = raw.get("sigef_codigo", "")
    sigef_data = raw.get("sigef_data", "").strip()
    incluir_sigef = bool(sigef_codigo)

    meta = {
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
            "incluir": incluir_sigef,
            "codigo":  sigef_codigo,
            "data":    sigef_data,
        },
    }
    return meta


def parse_vertices(texto_normalizado: str) -> list[dict]:
    """Extrai a lista de vértices da prosa do memorial.

    Estratégia:
      1. Encontra todas as ocorrências de declaração de vértice (codigo, lat, long).
      2. Encontra todas as ocorrências de declaração de leg (azimute, dist, confrontante).
      3. Casa cada vértice N com a leg que sai dele (a primeira leg após sua posição).
      4. Mantém o confrontante "corrente" entre legs — só atualiza quando houver
         "confrontando agora com".
      5. O último vértice da prosa (que volta ao primeiro) é IGNORADO porque ele é
         apenas a repetição textual do primeiro.
    """
    # Recorta a parte da prosa: do "Inicia-se" até o "fechando assim"
    m_inicio = re.search(r"Inicia-se a descrição", texto_normalizado, re.IGNORECASE)
    if not m_inicio:
        # fallback: usa o texto inteiro
        prosa = texto_normalizado
    else:
        prosa = texto_normalizado[m_inicio.start():]
        m_fim = re.search(r"fechando assim", prosa, re.IGNORECASE)
        if m_fim:
            prosa = prosa[: m_fim.end() + 200]  # mantém um pouco depois para pegar área/perímetro

    # 1) Coleta vértices com posição
    vertices_brutos = []
    for m in VERTEX_RE.finditer(prosa):
        vertices_brutos.append({
            "pos":     m.start(),
            "codigo":  m.group(1).strip(),
            "lat":     m.group(2).strip(),
            "long":    m.group(3).strip(),
        })

    if not vertices_brutos:
        return []

    # 2) Coleta legs com posição
    legs_brutos = []
    for m in LEG_RE.finditer(prosa):
        confrontante = (m.group(1) or "").strip()
        qual = (m.group(2) or "").strip()
        azimute = m.group(3).strip()
        distancia_str = m.group(4).strip()
        try:
            distancia = _parse_numero_br(distancia_str)
        except ValueError:
            distancia = 0.0

        # Extrai matrícula e CNS da qualificação
        mat = ""
        cns = ""
        if qual:
            m_mat = MATRICULA_QUAL_RE.search(qual)
            m_cns = CNS_QUAL_RE.search(qual)
            if m_mat:
                mat = m_mat.group(1).strip()
            if m_cns:
                cns = m_cns.group(1).strip()

        legs_brutos.append({
            "pos":           m.start(),
            "confrontante":  confrontante,
            "matricula":     mat,
            "cns":           cns,
            "azimute":       azimute,
            "distancia":     distancia,
        })

    # 3) Casa cada vértice com a primeira leg APÓS sua posição (e antes do próximo vértice)
    rows = []
    confrontante_atual = ""
    matricula_atual = ""
    cns_atual = ""

    # Detecta se o último vértice é repetição do primeiro (fechamento textual)
    n = len(vertices_brutos)
    primeiro_codigo = vertices_brutos[0]["codigo"]
    ultimo_eh_repeticao = (n > 1 and vertices_brutos[-1]["codigo"] == primeiro_codigo)
    n_efetivo = n - 1 if ultimo_eh_repeticao else n

    for i in range(n_efetivo):
        v = vertices_brutos[i]
        # próxima leg após v["pos"] e antes do próximo vértice
        pos_proximo = vertices_brutos[i + 1]["pos"] if i + 1 < n else len(prosa)
        leg = next(
            (l for l in legs_brutos if v["pos"] < l["pos"] < pos_proximo),
            None,
        )
        if leg is None:
            # Sem leg de saída, mas ainda registra o vértice (pode ser o último real)
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

        # Atualiza confrontante corrente se a leg trouxe mudança
        if leg["confrontante"]:
            confrontante_atual = leg["confrontante"]
            matricula_atual   = leg["matricula"]
            cns_atual         = leg["cns"]

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


def parse_pdf_sigef(pdf_path: str | Path) -> dict:
    """Parser principal. Retorna texto bruto, meta e vértices."""
    texto = extrair_texto_pdf(pdf_path)
    texto_norm = _normalizar(texto)
    return {
        "texto_bruto":     texto,
        "texto_normalizado": texto_norm,
        "meta":            parse_cabecalho(texto_norm),
        "vertices":        parse_vertices(texto_norm),
    }


def parse_texto_sigef(texto: str) -> dict:
    """Parser que recebe texto direto (útil para testes e para PDFs já extraídos)."""
    texto_norm = _normalizar(texto)
    return {
        "texto_bruto":     texto,
        "texto_normalizado": texto_norm,
        "meta":            parse_cabecalho(texto_norm),
        "vertices":        parse_vertices(texto_norm),
    }
