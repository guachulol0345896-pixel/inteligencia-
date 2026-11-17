"""
Módulo piloto de autoevaluación de riesgo de ENT (uso orientativo / académico).

IMPORTANTE: el puntaje NO es un diagnóstico ni reemplaza la valoración médica.
Los pesos son una simplificación pedagógica de factores de riesgo reconocidos por la
OMS (edad, tabaco, IMC, inactividad física, alcohol, antecedentes, hipertensión y diabetes).
La misma lógica está implementada en JavaScript en outputs/dashboard_ent.html.
"""
from __future__ import annotations
from dataclasses import dataclass, field

SINTOMAS_ALERTA = {
    "dolor_toracico": "Dolor u opresión en el pecho",
    "disnea": "Falta de aire con esfuerzos leves",
    "poliuria_polidipsia": "Sed o ganas de orinar excesivas",
    "tos_persistente": "Tos de más de 3 semanas",
    "perdida_peso": "Pérdida de peso sin explicación",
}


@dataclass
class Autoevaluacion:
    edad: int
    peso_kg: float
    talla_cm: float
    fumador: bool = False
    actividad_fisica: str = "moderado"      # sedentario | moderado | activo
    consumo_alcohol: str = "nunca"          # nunca | ocasional | frecuente
    antecedente_familiar: bool = False
    hipertension: bool = False
    diabetes: bool = False
    sintomas: list[str] = field(default_factory=list)

    @property
    def imc(self) -> float:
        return round(self.peso_kg / (self.talla_cm / 100) ** 2, 1)


def calcular_riesgo(e: Autoevaluacion) -> dict:
    if not 30 <= e.edad <= 70:
        raise ValueError("El piloto está dirigido a personas de 30 a 70 años.")
    factores = {}
    factores["edad"] = 0 if e.edad < 40 else 10 if e.edad < 50 else 20 if e.edad < 60 else 30
    factores["tabaco"] = 15 if e.fumador else 0
    factores["imc"] = 0 if e.imc < 25 else 5 if e.imc < 30 else 10
    factores["actividad_fisica"] = {"sedentario": 10, "moderado": 4, "activo": 0}[e.actividad_fisica]
    factores["alcohol"] = {"frecuente": 8, "ocasional": 2, "nunca": 0}[e.consumo_alcohol]
    factores["antecedente_familiar"] = 7 if e.antecedente_familiar else 0
    factores["hipertension"] = 10 if e.hipertension else 0
    factores["diabetes"] = 10 if e.diabetes else 0
    puntaje = min(sum(factores.values()), 100)
    nivel = "Bajo" if puntaje < 25 else "Moderado" if puntaje < 50 else "Alto"
    alerta = [SINTOMAS_ALERTA[s] for s in e.sintomas if s in SINTOMAS_ALERTA]
    if alerta:
        recomendacion = "Consulta médica prioritaria: reporta síntomas de alerta."
    elif nivel == "Alto":
        recomendacion = "Agenda un chequeo preventivo en tu EPS en el próximo mes."
    elif nivel == "Moderado":
        recomendacion = "Inscríbete en un programa de prevención (actividad física, nutrición o cesación de tabaco)."
    else:
        recomendacion = "Mantén tus hábitos y repite la autoevaluación en 12 meses."
    principales = sorted(((k, v) for k, v in factores.items() if v > 0), key=lambda kv: -kv[1])[:3]
    return {"puntaje": puntaje, "nivel": nivel, "imc": e.imc, "factores": factores,
            "principales_factores": [k for k, _ in principales],
            "sintomas_alerta": alerta, "recomendacion": recomendacion}


if __name__ == "__main__":
    casos = [
        Autoevaluacion(edad=35, peso_kg=72, talla_cm=176, actividad_fisica="activo"),
        Autoevaluacion(edad=52, peso_kg=88, talla_cm=172, fumador=True, actividad_fisica="sedentario",
                       consumo_alcohol="ocasional", antecedente_familiar=True),
        Autoevaluacion(edad=64, peso_kg=95, talla_cm=170, fumador=True, actividad_fisica="sedentario",
                       consumo_alcohol="frecuente", hipertension=True, diabetes=True, sintomas=["disnea"]),
    ]
    for i, c in enumerate(casos, 1):
        r = calcular_riesgo(c)
        print(f"Caso {i}: edad={c.edad} IMC={r['imc']} -> puntaje={r['puntaje']} nivel={r['nivel']} | "
              f"factores={r['principales_factores']} | {r['recomendacion']}")
