# Dashboard Kokai — menu engineering y food cost

Para el equipo de Kokai (gerencia): clasificación de platos, recomendaciones de precio y comparación de escenarios, sin tocar Python.

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Qué hace

Navegación en dos partes (barra lateral):

**Parte 1 · Qué decidir ahora**
1. **Resumen**: food cost calculado (receta ÷ venta neta de Justo) vs. meta (en % y $/mes; la meta se fija en la barra lateral), food cost con el plan, ahorro potencial como rango y las 3–5 decisiones recomendadas. Fecha de los datos visible en todas las páginas.
2. **Dónde se va la plata**: food cost por local y por familia de la carta, top 10 platos por gasto en pesos y top insumos (cada receta de la Maestra se expande hasta insumos comprados, incluyendo bases, salsas y combos).
3. **Mapa del menú**: estrellas / caballos / puzzles / perros con qué hacer en cada uno, y la lista de platos por cuadrante con su acción sugerida.
4. **Plan de acción**: plato · acción · precio actual → sugerido por canal (salón, Kokai.cl, UberEats; redondeado a terminación 90) · efecto en food cost y $ · prioridad (hacer ya / probar / opcional). Descarga en Excel.

**Parte 2 · Para que siga sirviendo**
5. **Cómo saber si funcionó**: food cost, unidades de los platos con alza, ticket promedio y venta por día de un mes nuevo contra la línea base (octubre 2026), cada uno con meta, semáforo, qué hacer si sale rojo y pasos para sacarlo de Justo. Lista de platos donde conviene revertir el alza.
6. **Reglas para decisiones futuras**: calculadora de precio de un plato nuevo (costo ÷ 0,30, con IVA, a precio de carta, vs. competencia y platos de la misma categoría), exposición a insumos («si el salmón sube 10 %…») y cuándo revisar la carta.
7. **Supuestos y vigencia**: fecha de vencimiento (6 meses desde el mes de los datos) y los supuestos en simple, incluidos los platos con costo estimado y la fecha de los precios de insumos de la Maestra.

**Para revisar un mes nuevo**: barra lateral → Actualizar desde Justo → «Un mes completo». La descarga guarda también pedidos y venta por local, con lo que el ticket promedio se calcula solo. Un Excel subido a mano puede venir sin columna `c` (se cruza con la Maestra) y se le indica el mes; su ticket se ingresa a mano y queda en `data/linea_base.json`. Los umbrales del semáforo y los pasos en Justo están en `config.py`.

**Técnico · Avanzado**: parámetros del optimizador, los tres escenarios tal como los entrega el modelo, calidad de datos.

### Cómo se pasa del optimizador al plan (`analisis.py`)

- Se usa el escenario **Base** como decisión, una por plato y local, tal como la entrega el modelo.
- Las alzas se redondean a precio de carta y el efecto se **re-evalúa con esos precios** bajo las tres elasticidades: Conservador y Optimista dan el rango del resumen; Base, el valor central.
- Todo se mide sobre **venta neta** (precio ÷ 1,19); el costo de receta ya es neto.
- El food cost es el **calculado con el método del proyecto** (receta ÷ venta neta); no se usa el reportado por Kokai.
- Prioridad: *hacer ya* = los cambios que juntos explican el 80 % de la baja del food cost (sin estrellas); *probar* = alzas en estrellas y otras alzas con efecto visible; *opcional* = el resto.

## Datos

| Origen | Cómo |
|---|---|
| Al abrir | Última descarga de Justo guardada en `data/`; si no hay, `03_entregables/ventas_con_costo_oct2026.xlsx`. |
| **Actualizar desde Justo** (barra lateral) | Corre `justo_fetch_sales.fetch_sales` → `join_ventas_costos.build_dataset` con progreso por local y página. Guarda `data/ventas_con_costo_<AAAAMMDD_HHMM>.xlsx` + un `.json` con el período y los productos excluidos. Nunca pisa archivos anteriores. Si falla (sin token/storeId, sin red), muestra el motivo y sigue con el dataset anterior. |
| **Subir un Excel manual** | Columnas `Local, Producto, q, p, c`. Si no calza, muestra qué falta. |
| Selector «Dataset activo» | Vuelve a cualquier dataset ya guardado sin llamar a la API. |

**Para que «Actualizar» funcione** hay que completar en `02_scripts/justo_integracion/.env` el `JUSTO_API_TOKEN` y descomentar `JUSTO_STORE_ID_PENALOLEN`, `JUSTO_STORE_ID_VITACURA`, `JUSTO_STORE_ID_NUNOA`.

**Período de un archivo sin metadata**: crear `03_entregables/ventas_con_costo_oct2026.json` con `{"desde": "AAAA-MM-DD", "hasta": "AAAA-MM-DD", "dias": 30}` para que el encabezado lo muestre.

## La optimización es lenta (por diseño, no corre sola)

Con ~330 platos el solver (SLSQP, ~650 variables) tarda unos **2 min por escenario** con `maxiter=3000` (con 300 no converge).

- Corre **en segundo plano** (`jobs.py`) para no congelar la app; se puede seguir navegando.
- Cada escenario se **guarda en disco** (`data/cache/`), con clave = contenido del dataset + escenario + parámetros. Reabrir la app o volver a un dataset anterior es instantáneo.
- Se lanza con el botón **Calcular recomendaciones**, automáticamente tras actualizar/subir datos, o al «Recalcular» en Avanzado. Cambiar filtros, pestañas o escenario **nunca** recalcula.
- Si un escenario no converge, se avisa en la UI y sus números se marcan como poco confiables.

## Estructura

```
app.py                      entrada: sidebar (datos), carga compartida, navegación por partes
kokai_dashboard/
  config.py                 rutas, import del motor, textos de negocio, colores, IVA, meta, familias
  context.py                datos compartidos por todas las páginas (cacheados)
  maestra.py                SKU/categoría, precios por canal y desglose de recetas desde la Maestra
  analisis.py               food cost por local/familia/plato/insumo, plan, exposición a insumos, precio piso
  seguimiento.py            indicadores mensuales vs. línea base y semáforo
  datasets.py               listado, metadata (fecha/período), guardado, validación de uploads
  pipeline.py               Actualizar datos: Justo → cruce → dataset nuevo
  engine.py                 clasificación cacheada + resultados en disco
  jobs.py                   cálculo en segundo plano
  tables.py / charts.py / export.py / fmt.py
  views/                    resumen, plata, mapa, plan (Parte 1) · funciono, reglas, supuestos (Parte 2) · avanzado, calculo
data/                       datasets descargados (+ .json) y cache/ de resultados
```

Gráficos con **Plotly**: hover con el nombre del plato, líneas de umbral y facetas por local con poco código.

## Publicado en Streamlit Community Cloud

Gratis, con los procesos de fondo funcionando. Hugging Face Spaces con Docker ya exige PRO (nov-2026), por eso no se usa.

- **Código** → repo privado de GitHub `iCastr0/kokai-dashboard` (lista blanca: sin Excels ni `.env`). Streamlit Cloud redespliega con cada push.
- **Datos** → dataset privado de Hugging Face `iCastr0/kokai-datos` (gratis): Maestra, entregable de octubre y todo `data/`. El disco de Streamlit Cloud se borra al reiniciar, así que `kokai_dashboard/storage.py` baja este repo al arrancar y le sube en segundo plano cada descarga de Justo, carga manual, ticket y resultado. Sin `HF_DATA_REPO` (en local) no hace nada.

```bash
../deploy/publicar.sh            # sube el código a GitHub (y crea el repo la primera vez)
../deploy/publicar.sh secretos   # imprime el TOML para Settings → Secrets de la app
```

Secretos: `JUSTO_*`, `APP_PASSWORD` (contraseña al entrar; sin ella no se pide), `HF_DATA_REPO` y `HF_TOKEN` (token de Hugging Face con escritura solo en el dataset). La app se duerme tras ~12 h sin visitas; al despertar recupera todo desde el dataset.
