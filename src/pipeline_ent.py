"""
Pipeline de Inteligencia de Negocios - Mortalidad prematura por ENT en hombres (30-70 años)
Proyecto final BI - Sistema de Autoevaluación de Riesgo de ENT en Colombia

Etapas:  1) Extracción   2) Limpieza y transformación   3) Análisis y KPI
         4) Gráficas      5) Exportación (Excel + CSV)    6) Dashboard HTML

Uso:
    python src/pipeline_ent.py                      # usa data/raw/SH.DYN.NCOM.MA.ZS_extraccion.csv
    python src/pipeline_ent.py --entrada API_SH.DYN.NCOM.MA.ZS_DS2_es_csv_v2.csv
        (acepta también el CSV oficial descargado de datos.bancomundial.org,
         que trae 4 filas de metadatos y columnas 1960-2024)
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
import numpy as np
import pandas as pd
from openpyxl.styles import Font, PatternFill

BASE = Path(__file__).resolve().parent.parent
RAW = BASE / "data" / "raw"
PROC = BASE / "data" / "processed"
OUT = BASE / "outputs"
GRAF = OUT / "graficas"

PAISES = {  # código ISO3 -> nombre en español
    "COL": "Colombia", "PER": "Perú", "ECU": "Ecuador", "CHL": "Chile",
    "ARG": "Argentina", "BRA": "Brasil", "MEX": "México",
}
ANIO_MIN, ANIO_MAX = 2000, 2021
LINEA_BASE_ODS, ANIO_META_ODS = 2015, 2030   # ODS 3.4: reducir 1/3 la mortalidad prematura por ENT

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("pipeline_ent")


# ----------------------------------------------------------------------------- 1. EXTRACCIÓN
def extraer(ruta: Path) -> pd.DataFrame:
    """Lee el CSV en formato ancho del Banco Mundial (con o sin filas de metadatos)."""
    with open(ruta, encoding="utf-8-sig") as f:
        primera = f.readline()
    saltar = 4 if primera.startswith('"Data Source"') or primera.startswith("Data Source") else 0
    df = pd.read_csv(ruta, skiprows=saltar, encoding="utf-8-sig")
    log.info("Extracción: %s filas x %s columnas desde %s", *df.shape, ruta.name)
    return df


# ----------------------------------------------------------------------------- 2. LIMPIEZA
def limpiar(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Devuelve la tabla larga limpia y la bitácora de limpieza."""
    bitacora = []

    def registrar(paso, antes, despues, detalle):
        bitacora.append({"paso": paso, "registros_antes": antes, "registros_despues": despues, "detalle": detalle})
        log.info("Limpieza | %s | %s -> %s | %s", paso, antes, despues, detalle)

    # 2.1 eliminar columnas vacías / sin nombre (el CSV oficial trae una columna final vacía)
    n = df.shape[1]
    df = df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]
    registrar("Columnas sin nombre", n, df.shape[1], "Columnas residuales eliminadas")

    # 2.2 filtrar países del alcance
    n = len(df)
    df = df[df["Country Code"].isin(PAISES)].copy()
    registrar("Filtro de países", n, len(df), "Se conservan COL, PER, ECU, CHL, ARG, BRA, MEX")

    # 2.3 despivotar (unpivot) años -> filas
    anios = [c for c in df.columns if str(c).strip().isdigit()]
    largo = df.melt(id_vars=["Country Code", "Indicator Code"], value_vars=anios,
                    var_name="anio", value_name="mortalidad_pct")
    registrar("Despivotado", len(df), len(largo), f"{len(anios)} columnas de año convertidas en filas")

    # 2.4 tipificar
    largo["anio"] = largo["anio"].astype(int)
    largo["mortalidad_pct"] = pd.to_numeric(largo["mortalidad_pct"], errors="coerce")

    # 2.5 recortar periodo de análisis
    n = len(largo)
    largo = largo[largo["anio"].between(ANIO_MIN, ANIO_MAX)]
    registrar("Filtro de periodo", n, len(largo), f"Años {ANIO_MIN}-{ANIO_MAX}")

    # 2.6 nulos (años sin publicación)
    n = len(largo)
    largo = largo.dropna(subset=["mortalidad_pct"])
    registrar("Valores nulos", n, len(largo), "Se eliminan años sin dato publicado (no se imputan)")

    # 2.7 duplicados
    n = len(largo)
    largo = largo.drop_duplicates(subset=["Country Code", "anio"])
    registrar("Duplicados", n, len(largo), "Clave única país-año")

    # 2.8 validación de dominio (probabilidad en %)
    fuera = largo[~largo["mortalidad_pct"].between(0, 100)]
    n = len(largo)
    largo = largo.drop(fuera.index)
    registrar("Validación de rango", n, len(largo), "Valores fuera de 0-100 % descartados")

    # 2.9 estandarizar nombres y derivar campos
    largo = largo.rename(columns={"Country Code": "codigo_pais", "Indicator Code": "codigo_indicador"})
    largo["pais"] = largo["codigo_pais"].map(PAISES)
    largo = largo.sort_values(["codigo_pais", "anio"]).reset_index(drop=True)
    largo["variacion_anual_pp"] = largo.groupby("codigo_pais")["mortalidad_pct"].diff().round(2)
    base = largo.groupby("codigo_pais")["mortalidad_pct"].transform("first")
    largo["indice_base2000"] = (largo["mortalidad_pct"] / base * 100).round(1)
    largo["quinquenio"] = (largo["anio"] // 5 * 5).astype(str) + "-" + (largo["anio"] // 5 * 5 + 4).astype(str)
    largo["es_colombia"] = largo["codigo_pais"].eq("COL")
    registrar("Campos derivados", len(largo), len(largo),
              "pais (ES), variacion_anual_pp, indice_base2000, quinquenio, es_colombia")

    cols = ["codigo_pais", "pais", "codigo_indicador", "anio", "quinquenio", "mortalidad_pct",
            "variacion_anual_pp", "indice_base2000", "es_colombia"]
    return largo[cols], bitacora


# ----------------------------------------------------------------------------- 3. ANÁLISIS Y KPI
def tendencia(serie: pd.DataFrame) -> tuple[float, float]:
    x, y = serie["anio"].to_numpy(), serie["mortalidad_pct"].to_numpy()
    m, b = np.polyfit(x, y, 1)
    r2 = 1 - ((y - (m * x + b)) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return float(m), float(r2)


def analizar(df: pd.DataFrame) -> tuple[pd.DataFrame, dict, pd.DataFrame]:
    a0, a1 = int(df["anio"].min()), int(df["anio"].max())
    filas = []
    for cod, g in df.groupby("codigo_pais"):
        v0 = g.loc[g["anio"] == a0, "mortalidad_pct"].iat[0]
        v1 = g.loc[g["anio"] == a1, "mortalidad_pct"].iat[0]
        m, r2 = tendencia(g)
        m_rec, _ = tendencia(g[g["anio"] >= a1 - 5])
        filas.append({
            "codigo_pais": cod, "pais": PAISES[cod], f"valor_{a0}": v0, f"valor_{a1}": v1,
            "variacion_abs_pp": round(v1 - v0, 2), "variacion_rel_pct": round((v1 / v0 - 1) * 100, 1),
            "tcac_pct": round(((v1 / v0) ** (1 / (a1 - a0)) - 1) * 100, 2),
            "pendiente_pp_anio": round(m, 3), "r2_tendencia": round(r2, 3),
            "pendiente_ultimos_5a": round(m_rec, 3),
            "promedio_periodo": round(g["mortalidad_pct"].mean(), 2),
            "volatilidad_pp": round(g["variacion_anual_pp"].std(), 2),
            "anios_con_aumento": int((g["variacion_anual_pp"] > 0).sum()),
            "maximo": g["mortalidad_pct"].max(), "minimo": g["mortalidad_pct"].min(),
        })
    resumen = pd.DataFrame(filas).sort_values(f"valor_{a1}").reset_index(drop=True)
    resumen.insert(2, f"ranking_{a1}", range(1, len(resumen) + 1))

    col = df[df["codigo_pais"] == "COL"].set_index("anio")["mortalidad_pct"]
    prom = df.groupby("anio")["mortalidad_pct"].mean()
    base_ods = col.get(LINEA_BASE_ODS)
    meta_ods = base_ods * 2 / 3
    reduc_req_anual = (base_ods - meta_ods) / (ANIO_META_ODS - LINEA_BASE_ODS)
    reduc_real_anual = (base_ods - col[a1]) / (a1 - LINEA_BASE_ODS)
    r_col = resumen.set_index("codigo_pais").loc["COL"]
    kpi = {
        "anio_inicio": a0, "anio_fin": a1,
        "col_valor_actual": float(col[a1]),
        "col_valor_inicial": float(col[a0]),
        "col_variacion_abs_pp": float(r_col["variacion_abs_pp"]),
        "col_variacion_rel_pct": float(r_col["variacion_rel_pct"]),
        "col_tcac_pct": float(r_col["tcac_pct"]),
        "col_pendiente": float(r_col["pendiente_pp_anio"]),
        "col_r2": float(r_col["r2_tendencia"]),
        "col_pendiente_ult5": float(r_col["pendiente_ultimos_5a"]),
        "col_ranking": int(r_col[f"ranking_{a1}"]), "n_paises": len(resumen),
        "promedio_grupo_actual": round(float(prom[a1]), 2),
        "brecha_vs_promedio_pp": round(float(col[a1] - prom[a1]), 2),
        "col_anios_con_aumento": int(r_col["anios_con_aumento"]),
        "col_volatilidad": float(r_col["volatilidad_pp"]),
        "ods_linea_base": float(base_ods), "ods_meta_2030": round(float(meta_ods), 2),
        "ods_reduccion_requerida_anual": round(float(reduc_req_anual), 3),
        "ods_reduccion_real_anual": round(float(reduc_real_anual), 3),
        "ods_cumplimiento_ritmo_pct": round(float(reduc_real_anual / reduc_req_anual * 100), 1),
        "ods_proyeccion_2030": round(float(col[a1] - reduc_real_anual * (ANIO_META_ODS - a1)), 2),
        "pais_mayor": resumen.iloc[-1]["pais"], "valor_mayor": float(resumen.iloc[-1][f"valor_{a1}"]),
        "pais_menor": resumen.iloc[0]["pais"], "valor_menor": float(resumen.iloc[0][f"valor_{a1}"]),
    }
    sexo = RAW / "colombia_por_sexo_2019.csv"
    if sexo.exists():
        s = pd.read_csv(sexo).set_index("Desagregacion")["2019"]
        kpi["col_hombres_2019"], kpi["col_mujeres_2019"] = float(s["Hombres"]), float(s["Mujeres"])
        kpi["brecha_sexo_pp"] = round(float(s["Hombres"] - s["Mujeres"]), 2)
        kpi["razon_hombre_mujer"] = round(float(s["Hombres"] / s["Mujeres"]), 2)

    quinq = df.pivot_table(index="quinquenio", columns="pais", values="mortalidad_pct", aggfunc="mean").round(2)
    log.info("KPI calculados: %s", json.dumps({k: kpi[k] for k in list(kpi)[:6]}, ensure_ascii=False))
    return resumen, kpi, quinq


# ----------------------------------------------------------------------------- 4. GRÁFICAS
COLORES = {"Colombia": "#C8102E", "Perú": "#7A8B99", "Ecuador": "#A3B1BD", "Chile": "#5B6D7C",
           "Argentina": "#2F4858", "Brasil": "#3E7CB1", "México": "#81A4CD"}


def _estilo(ax, titulo, ylabel="Probabilidad de morir 30-70 años (%)"):
    ax.set_title(titulo, loc="left", fontsize=12, fontweight="bold", color="#1F2937")
    ax.set_ylabel(ylabel, fontsize=9, color="#4B5563")
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", color="#E5E7EB", linewidth=0.8)
    ax.tick_params(colors="#4B5563", labelsize=9)


def graficar(df: pd.DataFrame, resumen: pd.DataFrame, kpi: dict) -> list[Path]:
    GRAF.mkdir(parents=True, exist_ok=True)
    a0, a1 = kpi["anio_inicio"], kpi["anio_fin"]
    rutas = []

    # G1 evolución por país
    fig, ax = plt.subplots(figsize=(9, 4.8), dpi=150)
    etiquetas = []
    for pais, g in df.groupby("pais"):
        es = pais == "Colombia"
        ax.plot(g["anio"], g["mortalidad_pct"], color=COLORES[pais], lw=2.8 if es else 1.4,
                alpha=1 if es else 0.85, zorder=3 if es else 2)
        etiquetas.append([g["mortalidad_pct"].iat[-1], pais])
    etiquetas.sort()
    for i in range(1, len(etiquetas)):          # evita superposición de etiquetas finales
        etiquetas[i][0] = max(etiquetas[i][0], etiquetas[i - 1][0] + 0.75)
    for yv, pais in etiquetas:
        ax.annotate(pais, (a1 + 0.3, yv), va="center", fontsize=8.5, color=COLORES[pais],
                    fontweight="bold" if pais == "Colombia" else "normal")
    ax.set_xlim(a0, a1 + 2.2)
    ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
    _estilo(ax, f"G1. Mortalidad prematura por ENT en hombres, {a0}-{a1}")
    rutas.append(_guardar(fig, "g1_evolucion_paises.png"))

    # G2 ranking último año
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    r = resumen.sort_values(f"valor_{a1}")
    barras = ax.barh(r["pais"], r[f"valor_{a1}"], color=[COLORES[p] for p in r["pais"]])
    ax.bar_label(barras, fmt="%.1f %%", padding=3, fontsize=9)
    ax.axvline(kpi["promedio_grupo_actual"], color="#111827", ls="--", lw=1)
    ax.text(kpi["promedio_grupo_actual"], -0.9, f" Promedio grupo {kpi['promedio_grupo_actual']:.1f} %",
            fontsize=8.5)
    _estilo(ax, f"G2. Ranking {a1}: probabilidad de morir por ENT (hombres)", ylabel="")
    ax.set_xlabel("%", fontsize=9)
    ax.grid(axis="x", color="#E5E7EB"); ax.grid(axis="y", visible=False); ax.set_axisbelow(True)
    rutas.append(_guardar(fig, "g2_ranking_ultimo_anio.png"))

    # G3 variación relativa
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    r = resumen.sort_values("variacion_rel_pct")
    barras = ax.barh(r["pais"], r["variacion_rel_pct"], color=[COLORES[p] for p in r["pais"]])
    ax.bar_label(barras, fmt="%.1f %%", padding=3, fontsize=9)
    ax.axvline(0, color="#111827", lw=0.8)
    _estilo(ax, f"G3. Variación relativa {a0}-{a1} (%)", ylabel="")
    ax.grid(axis="x", color="#E5E7EB"); ax.grid(axis="y", visible=False)
    rutas.append(_guardar(fig, "g3_variacion_relativa.png"))

    # G4 Colombia vs promedio con tendencia y meta ODS
    col = df[df["codigo_pais"] == "COL"]
    prom = df.groupby("anio")["mortalidad_pct"].mean()
    fig, ax = plt.subplots(figsize=(9, 4.8), dpi=150)
    ax.plot(col["anio"], col["mortalidad_pct"], color=COLORES["Colombia"], lw=2.6, marker="o", ms=3.5, label="Colombia")
    ax.plot(prom.index, prom.values, color="#6B7280", lw=1.6, ls="--", label="Promedio de los 7 países")
    x = np.arange(LINEA_BASE_ODS, ANIO_META_ODS + 1)
    meta = kpi["ods_linea_base"] - kpi["ods_reduccion_requerida_anual"] * (x - LINEA_BASE_ODS)
    ax.plot(x, meta, color="#059669", lw=1.6, label="Senda ODS 3.4 (-1/3 a 2030)")
    xp = np.arange(a1, ANIO_META_ODS + 1)
    ax.plot(xp, kpi["col_valor_actual"] - kpi["ods_reduccion_real_anual"] * (xp - a1),
            color=COLORES["Colombia"], lw=1.4, ls=":", label="Proyección al ritmo 2015-" + str(a1))
    ax.scatter([ANIO_META_ODS], [kpi["ods_meta_2030"]], color="#059669", zorder=4)
    ax.annotate(f"Meta 2030: {kpi['ods_meta_2030']:.1f} %", (ANIO_META_ODS, kpi["ods_meta_2030"]),
                xytext=(-110, 8), textcoords="offset points", fontsize=8.5, color="#059669")
    ax.legend(frameon=False, fontsize=8.5, loc="upper right")
    _estilo(ax, "G4. Colombia frente al promedio regional y a la meta ODS 3.4")
    rutas.append(_guardar(fig, "g4_colombia_vs_promedio_ods.png"))

    # G5 variación anual Colombia
    fig, ax = plt.subplots(figsize=(9, 3.8), dpi=150)
    v = col.dropna(subset=["variacion_anual_pp"])
    ax.bar(v["anio"], v["variacion_anual_pp"],
           color=np.where(v["variacion_anual_pp"] > 0, "#C8102E", "#3E7CB1"))
    ax.axhline(0, color="#111827", lw=0.8)
    _estilo(ax, "G5. Colombia: variación anual (puntos porcentuales)", ylabel="pp vs año anterior")
    rutas.append(_guardar(fig, "g5_variacion_anual_colombia.png"))

    # G6 mapa de calor quinquenal
    q = df.pivot_table(index="pais", columns="quinquenio", values="mortalidad_pct", aggfunc="mean")
    q = q.loc[resumen.sort_values(f"valor_{a1}", ascending=False)["pais"]]
    fig, ax = plt.subplots(figsize=(8, 4.2), dpi=150)
    im = ax.imshow(q.values, cmap="Reds", aspect="auto")
    ax.set_xticks(range(q.shape[1]), q.columns, fontsize=9)
    ax.set_yticks(range(q.shape[0]), q.index, fontsize=9)
    for i in range(q.shape[0]):
        for j in range(q.shape[1]):
            val = q.values[i, j]
            ax.text(j, i, f"{val:.1f}", ha="center", va="center", fontsize=8.5,
                    color="white" if val > 19 else "#111827")
    fig.colorbar(im, ax=ax, shrink=0.8, label="%")
    ax.set_title("G6. Promedio quinquenal por país (%)", loc="left", fontsize=12, fontweight="bold")
    rutas.append(_guardar(fig, "g6_mapa_calor_quinquenios.png"))

    # G7 brecha por sexo Colombia
    if "col_hombres_2019" in kpi:
        fig, ax = plt.subplots(figsize=(6, 3.6), dpi=150)
        barras = ax.bar(["Hombres", "Mujeres"], [kpi["col_hombres_2019"], kpi["col_mujeres_2019"]],
                        color=["#C8102E", "#7A8B99"], width=0.55)
        ax.bar_label(barras, fmt="%.1f %%", padding=3, fontsize=10)
        _estilo(ax, "G7. Colombia 2019: mortalidad prematura por ENT por sexo")
        rutas.append(_guardar(fig, "g7_brecha_sexo_colombia.png"))
    return rutas


def _guardar(fig, nombre):
    ruta = GRAF / nombre
    fig.tight_layout()
    fig.savefig(ruta, bbox_inches="tight")
    plt.close(fig)
    log.info("Gráfica generada: %s", nombre)
    return ruta


# ----------------------------------------------------------------------------- 5. EXPORTACIÓN
def exportar(crudo, limpio, resumen, kpi, quinq, bitacora):
    PROC.mkdir(parents=True, exist_ok=True)
    limpio.to_csv(PROC / "fact_mortalidad_ent.csv", index=False, encoding="utf-8-sig")
    resumen.to_csv(PROC / "resumen_paises.csv", index=False, encoding="utf-8-sig")
    (PROC / "kpi.json").write_text(json.dumps(kpi, ensure_ascii=False, indent=2), encoding="utf-8")

    dim_pais = pd.DataFrame({"codigo_pais": list(PAISES), "pais": list(PAISES.values()),
                             "region": ["Andina", "Andina", "Andina", "Cono Sur", "Cono Sur", "Cono Sur", "Norteamérica"]})
    dim_anio = pd.DataFrame({"anio": sorted(limpio["anio"].unique())})
    dim_anio["quinquenio"] = (dim_anio["anio"] // 5 * 5).astype(str) + "-" + (dim_anio["anio"] // 5 * 5 + 4).astype(str)
    dim_anio["periodo_ods"] = np.where(dim_anio["anio"] >= LINEA_BASE_ODS, "ODS (2015+)", "Pre-ODS")
    kpi_tabla = pd.DataFrame([{"kpi": k, "valor": v} for k, v in kpi.items()])
    dicc = pd.DataFrame([
        ("codigo_pais", "Código ISO 3166-1 alfa-3 del país", "Texto (3)", "COL, PER, ECU, CHL, ARG, BRA, MEX"),
        ("pais", "Nombre del país en español", "Texto", "Catálogo de 7 países"),
        ("codigo_indicador", "Código WDI del indicador", "Texto", "SH.DYN.NCOM.MA.ZS"),
        ("anio", "Año de referencia del dato", "Entero", f"{ANIO_MIN}-{ANIO_MAX}"),
        ("quinquenio", "Agrupación de 5 años", "Texto", "2000-2004 ... 2015-2019"),
        ("mortalidad_pct", "Probabilidad (%) de que un hombre de 30 años muera antes de los 70 por ECV, cáncer, diabetes o EPOC",
         "Decimal (4,1)", "0-100"),
        ("variacion_anual_pp", "Diferencia frente al año anterior, en puntos porcentuales", "Decimal", "Negativo = mejora"),
        ("indice_base2000", "Valor del año / valor del año inicial x 100", "Decimal", "100 = año inicial"),
        ("es_colombia", "Bandera para resaltar Colombia en visualizaciones", "Booleano", "True / False"),
    ], columns=["campo", "definicion", "tipo", "dominio"])

    ruta = OUT / "Base_Datos_Consolidada_ENT.xlsx"
    with pd.ExcelWriter(ruta, engine="openpyxl") as xw:
        pd.DataFrame({"Hoja": ["1_Datos_Crudos", "2_Hechos_Limpios", "3_Dim_Pais", "4_Dim_Anio", "5_Resumen_Paises",
                               "6_KPI", "7_Quinquenios", "8_Bitacora_Limpieza", "9_Diccionario"],
                      "Contenido": ["Extracción original en formato ancho (Banco Mundial / OMS GHO)",
                                    "Tabla de hechos despivotada y validada (país-año)",
                                    "Dimensión país", "Dimensión tiempo", "Indicadores por país",
                                    "KPI calculados por el programa", "Promedios quinquenales",
                                    "Registro de cada paso de limpieza", "Diccionario de datos de la tabla de hechos"]}
                     ).to_excel(xw, sheet_name="0_Indice", index=False)
        crudo.to_excel(xw, sheet_name="1_Datos_Crudos", index=False)
        limpio.to_excel(xw, sheet_name="2_Hechos_Limpios", index=False)
        dim_pais.to_excel(xw, sheet_name="3_Dim_Pais", index=False)
        dim_anio.to_excel(xw, sheet_name="4_Dim_Anio", index=False)
        resumen.to_excel(xw, sheet_name="5_Resumen_Paises", index=False)
        kpi_tabla.to_excel(xw, sheet_name="6_KPI", index=False)
        quinq.reset_index().to_excel(xw, sheet_name="7_Quinquenios", index=False)
        pd.DataFrame(bitacora).to_excel(xw, sheet_name="8_Bitacora_Limpieza", index=False)
        dicc.to_excel(xw, sheet_name="9_Diccionario", index=False)
        for ws in xw.book.worksheets:
            ws.freeze_panes = "A2"
            for col in ws.columns:
                ancho = max(len(str(c.value or "")) for c in col)
                ws.column_dimensions[col[0].column_letter].width = min(max(10, ancho + 2), 60)
            for c in ws[1]:
                c.font = Font(bold=True, color="FFFFFF")
                c.fill = matplotlib_fill()
    log.info("Excel consolidado: %s", ruta.name)
    return ruta


def matplotlib_fill():
    return PatternFill("solid", fgColor="1F3A5F")


# ----------------------------------------------------------------------------- 6. DASHBOARD
def dashboard(limpio, resumen, kpi):
    plantilla = (BASE / "src" / "dashboard_template.html").read_text(encoding="utf-8")
    datos = {
        "series": {p: g[["anio", "mortalidad_pct"]].values.tolist() for p, g in limpio.groupby("pais")},
        "resumen": resumen.to_dict(orient="records"),
        "kpi": kpi,
    }
    html = plantilla.replace("/*__DATOS__*/null", json.dumps(datos, ensure_ascii=False))
    ruta = OUT / "dashboard_ent.html"
    ruta.write_text(html, encoding="utf-8")
    log.info("Dashboard generado: %s", ruta.name)
    return ruta


# ----------------------------------------------------------------------------- MAIN
def main():
    ap = argparse.ArgumentParser(description="Pipeline BI de mortalidad prematura por ENT")
    ap.add_argument("--entrada", type=Path, default=RAW / "SH.DYN.NCOM.MA.ZS_extraccion.csv")
    args = ap.parse_args()
    crudo = extraer(args.entrada)
    limpio, bitacora = limpiar(crudo)
    resumen, kpi, quinq = analizar(limpio)
    graficar(limpio, resumen, kpi)
    exportar(crudo, limpio, resumen, kpi, quinq, bitacora)
    dashboard(limpio, resumen, kpi)
    log.info("Pipeline finalizado correctamente.")


if __name__ == "__main__":
    main()
