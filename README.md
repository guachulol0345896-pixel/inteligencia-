# Proyecto ENT - Inteligencia de negocios

Trabajo académico sobre mortalidad prematura por enfermedades no transmisibles y un prototipo orientativo de autoevaluación.

## Entrega del proyecto

El paquete del proyecto se preparó conservando los archivos originales y sustituyendo `outputs/Base_Datos_Consolidada_ENT.xlsx` por el archivo `basededatos.xlsx` enviado por separado.

**Estado de la publicación:** los archivos del proyecto todavía deben añadirse al repositorio. Este README no confirma que la carga del ZIP esté terminada.

## Estructura del paquete

- `src/`: scripts Python y plantilla del dashboard.
- `data/raw/`: datos originales de entrada.
- `data/processed/`: resultados consolidados.
- `outputs/`: dashboard HTML, libro Excel, gráficas y evidencias.

## Ejecución (una vez subidos los archivos)

```bash
pip install pandas numpy matplotlib openpyxl
python src/pipeline_ent.py
python src/riesgo_ent.py
```

El módulo de autoevaluación es un prototipo académico y no sustituye la valoración médica.
