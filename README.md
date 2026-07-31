**Curso:** Fundamentos en Ciencia de Datos — Maestría en Ciencia de Datos y Analítica, EAFIT
**Fecha de entrega real:** 26/07/2026

**Integrantes del equipo:**

| Nombre completo | Cédula         |
| --------------- | -------------- |
| Daniel Amaya Yepes      | 1037646508 |
| Daniel Santiago Cadavid      | 1000646110 |
| Luis Camilo Valencia      | 1037670493 |

**Enlace dashboard en streamlit:** https://theoutliers-taller-practico-02-mcvxjycv3a4mjwh4akzqmm.streamlit.app/

# TechLogistics S.A.S. — Sistema de Soporte a la Decisión (DSS)

Curaduría de datos y dashboard analítico para diagnosticar la erosión de margen
y la caída de lealtad de clientes de TechLogistics S.A.S.

**Challenge 02** · Fundamentos en Ciencia de Datos (Maestría) · Universidad EAFIT
· Periodo 2026-1

---

## El problema

TechLogistics opera tres sistemas que no se hablan entre sí: el ERP de
inventarios, la plataforma logística y el canal de feedback de clientes. La
junta directiva sospecha que la causa raíz de la pérdida de rentabilidad es la
**invisibilidad operativa**, no la demanda.

El perfilado forense de los datos crudos confirma la sospecha y la cuantifica:

| Hallazgo | Magnitud |
|---|---|
| Ventas cuyo SKU no existe en el maestro de inventario | **1.751 de 10.000 (17,5 %)** |
| Ingreso sin trazabilidad de costo | **USD 13,14 M de 75,28 M (17,4 %)** |
| Transacciones catalogadas con margen unitario negativo | **3.234 de 8.239 (39,3 %)** |
| Antigüedad mediana del último conteo físico de stock | **516 días** (relativa a la fecha de ejecución) |
| Envíos con código de error `999` en lugar de tiempo real | **50** |
| Registros de feedback duplicados | **500 (11,1 %)** |

Cifras reproducibles con `python -m scripts.perfilado_inicial`.


### Resultado de la curaduría (Fase 1)

| Activo | Health Score antes | Después | Mejora |
|---|---:|---:|---:|
| Inventario | 89,75 | 99,54 | +9,79 pp |
| Transacciones | 93,40 | 99,11 | +5,71 pp |
| Feedback | 78,13 | 98,22 | +20,09 pp |

Cero filas eliminadas: la política por defecto **marca y conserva** en lugar de
borrar, de modo que el ingreso total siga siendo trazable hasta el archivo
original. 317 registros quedan excluidos de algún cálculo pero permanecen
consultables y descargables desde el dashboard.

### Sola Fuente de Verdad (Fase 2)

`src/integration.py` construye una tabla de 10.000 filas —una por transacción—
uniendo los tres activos. El riesgo central no es unir, es **preservar el
grano**: 767 transacciones acumulan entre 2 y 4 opiniones de clientes, así que
un `merge` directo produciría 10.877 filas e inflaría el ingreso en
**USD 6.539.892 (+8,77 %)**. El feedback se agrega a grano de transacción
*antes* de unirse, y los merges declaran `validate='m:1'` / `'1:1'` para que
cualquier fan-out futuro falle de forma ruidosa.

La reconciliación contra el archivo original cuadra al centavo:
**USD 75.278.947,05** en ambos lados, diferencia 0,00.

### Las cinco preguntas de alta gerencia (Fase 3)

| # | Pregunta | Respuesta | Evidencia |
|---|---|---|---|
| 1 | Fuga de capital | **Ninguna de las dos hipótesis de la junta.** No es producto gancho ni una falla del canal Online: el precio se fija con independencia del costo | ρ = 0,014 (p = 0,217); pérdida de USD 7,66 M repartida entre 878 SKU |
| 2 | Crisis logística | **Ninguna zona requiere cambio de operador porque ninguna es peor.** El problema es del proceso completo | 0 de 10 correlaciones sobreviven a Bonferroni; **60,2 %** de envíos adversos, uniforme |
| 3 | Venta invisible | **Falla de catálogo, no fraude.** Seis criterios independientes coinciden | **USD 13,14 M = 17,45 %** del ingreso; 480 SKU en bloque contiguo |
| 4 | Paradoja de fidelidad | **La paradoja no existe:** ni el stock ni la satisfacción difieren entre categorías. La queja dominante es precio, no calidad | rating p = 0,966; stock p = 0,079; Precio/Valor = 43,7 % de las quejas |
| 5 | Riesgo operativo | **Las bodegas sí operan a ciegas, pero el riesgo aún no se ha cobrado** | **17,1 meses** de mediana sin conteo físico; tickets p = 0,835 |

Tres de las cinco preguntas apuntan a relaciones que el dato no sostiene. En
esos casos el dashboard aplica un **tratamiento de dos niveles**: primero el
ranking que pide el enunciado, con las celdas no significativas atenuadas y el
hallazgo nulo declarado de forma explícita; después el análisis alternativo
sobre las señales que sí portan información.

### Módulo de IA (Fase 4)

`src/ai_insights.py` pide a Llama-3 tres párrafos de recomendación sobre el
recorte que el usuario tiene aplicado. El riesgo de diseño no es técnico sino
de contenido: que el modelo invente cifras o recomiende actuar sobre hallazgos
que ya sabemos que son ruido. Tres defensas:

1. **El modelo no ve los datos, ve un resumen calculado.** Recibe 43 cifras ya
   computadas por `analytics`; no tiene el DataFrame ni puede agregar nada por
   su cuenta, así que toda cifra que use tiene que estar en ese bloque.
2. **El resumen incluye los veredictos estadísticos.** Cada hallazgo viaja con
   su etiqueta de solidez y el prompt de sistema **prohíbe explícitamente**
   recomendar acciones sobre lo marcado como no concluyente. Sin esto, un
   modelo servicial redactaría con toda seguridad *«cambie de operador en
   Barranquilla»* sobre una correlación de 0,039.
3. **Temperatura 0,3 y salida acotada.** Se busca análisis reproducible.

La pestaña ofrece un botón *Auditar exactamente qué recibió el modelo* con el
prompt íntegro y el resumen descargable en JSON, para que cualquier afirmación
sea verificable contra su fuente.

El criterio es el mismo en las cinco: un hallazgo se declara sólido solo si es
**significativo y de tamaño de efecto no trivial**. Con muestras de 8.000 a
10.000 filas el valor p se vuelve trivialmente pequeño, así que separar ambas
condiciones es lo que impide confundir «el test detectó algo» con «esto
importa». El caso más claro es la pregunta 1: la diferencia entre canales tiene
p = 0,0047 pero una V de Cramér de 0,04, y el panel la rotula *Significativo
pero irrelevante*.

## Instalación

Requiere Python 3.11 o superior.

```bash
git clone https://github.com/Daniel-Santiago-28/theoutliers-taller-practico-02.git
cd theoutliers-taller-practico-02

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

### Configuración de la API Key de Groq

La clave **nunca** se versiona ni se escribe en el código. Elija una vía:

```bash
# Opción A — variable de entorno (ejecución local)
cp .env.example .env             # y edite el valor

# Opción B — secretos de Streamlit
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

En Streamlit Community Cloud, cargue `GROQ_API_KEY` en *Settings → Secrets*.
Obtenga una clave gratuita en [console.groq.com/keys](https://console.groq.com/keys).

## Cómo replicar el análisis

```bash
# 1. Perfilado forense de los datos crudos -> docs/perfilado_inicial.md
python -m scripts.perfilado_inicial

# 2. Suite de pruebas completa (287 pruebas, ~75 s)
python -m pytest

# Iteración rápida, sin las pruebas de humo de la app (~10 s)
python -m pytest -m "not smoke"

# 3. Dashboard — 7 pestañas: Visión General, Auditoría, Transparencia,
#    Operaciones, Cliente, Insights de IA y Ficha Técnica
streamlit run app.py
```

**App en la nube:** _pendiente de despliegue._

## Arquitectura

La lógica de datos vive en `src/` y es **independiente de Streamlit**: todo
módulo del núcleo debe poder ejecutarse desde un script o un test sin levantar
la interfaz. `ui/` solo presenta.

```
├── app.py                      # orquestación de la UI
├── src/
│   ├── config.py               # ÚNICA fuente de verdad de decisiones y umbrales
│   ├── ingest.py               # ingesta forense + validación de esquema
│   ├── cleaning.py             # limpieza -> (DataFrame, CleaningLog)
│   ├── audit.py                # Health Score y métricas antes/después
│   ├── integrate.py            # merge, venta fantasma, variables derivadas
│   ├── analytics.py            # una función pura por pregunta de gerencia
│   └── ai_insights.py          # cliente Groq, prompts y manejo de errores
├── ui/                         # sidebar y pestañas del dashboard
├── data/raw/                   # los 3 CSV originales (inmutables)
├── docs/                       # perfilado, informe de hallazgos y capturas
├── scripts/                    # utilidades ejecutables
└── tests/                      # casos de la guía de validación como tests
```

### Alcance de los filtros: 4 de 7 pestañas

El panel lateral filtra por fecha, categoría, bodega, ciudad y canal, y ese
recorte propaga a **Visión General, Operaciones, Cliente e Insights de IA**.
Visión General también responde al interruptor "Incluir venta sin catálogo":
solo muestra cifras (ingreso, margen, unidades), sin veredictos estadísticos,
así que es la puerta de entrada natural para ver el efecto de un filtro antes
de entrar al detalle de cada pregunta.

Las pestañas de **Auditoría, Transparencia y Ficha Técnica lo ignoran a
propósito**: las dos primeras describen la curaduría de los archivos fuente,
que se ejecutó una única vez sobre los tres activos completos —un «Health
Score de las Laptops vendidas por Online» no existe como magnitud, la
limpieza no se hizo por subconjunto—, y Ficha Técnica es un catálogo de
metodología, no un análisis del recorte. Las tres declaran su alcance en
pantalla, y `tests/test_app_wiring.py` congela la decisión: si alguien
intenta pasarles un recorte, la firma cambia y el test falla.

Una consecuencia que conviene tener presente al demostrar la app: **filtrar por
categoría o por bodega excluye necesariamente toda la venta fantasma**, porque
ambos atributos provienen del maestro de inventario en el que esos SKU no
existen. Es correcto, no un error de filtrado.

### Dos decisiones de diseño que vale la pena señalar

**La ingesta es forense.** Los CSV se leen con `dtype=str` y sin interpretación
de nulos, de modo que el DataFrame refleje exactamente lo que hay en disco. Si
se dejara a pandas convertir `"???"` o `"nan"` a `NaN` durante la lectura, el
reporte de calidad "antes" mostraría una nulidad menor a la real y se perdería
la evidencia de qué centinelas usaba cada sistema fuente. Toda coerción ocurre
después, de forma explícita y registrada.

**Toda función de limpieza devuelve `(DataFrame, CleaningLog)`.** Ese log es la
fuente única que alimenta la pestaña de Transparencia, el reporte descargable y
el documento de hallazgos. Sin él, las justificaciones de imputación se
escribirían tres veces y se desincronizarían.

## Decisiones de curaduría

Declaradas en [`src/config.py`](src/config.py) con su justificación:

| Decisión | Criterio adoptado |
|---|---|
| Validación temporal | Contra `datetime.now()`, expuesto como `config.fecha_corte()`. Es una función y no una constante de módulo a propósito: una constante quedaría congelada en el instante del `import` |
| SKU sin catálogo | Left join; se conservan, se etiquetan y se excluyen solo del margen. Nunca se descartan |
| `Ventas_Web` en `Ciudad_Destino` | Es un canal, no un lugar: se anula la geografía y se marca con bandera, preservando la trazabilidad del ingreso |
| `Satisfaccion_NPS` | Se conserva el crudo y se agrega la segmentación Detractor / Pasivo / Promotor |
| `Lead_Time_Dias` `"25-30 días"` | Punto medio del intervalo (27,5): imputación estándar para datos censurados por intervalo |
| Costos atípicos | Filtro de Tukey (IQR × 1,5) **más un piso de negocio de USD 1**, porque la valla inferior de Tukey es negativa y no detecta el costo de USD 0,05 |
| Media vs mediana | No se decide a mano: se mide la asimetría de cada columna y se aplica la regla de Bulmer (\|a\| < 0,5 → media; si no, mediana). El estadístico queda registrado en la bitácora |
| Nominales casi uniformes | `Categoria` (12,2 % ausente) y `Estado_Envio` (16,8 %) **no se imputan**: sin moda dominante, rellenar inyectaría masa artificial en la dimensión por la que luego se segmenta |
| Duplicados de feedback | **No existen.** Lo que hay es una colisión de llave surrogate: los `Feedback_ID` repetidos apuntan a transacciones y clientes distintos. Se repara la llave en vez de borrar 500 opiniones legítimas |
| `Cantidad_Vendida` negativa | Las 100 filas con el centinela `-5` se imputan con la mediana de las demás ventas válidas del mismo `SKU_ID` (respaldo: mediana global si el SKU no tiene ninguna venta válida propia). El costo unitario no se usa como predictor: no correlaciona con la cantidad en este dataset (Spearman ρ ≈ -0,015) |
| `Rating_Producto` fuera de escala | El centinela `99` (30 filas) se imputa con la mediana de las respuestas válidas, no la media: es una escala ordinal Likert (1-5), y la media asumiría distancias iguales entre categorías que la escala no garantiza |
| Feedback con varias opiniones por venta | 767 transacciones reciben entre 2 y 4 `Feedback_ID` distintos. No se elimina ninguna fila (perdería información) ni se promedia en silencio (mezclaría clientes distintos bajo una sola venta): se marca `Feedback_Confiable = False` en cada fila del grupo para que el diagnóstico de fidelidad (pregunta 4) las excluya del análisis de calificación |
| Trazabilidad | Toda corrección deja una bandera booleana **en la propia fila** (`*_Imputado`, `*_Fuera_Escala`, `Cantidad_Vendida_Imputado`, `Feedback_Confiable`, …), no solo una línea en la bitácora: un valor estimado nunca queda indistinguible de uno observado |

## Licencia y contexto

Trabajo académico. Los datos de TechLogistics S.A.S. son ficticios y fueron
provistos con defectos deliberados como parte del ejercicio.
