"""Rutas, imports del motor (sin copiar su lógica) y textos de negocio del dashboard."""

import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="Data Validation extension")  # ruido de openpyxl con la Maestra

DASH_DIR = Path(__file__).resolve().parents[1]
ROOT = DASH_DIR.parent
SCRIPTS = ROOT / "02_scripts"
for _p in (SCRIPTS / "kokai_menu_optimizer_v2", SCRIPTS / "justo_integracion", SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

DATA_DIR = DASH_DIR / "data"
DEFAULT_DATASET = ROOT / "03_entregables" / "ventas_con_costo_oct2026.xlsx"
MAESTRA_PATH = ROOT / "01_datos_originales" / "MAESTRA_KOKAI_COSTOS_PRODUCCION_Abr2026_v5.xlsx"

# El motor se importa tal cual; aquí solo se re-exportan sus constantes.
from kokai_menu_optimizer import (  # noqa: E402
    CLASSES, DEFAULT_BOUND_DELTA, DEFAULT_BOUND_U, DEFAULT_ELASTICITY,
    DEFAULT_MAX_UNITS_DROP, SCENARIOS,
)

# Paleta del dashboard (minimalista). El Excel que genera el script mantiene sus propios colores.
NAVY, SLATE, SILVER, WHITE, ACCENT = "#2d3142", "#4f5d75", "#bfc0c0", "#ffffff", "#ef8354"
# Cuadrantes: paleta validada (lightness, chroma y separación para daltonismo en todos los pares). Contraste
# bajo sobre blanco en verde y amarillo, por eso siempre van con símbolo y etiqueta.
CLASS_COLOR = {"Estrella": "#1baf7a", "Caballo de batalla": "#e0532b", "Puzzle": "#2a78d6", "Perro": "#eda100"}
CLASS_TEXT = {"Estrella": WHITE, "Caballo de batalla": WHITE, "Puzzle": WHITE, "Perro": NAVY}  # texto legible sobre cada color
CLASS_SYMBOL = {"Estrella": "circle", "Caballo de batalla": "square", "Puzzle": "diamond", "Perro": "triangle-up"}
SCENARIO_COLOR = {"Conservador": SILVER, "Base": SLATE, "Optimista": NAVY}

# Nombres cortos de negocio para cada cuadrante (el motor usa los nombres de Kasavana-Smith).
CLASS_LABEL = {"Estrella": "Estrellas", "Caballo de batalla": "Caballos", "Puzzle": "Puzzles", "Perro": "Perros"}
CLASS_INFO = {  # (qué son, qué hacer)
    "Estrella": ("Se venden mucho y dejan buen margen.", "Cuidarlas: no tocar receta ni porción."),
    "Caballo de batalla": ("Se venden mucho, pero dejan poco margen.",
                           "Revisar la porción o subir el precio levemente."),
    "Puzzle": ("Dejan buen margen, pero se venden poco.", "Darles visibilidad en la carta y en las apps."),
    "Perro": ("Se venden poco y dejan poco margen.", "Sacarlos o rediseñarlos."),
}
CLASS_RULE = (
    "Un plato *se vende mucho* si vende al menos el 70 % de lo que vendería un plato promedio de su local. "
    "*Deja buen margen* si deja más pesos por plato (precio sin IVA − costo de receta) que el promedio del local. "
    "Se calcula por separado en cada local, así que un mismo plato puede caer en cuadrantes distintos."
)

SCENARIO_INFO = {
    "Conservador": "Los clientes **reaccionan fuerte** a las alzas de precio: si el precio sube, la venta cae "
                   "bastante. Es el caso más prudente y la mejora que muestra es la menor.",
    "Base": "Reacción **intermedia** de los clientes al precio. Es el escenario de referencia.",
    "Optimista": "Los clientes **casi no notan** alzas pequeñas de precio. Es el caso más favorable y la mejora "
                 "que muestra es la mayor.",
}
RANGE_LOW, RANGE_MID, RANGE_HIGH = "Conservador", "Base", "Optimista"  # extremos del rango y valor central

ASSUMPTION_WARNING = (
    "**Son recomendaciones, no decisiones tomadas.** Se calculan suponiendo cuánto baja la venta cuando sube "
    "el precio (la *elasticidad*). Ese valor **todavía no está medido**: el piloto de elasticidad está "
    "diseñado, pero aún no se ejecuta. Por eso los efectos se muestran como rango."
)

# --- Food cost (método del proyecto: costo de receta ÷ venta neta de Justo) ---------------------------
IVA = 0.19  # los precios de Justo y de la carta incluyen IVA; el costo de receta es neto
FC_META = None  # meta en el mismo método; se fija en la barra lateral (None = por definir)

# Familias de la carta (agrupan las hojas de categoría de la Maestra).
FAMILIA = {
    **{c: "Rolls" for c in ["CALIFORNIA ROLLS", "SPECIALS ROLLS", "CHEESE ROLLS", "VEGGIE ROLLS", "TEMPURA ROLLS",
                            "ORIENTAL ROLLS", "KETO ROLLS", "VEGAN ROLLS", "NIKKEI ROLLS", "ACEVICHADOS", "HOSOMAKI"]},
    "COMBINACIONES": "Tablas y promos",
    "PIQUEOS": "Entradas",
    **{c: "Sashimi, nigiri y ceviches" for c in ["SASHIMI", "CESHIMI", "NIGIRI", "GUNKAN", "TIRADITOS", "CEVICHES"]},
    "GOHAN": "Gohan",
    "EXTRAS": "Extras y salsas",
    **{c: "Bebidas" for c in ["BEBIDAS", "MOCKTAIL", "VINOS Y TRAGOS"]},
    "POSTRES": "Postres",
}
# Nombres legibles para los insumos que más pesan (el resto se muestra tal como viene en la Maestra).
INSUMO_NOMBRE = {
    "Salmon fresco": "Salmón fresco", "Palta hass": "Palta", "Arroz grado 2 carl": "Arroz",
    "Camaron 36/40 pyd": "Camarón", "Queso crema california 10x1,36": "Queso crema", "Huevo pausterizado": "Huevo",
    "Alga marina nori blue mayamoto": "Alga nori", "Mayonesa alacena": "Mayonesa", "Real mayo kraft galon": "Mayonesa",
    "Pechuga de pollo nacional caja": "Pollo", "Atun pieza": "Atún", "Limon sutil": "Limón", "Pulpo": "Pulpo",
    "Panko blanco mayamoto": "Panko", "Cebollin 1 atado 0,5 kg": "Cebollín", "Vinagre de arroz": "Vinagre de arroz",
    "Salmon ahumado": "Salmón ahumado", "Empanada camaron queso": "Empanada camarón queso (compra)",
    "Pasta de aji amarillo cosecha verde frasco": "Ají amarillo", "Carne de jaiba": "Jaiba",
}

PUSH_THRESHOLD = 0.005  # |u| menor a 0,5 % se muestra como «Dejar igual»

DEFAULT_MAXITER = 3000  # con 327 platos, 300 no alcanza para converger (~2 min por escenario con 3000)

DEFAULT_PARAMS = {
    "maxiter": DEFAULT_MAXITER,
    "max_drop": DEFAULT_MAX_UNITS_DROP,
    "bound_delta": tuple(DEFAULT_BOUND_DELTA),
    "bound_u": tuple(DEFAULT_BOUND_U),
}

# --- Parte 2 · Seguimiento, reglas y vigencia ------------------------------------------------------
BASELINE_DATASET = DEFAULT_DATASET  # mes con el que se armó el plan (octubre 2026): contra esto se compara
STATUS = {  # paleta de estado (fija, distinta de la de cuadrantes); siempre va con ícono + texto
    "verde": ("#0ca30c", "●", "En meta"), "amarillo": ("#fab219", "▲", "Atención"), "rojo": ("#d03b3b", "■", "Actuar"),
}
# Umbrales del semáforo, en cambio vs. la línea base (fracciones; las ventas se comparan por día).
SEM_UNIDADES = (-0.03, -0.05)   # unidades de los platos con alza: verde ≥ −3 %, rojo < −5 % → revertir
SEM_TICKET = (0.0, -0.03)       # ticket promedio: verde ≥ base, rojo < −3 %
SEM_VENTA = (-0.02, -0.05)      # venta neta por día: verde ≥ −2 % (lo que permite el modelo), rojo < −5 %
SEM_FC_HOLGURA = 0.003          # food cost: verde si queda a ≤ 0,3 pts de lo que promete el plan
MIN_UNIDADES_PLATO = 10         # bajo esto la caída de un plato es ruido y no se marca

FC_PISO_NUEVO = 0.30            # precio piso de un plato nuevo = costo de receta ÷ 0,30 (neto de IVA)
ALZA_INSUMO_CLAVE = 0.10        # un insumo clave que sube más que esto gatilla revisar la carta
VIGENCIA_MESES = 6              # validez máxima del plan desde el mes de los datos
REVISION_MESES = 3              # revisión de carta por temporada

# Pasos en el panel de Justo. Son de referencia: los nombres exactos de los menús los debe confirmar quien
# administra Justo en Kokai (la documentación pública de Justo no los detalla).
JUSTO_PASOS = {
    "dashboard": [
        "En este dashboard, barra lateral → **Actualizar desde Justo** → «Un mes completo» → elegir el mes → "
        "**Actualizar datos** (tarda un par de minutos).",
        "Volver a esta página: el mes nuevo aparece en «Mes a revisar» y los indicadores se calculan solos.",
    ],
    "ventas_producto": [
        "Entrar al panel de administración de Justo → sección de **reportes de ventas**.",
        "Elegir el rango de fechas del mes (del 1 al último día) y el local (o todos).",
        "Abrir el reporte **por producto** y descargarlo en Excel.",
        "Dejar las columnas Local, Producto, q (unidades) y p (precio promedio con IVA) y subirlo en la barra "
        "lateral → **Subir un Excel manual**, indicando el mes. El costo de receta se cruza solo.",
    ],
    "ticket": [
        "En el mismo reporte de ventas del mes, anotar la **venta total** y el **número de pedidos** (o "
        "«ticket promedio» si el reporte lo trae).",
        "Ticket promedio = venta total ÷ número de pedidos, por local o para los tres juntos.",
        "Si el mes se descargó con «Actualizar desde Justo», el ticket se calcula solo.",
    ],
}
