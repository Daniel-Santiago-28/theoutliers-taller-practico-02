# Perfilado forense de datos crudos — TechLogistics S.A.S.

Línea base **ANTES** de cualquier limpieza. Generado por `scripts/perfilado_inicial.py`.

> Los datos se leen sin coerción de tipos ni interpretación de nulos, para que las métricas reflejen exactamente lo que hay en disco.

## Dataset: `inventario` — 2,500 filas x 8 columnas

| Columna | Distintos | Vacíos | Centinelas | % ausencia real | No numéricos |
|---|---:|---:|---:|---:|---:|
| `SKU_ID` | 2,500 | 0 | 0 | 0.0% | 2,500 |
| `Categoria` | 8 | 0 | 305 | 12.2% | 2,500 |
| `Stock_Actual` | 1,398 | 100 | 0 | 4.0% | 100 |
| `Costo_Unitario_USD` | 2,482 | 0 | 0 | 0.0% | 0 |
| `Punto_Reorden` | 200 | 0 | 0 | 0.0% | 0 |
| `Lead_Time_Dias` | 6 | 0 | 403 | 16.12% | 1,290 |
| `Bodega_Origen` | 6 | 0 | 0 | 0.0% | 2,500 |
| `Ultima_Revision` | 679 | 0 | 0 | 0.0% | 2,500 |

### Valores distintos en columnas de baja cardinalidad

- **Categoria** (8 valores): `'Laptops'`=329, `'Monitores'`=327, `'Smartphones'`=314, `'Tablets'`=309, `'Accesorios'`=307, `'smart-phone'`=306, `'???'`=305, `'LAPTOP'`=303
- **Lead_Time_Dias** (6 valores): `'25-30 días'`=454, `'Inmediato'`=433, `'10'`=419, `'nan'`=403, `'5'`=399, `'3'`=392
- **Bodega_Origen** (6 valores): `'norte'`=437, `'Sur'`=436, `'BOD-EXT-99'`=424, `'ZONA_FRANCA'`=408, `'Norte'`=407, `'Occidente'`=388

### Duplicados

- Filas idénticas completas: **0**
- Repeticiones de la llave `SKU_ID`: **0** (2,500 valores únicos en 2,500 filas)

## Dataset: `transacciones` — 10,000 filas x 10 columnas

| Columna | Distintos | Vacíos | Centinelas | % ausencia real | No numéricos |
|---|---:|---:|---:|---:|---:|
| `Transaccion_ID` | 10,000 | 0 | 0 | 0.0% | 10,000 |
| `SKU_ID` | 2,889 | 0 | 0 | 0.0% | 10,000 |
| `Fecha_Venta` | 500 | 0 | 0 | 0.0% | 10,000 |
| `Cantidad_Vendida` | 15 | 0 | 0 | 0.0% | 0 |
| `Precio_Venta_Final` | 9,737 | 0 | 0 | 0.0% | 0 |
| `Costo_Envio` | 5,895 | 834 | 0 | 8.34% | 834 |
| `Tiempo_Entrega_Real` | 30 | 0 | 0 | 0.0% | 0 |
| `Estado_Envio` | 6 | 1,683 | 0 | 16.83% | 10,000 |
| `Ciudad_Destino` | 8 | 0 | 0 | 0.0% | 10,000 |
| `Canal_Venta` | 4 | 0 | 0 | 0.0% | 10,000 |

### Valores distintos en columnas de baja cardinalidad

- **Cantidad_Vendida** (15 valores): `'13'`=789, `'5'`=765, `'12'`=743, `'4'`=726, `'3'`=717, `'7'`=717, `'9'`=695, `'14'`=688, `'8'`=684, `'11'`=684, `'1'`=683, `'6'`=679, `'2'`=672, `'10'`=658, `'-5'`=100
- **Estado_Envio** (6 valores): `'Retrasado'`=1,757, `'Entregado'`=1,684, `''`=1,683, `'Devuelto'`=1,645, `'En Camino'`=1,628, `'Perdido'`=1,603
- **Ciudad_Destino** (8 valores): `'Ventas_Web'`=1,290, `'BOG'`=1,267, `'Bogotá'`=1,261, `'Cali'`=1,256, `'Bucaramanga'`=1,250, `'Medellín'`=1,234, `'MED'`=1,223, `'Barranquilla'`=1,219
- **Canal_Venta** (4 valores): `'Físico'`=2,532, `'Online'`=2,518, `'WhatsApp'`=2,510, `'App'`=2,440

### Duplicados

- Filas idénticas completas: **0**
- Repeticiones de la llave `Transaccion_ID`: **0** (10,000 valores únicos en 10,000 filas)

## Dataset: `feedback` — 4,500 filas x 9 columnas

| Columna | Distintos | Vacíos | Centinelas | % ausencia real | No numéricos |
|---|---:|---:|---:|---:|---:|
| `Feedback_ID` | 4,000 | 0 | 0 | 0.0% | 4,500 |
| `Transaccion_ID` | 3,623 | 0 | 0 | 0.0% | 4,500 |
| `Rating_Producto` | 6 | 0 | 0 | 0.0% | 0 |
| `Rating_Logistica` | 5 | 0 | 0 | 0.0% | 0 |
| `Comentario_Texto` | 7 | 0 | 1,288 | 28.62% | 4,500 |
| `Recomienda_Marca` | 4 | 0 | 1,119 | 24.87% | 4,500 |
| `Ticket_Soporte_Abierto` | 4 | 0 | 0 | 0.0% | 2,243 |
| `Edad_Cliente` | 68 | 0 | 0 | 0.0% | 0 |
| `Satisfaccion_NPS` | 1,803 | 0 | 0 | 0.0% | 0 |

### Valores distintos en columnas de baja cardinalidad

- **Rating_Producto** (6 valores): `'5'`=932, `'1'`=922, `'3'`=903, `'2'`=876, `'4'`=837, `'99'`=30
- **Rating_Logistica** (5 valores): `'3'`=922, `'1'`=919, `'5'`=906, `'4'`=901, `'2'`=852
- **Comentario_Texto** (7 valores): `'Excelente'`=677, `'Lento'`=668, `'N/A'`=657, `'Dañado'`=647, `'---'`=631, `'No volvería'`=624, `'Precio justo'`=596
- **Recomienda_Marca** (4 valores): `'SI'`=1,162, `'NO'`=1,142, `'N/A'`=1,119, `'Maybe'`=1,077
- **Ticket_Soporte_Abierto** (4 valores): `'Sí'`=1,158, `'1'`=1,140, `'0'`=1,117, `'No'`=1,085

### Duplicados

- Filas idénticas completas: **0**
- Repeticiones de la llave `Feedback_ID`: **500** (4,000 valores únicos en 4,500 filas)

----------------------------------------------------------------------

## Integridad referencial entre sistemas

- SKU únicos en el maestro de inventario: **2,500**
- SKU únicos con ventas: **2,889**
- SKU vendidos que NO existen en el maestro: **480**
- Transacciones afectadas (ventas fantasma): **1,751** de 10,000 (**17.51%**)
- Rango de SKU huérfanos: `PROD-3500` .. `PROD-4000`
- Rango de SKU catalogados: `PROD-1000` .. `PROD-3499`
- Huérfanos por encima del SKU máximo catalogado: **480/480** (100.0%)
- Feedback que referencia transacciones inexistentes: **0** filas (0 IDs distintos)
- Cobertura de feedback sobre ventas: **36.23%** de las transacciones tiene al menos una opinión

----------------------------------------------------------------------

## Validación temporal

Fecha de corte declarada: **2026-01-31**

- **Fecha_Venta**: rango 2024-09-23 .. 2026-02-04 | no parseables: **0** | posteriores al corte: **75**
- **Ultima_Revision**: rango 2024-03-04 .. 2026-01-31 | no parseables: **0** | posteriores al corte: **0**
- Antigüedad de la última revisión de stock (días): mín 0, mediana 342, máx 698