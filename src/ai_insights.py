"""Módulo de recomendación estratégica con Groq (Llama-3).

El diseño se organiza alrededor de un único riesgo: que el modelo invente
cifras o recomiende actuar sobre hallazgos que ya sabemos que son ruido.

Tres defensas contra eso:

1. **El modelo no ve los datos, ve un resumen calculado.** ``construir_resumen``
   produce un diccionario con cifras ya computadas por ``src.analytics``. El
   modelo no recibe el DataFrame ni puede agregar nada por su cuenta, así que
   toda cifra que use tiene que estar en ese bloque.
2. **El resumen incluye los veredictos estadísticos.** Cada hallazgo viaja con
   su etiqueta de solidez, y el prompt de sistema prohíbe explícitamente
   recomendar acciones sobre lo marcado como no concluyente. Sin esto, un
   modelo servicial redactaría con toda seguridad "cambie de operador en
   Barranquilla" sobre una correlación de 0,039.
3. **Temperatura baja y salida acotada.** Se busca análisis reproducible, no
   creatividad.

La clave de API nunca vive en el código: se lee de ``st.secrets`` o de la
variable de entorno ``GROQ_API_KEY``.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field

import pandas as pd

from src import analytics, config

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Errores de dominio
# --------------------------------------------------------------------------


class ErrorIA(Exception):
    """Error base del módulo de IA. Siempre trae un mensaje presentable."""

    def __init__(self, mensaje: str, sugerencia: str = ""):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.sugerencia = sugerencia


class ClaveNoConfigurada(ErrorIA):
    """No hay GROQ_API_KEY disponible en secretos ni en el entorno."""


class ErrorAutenticacion(ErrorIA):
    """La clave existe pero el servicio la rechaza."""


class LimiteDeUso(ErrorIA):
    """Se agotó la cuota o se excedió el límite de peticiones."""


class TiempoAgotado(ErrorIA):
    """El servicio no respondió dentro del plazo configurado."""


class ModeloNoDisponible(ErrorIA):
    """El identificador de modelo no existe o fue retirado."""


class ServicioNoDisponible(ErrorIA):
    """Fallo de red o del lado de Groq."""


# --------------------------------------------------------------------------
# El prompt
# --------------------------------------------------------------------------

# Se expone como constante de módulo a propósito: es el artefacto que más se
# ajusta durante el desarrollo y debe poder revisarse y editarse sin leer la
# lógica que lo rodea.

PROMPT_SISTEMA = """\
Eres un consultor senior especializado en retail tecnológico. Presentas \
hallazgos ante la junta directiva de TechLogistics S.A.S., una cadena que \
está perdiendo margen y lealtad de clientes.

REGLAS ABSOLUTAS SOBRE LOS DATOS
1. Usa exclusivamente las cifras del bloque DATOS. Toda cifra que menciones \
debe aparecer literalmente ahí.
2. No inventes, estimes, redondees hacia otro valor ni extrapoles ningún \
número que no esté en DATOS. Si te falta un dato para sostener una \
afirmación, no hagas la afirmación.
3. Respeta los veredictos estadísticos. Cuando un hallazgo aparezca marcado \
como "Sin evidencia" o "Significativo pero irrelevante", te está PROHIBIDO \
recomendar una acción basada en él. En su lugar, advierte que la empresa hoy \
no puede medir eso y que arreglar la medición es el primer paso.
4. No menciones nombres de columnas, código, ni pruebas estadísticas por su \
nombre técnico. Traduce todo a lenguaje de negocio. Puedes decir "no es \
distinguible del azar", pero no "el p-valor es 0,43".
5. El análisis corresponde solo al recorte de datos descrito. No generalices \
a la operación completa si el recorte es parcial.

FORMATO DE SALIDA
Exactamente tres párrafos, separados por una línea en blanco. Sin títulos, \
sin viñetas, sin numeración, sin preámbulo y sin frase de cierre.

Párrafo 1 — Diagnóstico. La fuga de dinero más grande del recorte, con su \
cifra en dólares y su causa raíz.
Párrafo 2 — Advertencia. Qué NO sostienen los datos, y por qué tomar una \
decisión costosa sobre eso destruiría valor.
Párrafo 3 — Plan de acción. La medida prioritaria, qué área debe ejecutarla \
y qué se espera recuperar.

Escribe en español, en tono ejecutivo y directo, sin adjetivos de relleno. \
Máximo 120 palabras por párrafo."""

PLANTILLA_USUARIO = """\
DATOS

{recorte}

VOLUMEN DEL RECORTE
- Transacciones analizadas: {transacciones}
- Ingreso del recorte: USD {ingreso}
- Participación sobre el ingreso total: {pct_ingreso} %

HALLAZGO 1 — RENTABILIDAD
- SKU que se venden con pérdida: {p1_skus} de {p1_skus_total} \
({p1_pct_skus} %)
- Pérdida acumulada: USD {p1_perdida}
- Ventas con margen negativo: {p1_pct_trx} % de las transacciones
- Erosión sobre la utilidad de los productos rentables: {p1_erosion} %
- Ventas deficitarias que ya perdían dinero antes de pagar el transporte: \
{p1_antes_flete} %
- Relación entre el precio de venta y el costo de compra: {p1_pricing_valor} \
→ veredicto: {p1_pricing_veredicto}
- Hipótesis "pérdida deliberada para ganar volumen" → veredicto: \
{p1_volumen_veredicto}
- Hipótesis "falla de precios del canal Online" → veredicto: \
{p1_canal_veredicto}
- Tasa de ventas deficitarias por canal: {p1_por_canal}

HALLAZGO 2 — LOGÍSTICA
- Envíos que terminan retrasados, perdidos o devueltos: {p2_adversa} % \
(sobre {p2_con_estado} envíos con estado registrado)
- Días de entrega, mediana: {p2_mediana} · percentil 90: {p2_p90}
- Relaciones entre demora y satisfacción que resisten el control por \
comparaciones múltiples: {p2_signif} de {p2_evaluadas}
- Diferencia de la tasa de fallo entre ciudades → veredicto: \
{p2_adversa_veredicto}
- Diferencia del tiempo de entrega entre ciudades → veredicto: \
{p2_tiempo_veredicto}
- Tasa de fallo por ciudad: {p2_por_ciudad}

HALLAZGO 3 — VENTA SIN CATÁLOGO
- Ingreso de productos que se venden pero no están registrados en el \
inventario: USD {p3_ingreso} ({p3_pct} % del ingreso del recorte)
- Productos involucrados: {p3_skus} · Transacciones: {p3_trx}
- Utilidad que no puede auditarse sobre ese ingreso: USD {p3_margen}
- Origen diagnosticado: {p3_origen}

HALLAZGO 4 — CLIENTE Y CATEGORÍAS
- Diferencia de satisfacción entre categorías → veredicto: \
{p4_sentimiento_veredicto}
- Diferencia de nivel de inventario entre categorías → veredicto: \
{p4_stock_veredicto}
- Motivo dominante de los reclamos: {p4_causa} ({p4_causa_pct} % de las \
quejas con causa identificada)
- Reparto de los motivos de reclamo: {p4_reparto}

HALLAZGO 5 — CONTROL DE INVENTARIO
- Tiempo sin conteo físico del inventario, mediana: {p5_meses} meses
- Antigüedad máxima observada: {p5_max} días
- Relación entre desatención del inventario y reclamos → veredicto: \
{p5_correlacion_veredicto}
- Diferencia de reclamos entre bodegas → veredicto: {p5_tickets_veredicto}
- Bodegas sin nomenclatura regional estándar: {p5_no_estandar} de \
{p5_bodegas}

Redacta ahora los tres párrafos."""


# --------------------------------------------------------------------------
# Construcción del resumen que ve el modelo
# --------------------------------------------------------------------------


@dataclass
class ResultadoIA:
    """Salida del módulo, lista para presentarse en la interfaz."""

    parrafos: list[str]
    modelo: str
    tokens_entrada: int = 0
    tokens_salida: int = 0
    resumen_enviado: dict = field(default_factory=dict)
    prompt_usuario: str = ""

    @property
    def texto(self) -> str:
        return "\n\n".join(self.parrafos)


def _formatear_tabla(df: pd.DataFrame, columna_clave: str,
                     columna_valor: str, sufijo: str = " %") -> str:
    """Serializa una tabla pequeña como texto plano legible por el modelo."""
    if df.empty or columna_clave not in df or columna_valor not in df:
        return "no disponible"
    partes = [f"{fila[columna_clave]} {fila[columna_valor]:.1f}{sufijo}"
              for _, fila in df.iterrows()]
    return "; ".join(partes)


def construir_resumen(
    recorte: pd.DataFrame, descripcion_filtro: str,
    ingreso_total_operacion: float | None = None,
    diagnostico_fantasma: dict | None = None,
) -> dict:
    """Calcula el resumen estadístico del recorte que verá el modelo.

    Es la frontera de confianza del módulo: **todo** lo que el modelo puede
    decir tiene que salir de aquí. Si una cifra no está en este diccionario, no
    existe para el modelo.

    Args:
        recorte: SSOT ya filtrada por la selección del usuario.
        descripcion_filtro: Texto legible del recorte aplicado.
        ingreso_total_operacion: Ingreso sin filtrar, para dar contexto de
            participación. Si es None se usa el del propio recorte.
        diagnostico_fantasma: Diagnóstico de seis criterios de la Fase 2.

    Returns:
        Diccionario de cifras y veredictos, serializable y auditable.

    Raises:
        ValueError: Si el recorte está vacío.
    """
    if recorte.empty:
        raise ValueError(
            "El recorte no contiene transacciones. Amplíe los filtros antes "
            "de solicitar el análisis de IA.")

    q1 = analytics.analizar_fuga_capital(recorte)
    q2 = analytics.analizar_crisis_logistica(recorte)
    q3 = analytics.analizar_venta_invisible(recorte, diagnostico_fantasma)
    q4 = analytics.analizar_paradoja_fidelidad(recorte)
    q5 = analytics.analizar_riesgo_operativo(recorte)

    ingreso = float(recorte["Ingreso_Bruto"].sum())
    referencia = ingreso_total_operacion or ingreso

    return {
        "recorte": descripcion_filtro,
        "transacciones": f"{len(recorte):,}",
        "ingreso": f"{ingreso:,.0f}",
        "pct_ingreso": f"{100 * ingreso / referencia:.1f}" if referencia
        else "100,0",

        "p1_skus": f"{q1.kpis.get('skus_con_perdida', 0):,}",
        "p1_skus_total": f"{q1.kpis.get('skus_analizados', 0):,}",
        "p1_pct_skus": f"{q1.kpis.get('pct_skus_con_perdida', 0):.1f}",
        "p1_perdida": f"{q1.kpis.get('perdida_total_usd', 0):,.0f}",
        "p1_pct_trx": f"{q1.kpis.get('pct_trx_con_perdida', 0):.1f}",
        "p1_erosion": f"{q1.kpis.get('erosion_pct', 0):.1f}",
        "p1_antes_flete": f"{q1.kpis.get('pct_perdida_antes_del_flete', 0):.1f}",
        "p1_pricing_valor": _describir_relacion(q1.veredicto_pricing),
        "p1_pricing_veredicto": q1.veredicto_pricing.etiqueta,
        "p1_volumen_veredicto": q1.veredicto_volumen.etiqueta,
        "p1_canal_veredicto": q1.veredicto_canal.etiqueta,
        "p1_por_canal": _formatear_tabla(q1.por_canal, "Canal_Venta",
                                         "tasa_negativa_pct"),

        "p2_adversa": f"{q2.kpis.get('tasa_envio_adverso_pct', 0):.1f}",
        "p2_con_estado": f"{q2.kpis.get('trx_con_estado', 0):,}",
        "p2_mediana": f"{q2.kpis.get('entrega_mediana_dias', 0):.0f}",
        "p2_p90": f"{q2.kpis.get('entrega_p90_dias', 0):.0f}",
        "p2_signif": q2.kpis.get("correlaciones_significativas", 0),
        "p2_evaluadas": q2.kpis.get("correlaciones_evaluadas", 0),
        "p2_adversa_veredicto": q2.veredicto_adversa.etiqueta,
        "p2_tiempo_veredicto": q2.veredicto_tiempo.etiqueta,
        "p2_por_ciudad": _formatear_tabla(q2.desempeno_ciudad,
                                          "Ciudad_Destino", "tasa_adversa"),

        "p3_ingreso": f"{q3.kpis.get('ingreso_usd', 0):,.0f}",
        "p3_pct": f"{q3.kpis.get('pct_ingreso', 0):.2f}",
        "p3_skus": f"{q3.kpis.get('skus', 0):,}",
        "p3_trx": f"{q3.kpis.get('transacciones', 0):,}",
        "p3_margen": f"{q3.kpis.get('margen_no_controlado_usd', 0):,.0f}",
        "p3_origen": q3.veredicto_origen,

        "p4_sentimiento_veredicto": q4.veredicto_sentimiento.etiqueta,
        "p4_stock_veredicto": q4.veredicto_stock.etiqueta,
        "p4_causa": q4.kpis.get("causa_dominante", "no disponible"),
        "p4_causa_pct": f"{q4.kpis.get('pct_causa_dominante', 0):.1f}",
        "p4_reparto": "; ".join(
            f"{k} {v:.1f} %"
            for k, v in q4.kpis.get("reparto_causas", {}).items()) or
        "no disponible",

        "p5_meses": f"{q5.kpis.get('antiguedad_meses', 0):.1f}",
        "p5_max": f"{q5.kpis.get('antiguedad_maxima', 0):.0f}",
        "p5_correlacion_veredicto":
            q5.veredicto_antiguedad_tickets.etiqueta,
        "p5_tickets_veredicto": q5.veredicto_tickets_bodega.etiqueta,
        "p5_no_estandar": q5.kpis.get("bodegas_no_estandar", 0),
        "p5_bodegas": q5.kpis.get("bodegas_evaluadas", 0),
    }


def _describir_relacion(veredicto: analytics.Veredicto) -> str:
    """Traduce un coeficiente a lenguaje no técnico.

    El prompt prohíbe al modelo citar pruebas estadísticas por su nombre, así
    que la traducción se hace aquí y no se le delega.
    """
    if veredicto.tamano_efecto is None:
        return "no medida"
    efecto = abs(veredicto.tamano_efecto)
    if efecto < 0.10:
        return "prácticamente nula (el precio no acompaña al costo)"
    if efecto < 0.30:
        return "débil"
    if efecto < 0.50:
        return "moderada"
    return "fuerte"


def construir_prompt(resumen: dict) -> tuple[str, str]:
    """Arma el par (prompt de sistema, prompt de usuario).

    Args:
        resumen: Salida de ``construir_resumen``.

    Returns:
        Tupla (sistema, usuario).

    Raises:
        ErrorIA: Si al resumen le falta alguna clave que la plantilla espera.
    """
    try:
        usuario = PLANTILLA_USUARIO.format(**resumen)
    except KeyError as exc:
        raise ErrorIA(
            f"El resumen enviado al modelo está incompleto: falta {exc}.",
            "Es un error de programación, no de configuración.") from exc
    return PROMPT_SISTEMA, usuario


# --------------------------------------------------------------------------
# Gestión de la clave
# --------------------------------------------------------------------------


def obtener_clave() -> str:
    """Lee la clave de API sin exponerla nunca en el código.

    Orden de búsqueda: ``st.secrets`` primero (es lo que usa Streamlit
    Community Cloud) y variable de entorno después (ejecución local con
    ``.env``).

    Returns:
        La clave de API.

    Raises:
        ClaveNoConfigurada: Si no se encuentra en ninguna de las dos fuentes.
    """
    try:
        import streamlit as st
        if config.NOMBRE_VAR_ENTORNO_GROQ in st.secrets:
            clave = str(st.secrets[config.NOMBRE_VAR_ENTORNO_GROQ]).strip()
            if clave:
                return clave
    except Exception:  # noqa: BLE001
        # Fuera de Streamlit, o sin archivo de secretos: se sigue al entorno.
        logger.debug("Secretos de Streamlit no disponibles")

    clave = (os.environ.get(config.NOMBRE_VAR_ENTORNO_GROQ) or "").strip()
    if clave:
        return clave

    raise ClaveNoConfigurada(
        "No se encontró la clave de API de Groq.",
        "Copie `.env.example` a `.env` y ponga su clave, o cárguela en "
        "Settings → Secrets si la app está en la nube. Puede obtener una "
        "gratuita en console.groq.com/keys.")


# --------------------------------------------------------------------------
# Llamada al modelo
# --------------------------------------------------------------------------


def _crear_cliente(clave: str):
    """Instancia el cliente de Groq con importación diferida."""
    try:
        from groq import Groq
    except ImportError as exc:
        raise ServicioNoDisponible(
            "La librería `groq` no está instalada.",
            "Ejecute `pip install -r requirements.txt`.") from exc
    return Groq(api_key=clave, timeout=config.TIMEOUT_GROQ_SEG)


def _traducir_error(exc: Exception) -> ErrorIA:
    """Convierte una excepción del SDK en un error con mensaje presentable.

    Se traduce aquí y no en la interfaz para que la capa de presentación no
    tenga que conocer los tipos de excepción del proveedor.
    """
    import groq

    if isinstance(exc, groq.AuthenticationError):
        return ErrorAutenticacion(
            "La clave de API de Groq fue rechazada.",
            "Verifique que esté completa y vigente en console.groq.com/keys.")
    if isinstance(exc, groq.RateLimitError):
        return LimiteDeUso(
            "Se alcanzó el límite de peticiones de la cuenta de Groq.",
            "Espere un minuto y vuelva a intentarlo. El plan gratuito tiene "
            "un tope por minuto.")
    if isinstance(exc, groq.APITimeoutError):
        return TiempoAgotado(
            f"El modelo no respondió en {config.TIMEOUT_GROQ_SEG} segundos.",
            "Reintente, o reduzca el recorte con los filtros del panel "
            "lateral para acortar el análisis.")
    if isinstance(exc, groq.NotFoundError):
        return ModeloNoDisponible(
            f"El modelo `{config.MODELO_GROQ}` no está disponible.",
            "Puede haber sido retirado. Revise la lista vigente en "
            "console.groq.com/docs/models y actualice MODELO_GROQ en "
            "src/config.py.")
    if isinstance(exc, (groq.APIConnectionError, groq.InternalServerError)):
        return ServicioNoDisponible(
            "No se pudo contactar el servicio de Groq.",
            "Puede ser un problema de red o una interrupción del proveedor. "
            "Reintente en unos minutos.")
    if isinstance(exc, groq.APIStatusError):
        return ServicioNoDisponible(
            f"Groq respondió con un error (código {exc.status_code}).",
            "Reintente; si persiste, revise el estado del servicio.")

    return ServicioNoDisponible(
        "Ocurrió un error inesperado al generar el análisis.",
        f"Detalle técnico: {type(exc).__name__}: {exc}")


def _separar_parrafos(texto: str) -> list[str]:
    """Normaliza la respuesta a exactamente tres párrafos.

    El modelo puede desviarse del formato pedido pese a las instrucciones. En
    lugar de rechazar la respuesta se normaliza: si devuelve más de tres
    bloques se conservan los tres primeros; si devuelve uno solo con saltos
    simples, se parte por ellos.
    """
    bloques = [p.strip() for p in texto.strip().split("\n\n") if p.strip()]

    if len(bloques) < 3:
        candidatos = [p.strip() for p in texto.strip().split("\n") if p.strip()]
        if len(candidatos) >= 3:
            bloques = candidatos

    # Se retiran viñetas o numeración residual que el modelo pudiera añadir.
    limpios = []
    for bloque in bloques:
        for prefijo in ("- ", "* ", "1. ", "2. ", "3. "):
            if bloque.startswith(prefijo):
                bloque = bloque[len(prefijo):].strip()
        limpios.append(bloque)

    return limpios[:3] if len(limpios) >= 3 else limpios


def generar_recomendaciones(resumen: dict, cliente=None) -> ResultadoIA:
    """Solicita a Llama-3 las tres recomendaciones estratégicas.

    Args:
        resumen: Salida de ``construir_resumen``.
        cliente: Cliente de Groq ya construido. Se inyecta en las pruebas para
            no depender de la red; en producción se deja en None.

    Returns:
        ResultadoIA con los párrafos y la traza de lo que se envió.

    Raises:
        ClaveNoConfigurada: Si no hay clave disponible.
        ErrorIA: Ante cualquier fallo del servicio, ya traducido a un mensaje
            presentable con su sugerencia de solución.
    """
    sistema, usuario = construir_prompt(resumen)

    if cliente is None:
        cliente = _crear_cliente(obtener_clave())

    try:
        respuesta = cliente.chat.completions.create(
            model=config.MODELO_GROQ,
            messages=[
                {"role": "system", "content": sistema},
                {"role": "user", "content": usuario},
            ],
            temperature=config.TEMPERATURA_GROQ,
            max_tokens=config.MAX_TOKENS_GROQ,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Fallo la llamada a Groq: %s", exc)
        raise _traducir_error(exc) from exc

    contenido = (respuesta.choices[0].message.content or "").strip()
    if not contenido:
        raise ServicioNoDisponible(
            "El modelo devolvió una respuesta vacía.",
            "Reintente; si persiste, reduzca el recorte de datos.")

    uso = getattr(respuesta, "usage", None)
    resultado = ResultadoIA(
        parrafos=_separar_parrafos(contenido),
        modelo=config.MODELO_GROQ,
        tokens_entrada=getattr(uso, "prompt_tokens", 0) or 0,
        tokens_salida=getattr(uso, "completion_tokens", 0) or 0,
        resumen_enviado=resumen,
        prompt_usuario=usuario,
    )
    logger.info("Análisis generado: %d párrafos, %d tokens de salida",
                len(resultado.parrafos), resultado.tokens_salida)
    return resultado
