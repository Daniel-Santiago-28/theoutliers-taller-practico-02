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
| Ingreso sin trazabilidad de costo | **USD 12,98 M de 74,57 M (17,4 %)** |
| Transacciones catalogadas con margen unitario negativo | **3.193 de 8.249 (38,7 %)** |
| Antigüedad mediana del último conteo físico de stock | **342 días** |
| Envíos con código de error `999` en lugar de tiempo real | **50** |
| Registros de feedback duplicados | **500 (11,1 %)** |

Cifras reproducibles con `python -m scripts.perfilado_inicial`.

## Estado del proyecto

| Fase | Contenido | Estado |
|---|---|---|
| 0 | Scaffolding, ingesta forense y perfilado de línea base | ✅ Completa |
| 1 | Limpieza, imputación justificada y Health Score | ✅ Completa |
| 2 | Integración, venta fantasma y feature engineering | ⬜ Pendiente |
| 3 | Dashboard Streamlit y resolución de las 5 preguntas | ⬜ Pendiente |
| 4 | Módulo de IA (Groq / Llama-3) y documento de hallazgos | ⬜ Pendiente |

### Resultado de la curaduría (Fase 1)

| Activo | Health Score antes | Después | Mejora |
|---|---:|---:|---:|
| Inventario | 89,75 | 99,54 | +9,79 pp |
| Transacciones | 93,36 | 99,03 | +5,67 pp |
| Feedback | 78,13 | 98,19 | +20,06 pp |

Cero filas eliminadas: la política por defecto **marca y conserva** en lugar de
borrar, de modo que el ingreso total siga siendo trazable hasta el archivo
original. 317 registros quedan excluidos de algún cálculo pero permanecen
consultables y descargables desde el dashboard.

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

# 2. Suite de pruebas (congela la línea base de calidad)
python -m pytest tests/ -v

# 3. Dashboard — pestañas Auditoría y Transparencia operativas
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
| Fecha de corte | `2026-01-31` fija y configurable, no `datetime.now()`, para que el análisis sea determinista y reproducible |
| SKU sin catálogo | Left join; se conservan, se etiquetan y se excluyen solo del margen. Nunca se descartan |
| `Ventas_Web` en `Ciudad_Destino` | Es un canal, no un lugar: se anula la geografía y se marca con bandera, preservando la trazabilidad del ingreso |
| `Satisfaccion_NPS` | Se conserva el crudo y se agrega la segmentación Detractor / Pasivo / Promotor |
| `Lead_Time_Dias` `"25-30 días"` | Punto medio del intervalo (27,5): imputación estándar para datos censurados por intervalo |
| Costos atípicos | Filtro de Tukey (IQR × 1,5) **más un piso de negocio de USD 1**, porque la valla inferior de Tukey es negativa y no detecta el costo de USD 0,05 |
| Media vs mediana | No se decide a mano: se mide la asimetría de cada columna y se aplica la regla de Bulmer (\|a\| < 0,5 → media; si no, mediana). El estadístico queda registrado en la bitácora |
| Nominales casi uniformes | `Categoria` (12,2 % ausente) y `Estado_Envio` (16,8 %) **no se imputan**: sin moda dominante, rellenar inyectaría masa artificial en la dimensión por la que luego se segmenta |
| Duplicados de feedback | **No existen.** Lo que hay es una colisión de llave surrogate: los `Feedback_ID` repetidos apuntan a transacciones y clientes distintos. Se repara la llave en vez de borrar 500 opiniones legítimas |

## Licencia y contexto

Trabajo académico. Los datos de TechLogistics S.A.S. son ficticios y fueron
provistos con defectos deliberados como parte del ejercicio.
