# Proyecto Final BI – Mortalidad prematura por ENT en hombres (30–70 años)

Programa que ejecuta el ciclo de BI: extracción → limpieza → análisis/KPI → gráficas → Excel → dashboard.

## Requisitos
```
pip install pandas numpy matplotlib openpyxl
```

## Ejecución
```
python src/pipeline_ent.py                       # usa data/raw/SH.DYN.NCOM.MA.ZS_extraccion.csv
python src/pipeline_ent.py --entrada <CSV oficial del Banco Mundial>   # actualiza con la versión 2000-2021
python src/riesgo_ent.py                         # casos de prueba del módulo de autoevaluación
```

## Salidas
- `outputs/Base_Datos_Consolidada_ENT.xlsx` – base consolidada (10 hojas)
- `outputs/dashboard_ent.html` – tablero interactivo + autoevaluación (abrir en el navegador)
- `outputs/graficas/` – gráficas G1–G7
- `data/processed/` – tabla de hechos, resumen por país y KPI (JSON)

Fuente: Banco Mundial, indicador SH.DYN.NCOM.MA.ZS (origen OMS GHO). Licencia CC BY 4.0.
El módulo de autoevaluación es orientativo y no constituye diagnóstico médico.
