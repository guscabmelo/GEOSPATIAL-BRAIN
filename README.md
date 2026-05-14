# GEOSPATIAL BRAIN

App web para geração de **Memorial Descritivo** e **Tabela de Coordenadas** no padrão LADU / SIGEF / INCRA, derivado da skill `engenheiro-agrimensor-analitico`.

## Funcionalidades

- 📍 Entrada de vértices via upload de CSV/XLSX ou editor interativo
- 📄 Geração de memorial descritivo em prosa única (padrão SIGEF), com troca automática de confrontante
- 📊 Tabela de coordenadas formatada (lat/long em GMS, azimute, distância, confrontante)
- 🔏 Bloco opcional de certificação SIGEF
- ⬇️ Exportação em `.md`, `.txt`, `.docx`, `.csv`, `.xlsx`
- 💾 Importar/exportar configuração `meta.json`

## Instalação

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Estrutura

```
GEOSPATIAL-BRAIN/
├── app.py                          # App Streamlit
├── requirements.txt
├── core/
│   ├── calculos_topograficos.py    # Cálculos geodésicos (da skill)
│   └── gerar_memorial.py           # Gerador de memorial (da skill)
└── dados/
    ├── exemplo_vertices.csv        # CSV de exemplo (Fazenda Água Preta)
    ├── exemplo_meta.json           # meta.json de exemplo
    └── dados_rt_padrao.json        # Dados padrão do RT
```

## Formato do CSV de vértices

| coluna           | obrigatória | exemplo                  |
|------------------|-------------|--------------------------|
| `ordem`          | sim         | `1, 2, 3...`             |
| `vertice`        | sim         | `ALG-P-0001`             |
| `lat`            | sim         | `9°11'50,695"` ou `-9.197` |
| `long`           | sim         | `35°22'10,663"`          |
| `azimute`        | sim         | `138°24'` ou `138.4`     |
| `distancia`      | sim         | `304.44`                 |
| `confrontante`   | sim         | `JOSÉ DA SILVA`          |
| `matricula_conf` | não         | `2093`                   |
| `cns_conf`       | não         | `00.326-9`               |

## Padrões aplicados

- Coordenadas: GMS com 3 decimais nos segundos, vírgula decimal
- Azimutes: `GG°MM'` (sem segundos)
- Distâncias: 2 decimais, vírgula decimal, ponto de milhar
- Áreas: 4 decimais em hectares
- Sistema: SIRGAS 2000

Baseado na skill **engenheiro-agrimensor-analitico**.
