"""
calculos_topograficos.py — Biblioteca e CLI para cálculos topográficos e geodésicos.

Funções:
  - parse_gms(s)              Converte string "GG°MM'SS.sss\"" para grau decimal.
  - format_gms(d, decimais)   Converte grau decimal para string "GG°MM'SS.sss\"".
  - azimute(p1, p2)           Azimute no plano (p = (E, N)).
  - distancia(p1, p2)         Distância euclidiana no plano.
  - area_gauss(vertices)      Área da poligonal pela fórmula de Gauss.
  - transformar(coord, src, dst)  Transformação entre CRS via pyproj.
  - convergencia_meridiana(lat, lon, mc)   Convergência meridiana em graus.
  - fechamento_poligonal(vertices)   Vetor de erro e erro relativo.
  - compensar_proporcional(vertices)   Compensação proporcional ao lado.

Uso CLI:
  python calculos_topograficos.py azimute --p1 E1,N1 --p2 E2,N2
  python calculos_topograficos.py area --vertices arquivo.csv
  python calculos_topograficos.py transformar --de EPSG:4674 --para EPSG:31983 \\
        --entrada pontos.csv --saida pontos_utm.csv
  python calculos_topograficos.py fechamento --vertices arquivo.csv
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    from pyproj import Transformer
except ImportError:
    Transformer = None


# ============================================================
# Conversões GMS ↔ decimal
# ============================================================

GMS_RE = re.compile(
    r"""^\s*
    (?P<sinal>[-+]?)
    (?P<g>\d+)\s*[°dD]\s*
    (?:(?P<m>\d+)\s*['mM]\s*)?
    (?:(?P<s>\d+(?:[.,]\d+)?)\s*["sS]?\s*)?
    \s*(?P<hemi>[NSEWOnsew])?
    \s*$""",
    re.VERBOSE,
)


def parse_gms(s: str | float | int) -> float:
    """Converte string GMS para grau decimal. Aceita também float/int direto."""
    if isinstance(s, (int, float)):
        return float(s)
    s = str(s).strip().replace(",", ".")
    # tenta ler como decimal puro primeiro
    try:
        return float(s)
    except ValueError:
        pass
    m = GMS_RE.match(s)
    if not m:
        raise ValueError(f"Formato GMS inválido: {s!r}")
    g = int(m.group("g"))
    mn = int(m.group("m") or 0)
    sc = float(m.group("s") or 0)
    sinal = -1.0 if m.group("sinal") == "-" else 1.0
    hemi = (m.group("hemi") or "").upper()
    if hemi in ("S", "W", "O"):
        sinal = -1.0
    return sinal * (g + mn / 60.0 + sc / 3600.0)


def format_gms(d: float, decimais: int = 3) -> str:
    """Converte grau decimal para string GG°MM'SS.sss\"."""
    sinal = "-" if d < 0 else ""
    d = abs(d)
    g = int(d)
    mn_full = (d - g) * 60.0
    mn = int(mn_full)
    sc = (mn_full - mn) * 60.0
    # ajuste de carry: se sc arredondar para 60, somar nos minutos
    if round(sc, decimais) >= 60.0:
        sc = 0.0
        mn += 1
        if mn >= 60:
            mn = 0
            g += 1
    width = 2 if decimais == 0 else 3 + decimais
    return f"{sinal}{g:02d}°{mn:02d}'{sc:0{width}.{decimais}f}\""


# ============================================================
# Cálculos no plano
# ============================================================

@dataclass
class Ponto:
    E: float
    N: float
    nome: str | None = None

    def __iter__(self):
        return iter((self.E, self.N))


def azimute(p1: Sequence[float], p2: Sequence[float]) -> float:
    """Azimute do plano (graus, 0–360), referenciado ao N do grid."""
    dE = p2[0] - p1[0]
    dN = p2[1] - p1[1]
    az = math.degrees(math.atan2(dE, dN))
    if az < 0:
        az += 360.0
    return az


def distancia(p1: Sequence[float], p2: Sequence[float]) -> float:
    dE = p2[0] - p1[0]
    dN = p2[1] - p1[1]
    return math.hypot(dE, dN)


def area_gauss(vertices: Iterable[Sequence[float]]) -> float:
    """Área da poligonal fechada (m²). Vértices na ordem do percurso. Se o
    último ≠ primeiro, fecha automaticamente."""
    vs = [tuple(v) for v in vertices]
    if vs[0] != vs[-1]:
        vs.append(vs[0])
    s = 0.0
    for (E1, N1), (E2, N2) in zip(vs, vs[1:]):
        s += E1 * N2 - E2 * N1
    return abs(s) / 2.0


# ============================================================
# Geodésia
# ============================================================

def transformar(
    coord: tuple[float, float], src: str = "EPSG:4674", dst: str = "EPSG:31983"
) -> tuple[float, float]:
    """Transforma coordenada (x, y) ou (lon, lat) entre CRSs."""
    if Transformer is None:
        raise RuntimeError("pyproj não instalado. `pip install pyproj`.")
    tf = Transformer.from_crs(src, dst, always_xy=True)
    return tf.transform(coord[0], coord[1])


def convergencia_meridiana(lat_deg: float, lon_deg: float, mc_deg: float) -> float:
    """Convergência meridiana aproximada, em graus. γ ≈ (λ - λ0) · sin(φ)."""
    return (lon_deg - mc_deg) * math.sin(math.radians(lat_deg))


def fator_escala_utm(E_utm: float) -> float:
    """Fator de escala UTM para uma coordenada E (em metros, com False Easting de 500000)."""
    k0 = 0.9996
    dE = E_utm - 500000.0
    R = 6_378_137.0  # raio aprox.
    return k0 * (1.0 + (dE * dE) / (2.0 * R * R * k0 * k0))


# ============================================================
# Fechamento e compensação
# ============================================================

def fechamento_poligonal(vertices: Sequence[tuple[float, float]]) -> dict:
    """Calcula erro de fechamento da poligonal."""
    vs = list(vertices)
    if vs[0] == vs[-1]:
        vs = vs[:-1]  # remove repetição
    perim = 0.0
    dE_total = 0.0
    dN_total = 0.0
    n = len(vs)
    for i in range(n):
        p1 = vs[i]
        p2 = vs[(i + 1) % n]
        d = distancia(p1, p2)
        perim += d
        dE_total += p2[0] - p1[0]
        dN_total += p2[1] - p1[1]
    erro_linear = math.hypot(dE_total, dN_total)
    erro_relativo = perim / erro_linear if erro_linear > 0 else float("inf")
    return {
        "perimetro": perim,
        "dE_total": dE_total,
        "dN_total": dN_total,
        "erro_linear": erro_linear,
        "erro_relativo": erro_relativo,
        "erro_relativo_str": f"1/{erro_relativo:.0f}" if erro_relativo != float("inf") else "perfeito",
    }


def compensar_proporcional(
    vertices: Sequence[tuple[float, float]]
) -> list[tuple[float, float]]:
    """Compensação proporcional ao comprimento de cada lado. Distribui o
    desfechamento ΔE_total e ΔN_total entre os vértices."""
    vs = list(vertices)
    fechado = vs[0] == vs[-1]
    if fechado:
        vs = vs[:-1]
    n = len(vs)
    # comprimentos
    Ls = []
    for i in range(n):
        Ls.append(distancia(vs[i], vs[(i + 1) % n]))
    perim = sum(Ls)
    fech = fechamento_poligonal(vs)
    dE_t, dN_t = fech["dE_total"], fech["dN_total"]
    # acumular L até cada vértice; vértice i recebe correção proporcional a sum_L[0..i]
    sum_L = 0.0
    novos: list[tuple[float, float]] = []
    novos.append(vs[0])
    for i in range(1, n):
        sum_L += Ls[i - 1]
        f = sum_L / perim
        E = vs[i][0] - dE_t * f
        N = vs[i][1] - dN_t * f
        novos.append((E, N))
    if fechado:
        novos.append(novos[0])
    return novos


# ============================================================
# CLI
# ============================================================

def _read_vertices_csv(path: str) -> list[Ponto]:
    if pd is None:
        raise RuntimeError("pandas não instalado.")
    df = pd.read_csv(path)
    cols = {c.lower(): c for c in df.columns}
    if "ordem" in cols:
        df = df.sort_values(cols["ordem"])
    pts = []
    for _, row in df.iterrows():
        E = float(row[cols.get("e", "E")])
        N = float(row[cols.get("n", "N")])
        nome = str(row[cols.get("vertice", "vertice")]) if "vertice" in cols else None
        pts.append(Ponto(E, N, nome))
    return pts


def _cmd_azimute(args):
    p1 = tuple(map(float, args.p1.split(",")))
    p2 = tuple(map(float, args.p2.split(",")))
    az = azimute(p1, p2)
    d = distancia(p1, p2)
    print(f"Azimute: {az:.6f}° ({format_gms(az, 0)})")
    print(f"Distancia: {d:.3f} m")


def _cmd_area(args):
    pts = _read_vertices_csv(args.vertices)
    coords = [(p.E, p.N) for p in pts]
    A = area_gauss(coords)
    print(f"Area: {A:.4f} m² = {A / 10000.0:.4f} ha")


def _cmd_transformar(args):
    if pd is None:
        raise RuntimeError("pandas não instalado.")
    df = pd.read_csv(args.entrada)
    cols = list(df.columns)
    # heurística: tenta achar colunas x/y, lon/lat, E/N
    pares = [("lon", "lat"), ("longitude", "latitude"), ("x", "y"), ("E", "N"), ("e", "n")]
    xcol = ycol = None
    for px, py in pares:
        if px in cols and py in cols:
            xcol, ycol = px, py
            break
    if xcol is None:
        raise RuntimeError("Não identifiquei colunas de coordenada. Use lon/lat, x/y ou E/N.")
    tf = Transformer.from_crs(args.de, args.para, always_xy=True)
    df[f"{xcol}_out"], df[f"{ycol}_out"] = tf.transform(df[xcol].values, df[ycol].values)
    df.to_csv(args.saida, index=False)
    print(f"Salvo em {args.saida}")


def _cmd_fechamento(args):
    pts = _read_vertices_csv(args.vertices)
    coords = [(p.E, p.N) for p in pts]
    r = fechamento_poligonal(coords)
    print(f"Perimetro........: {r['perimetro']:.3f} m")
    print(f"ΔE total.........: {r['dE_total']:.4f} m")
    print(f"ΔN total.........: {r['dN_total']:.4f} m")
    print(f"Erro linear......: {r['erro_linear']:.4f} m")
    print(f"Erro relativo....: {r['erro_relativo_str']}")


def main(argv=None):
    p = argparse.ArgumentParser(description="Cálculos topográficos.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("azimute", help="Azimute e distância entre dois pontos UTM.")
    s.add_argument("--p1", required=True, help="E1,N1")
    s.add_argument("--p2", required=True, help="E2,N2")
    s.set_defaults(func=_cmd_azimute)

    s = sub.add_parser("area", help="Área de poligonal a partir de CSV.")
    s.add_argument("--vertices", required=True)
    s.set_defaults(func=_cmd_area)

    s = sub.add_parser("transformar", help="Transforma CRS de um CSV.")
    s.add_argument("--de", default="EPSG:4674")
    s.add_argument("--para", default="EPSG:31983")
    s.add_argument("--entrada", required=True)
    s.add_argument("--saida", required=True)
    s.set_defaults(func=_cmd_transformar)

    s = sub.add_parser("fechamento", help="Erro de fechamento da poligonal.")
    s.add_argument("--vertices", required=True)
    s.set_defaults(func=_cmd_fechamento)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
