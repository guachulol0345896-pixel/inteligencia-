# Proyecto ENT - Inteligencia de negocios

Proyecto académico de análisis de mortalidad prematura por enfermedades no transmisibles en Colombia y países de referencia. Incluye scripts Python para ETL, indicadores KPI, gráficas y un tablero HTML con un prototipo de autoevaluación orientativa.

## Archivos
- `src/`: programa de extracción, limpieza, análisis y autoevaluación.
- `data/raw/`: datos de entrada.
- `data/processed/`: resultados procesados.
- `outputs/dashboard_ent.html`: dashboard para abrir en un navegador.
- `outputs/Base_Datos_Consolidada_ENT.xlsx`: archivo Excel de base de datos, sustituido por la versión entregada aparte por el equipo.

## Requisitos y ejecución
```bash
pip install pandas numpy matplotlib openpyxl
python src/pipeline_ent.py
python src/riesgo_ent.py
```

El módulo de autoevaluación es un prototipo académico y no sustituye una valoración médica.

Fuente de los indicadores: Banco Mundial, SH.DYN.NCOM.MA.ZS (origen OMS).
