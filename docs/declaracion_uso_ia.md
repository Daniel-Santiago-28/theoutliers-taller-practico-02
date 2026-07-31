# Declaración de Uso de Inteligencia Artificial

**Proyecto:** Sistema de Soporte a la Decisión — TechLogistics S.A.S. (Challenge 02)
**Equipo:** Daniel Amaya Yepes, Daniel Santiago Cadavid, Luis Camilo Valencia

---

## Resumen

Este proyecto se construyó con la asistencia de **Claude (Anthropic)**, a
través de Claude Code, como herramienta de generación de código y
documentación. **El código —ingesta, limpieza, integración, análisis
estadístico, dashboard y pruebas— fue construido con IA.** Lo que no fue
generado ni aceptado sin supervisión es el criterio: cada resultado, cada
prueba, cada conclusión de negocio y cada accionable del informe de
hallazgos fue **revisado y refinado por el equipo** antes de darse por
válido.
---

## Qué se construyó con IA

- **Los seis módulos de `src/`** (`ingest.py`, `cleaning.py`, `audit.py`,
  `integration.py`, `analytics.py`, `ai_insights.py`) y el dashboard
  completo en `ui/`.
- **La suite de pruebas** (288 pruebas en `tests/`), incluidas las pruebas
  de humo con `AppTest` de Streamlit.
- **La documentación**: `README.md`, `docs/perfilado_inicial.md`,
  `docs/informe_hallazgos.md`, la pestaña *Ficha Técnica* del dashboard.
- Las justificaciones estadísticas de primera versión (por qué media o
  mediana, por qué Kruskal-Wallis y no ANOVA, por qué Bonferroni).

## Qué hizo el equipo, no la IA

La asistencia de IA en este proyecto fue **dirigida**, no autónoma.

- **Las reglas de negocio las definió el equipo.** Cuando se
  decidió cómo tratar el feedback de clientes que se repite por
  transacción, la instrucción fue explícita: *"NO eliminar ni promediar en
  silencio, marcar con la bandera `Feedback_Confiable = False`"*, con su
  justificación de negocio ya redactada por el equipo. La IA implementó esa
  decisión; no la propuso.
- **Las estrategias de imputación se cuestionaron y se ajustaron.** La
  primera versión de la limpieza dejaba `Cantidad_Vendida` sin imputar; el
  equipo pidió explícitamente apoyarse en el costo, se discutió la
  evidencia (el costo no correlaciona con la cantidad, ρ ≈ -0,015) y se
  acordó la estrategia final —mediana por SKU— antes de tocar una sola
  línea de código. Lo mismo ocurrió con `Rating_Producto`: el equipo pidió
  mediana en vez de dejar que la regla automática de Bulmer decidiera.
- **Los hallazgos adicionales partieron de preguntas del equipo, no de la
  IA.** La prueba de si el NPS medio difiere entre bodegas (complemento de
  la pregunta 5).
- **El informe de hallazgos se revisó antes de publicarse.** El equipo tomó
  las capturas reales del dashboard, verificó que las cifras del texto
  coincidieran con lo que la aplicación muestra, y encontró y corrigió
  diferentes errores en `docs/informe_hallazgos.md` antes de aceptar la
  versión final en PDF.
- **Ninguna publicación fue autónoma.** Cada `git push` al repositorio
  remoto ocurrió únicamente tras una instrucción explícita del equipo.
- **Cada cambio se verificó, no se asumió.** Todo ajuste al código pasó por
  la suite de pruebas (270 → 288 pruebas a lo largo del proyecto) antes de
  considerarse terminado.
- **Pruebas funcionales del dashboard.** El equipo revisó meticulosamente
y analizó cada pestaña del dashboard, utilizando todas las funcionalidades
allí dispuestas y revisando la coherencia y consistencia del mismo. Además
de buscar errores o bugs entre las pestañas.