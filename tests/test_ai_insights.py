"""Pruebas del módulo de IA.

Ninguna prueba llama a la red: el cliente de Groq se inyecta como doble, así
que la suite es determinista, gratuita y ejecutable sin clave de API. Lo que
se verifica es lo que puede fallar de verdad —el contenido del prompt, la
gestión de la clave y la traducción de errores del proveedor— y no la
capacidad de redacción del modelo.
"""

import json
from types import SimpleNamespace

import pandas as pd
import pytest

from src import ai_insights, config, filters


# --------------------------------------------------------------------------
# Dobles de prueba
# --------------------------------------------------------------------------


class _RespuestaFalsa:
    """Imita la forma de la respuesta del SDK de Groq."""

    def __init__(self, contenido: str, entrada: int = 800, salida: int = 300):
        mensaje = SimpleNamespace(content=contenido)
        self.choices = [SimpleNamespace(message=mensaje)]
        self.usage = SimpleNamespace(prompt_tokens=entrada,
                                     completion_tokens=salida)


class _ClienteFalso:
    """Cliente que devuelve un contenido fijo y registra lo que recibió."""

    def __init__(self, contenido: str):
        self._contenido = contenido
        self.recibido = {}
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.recibido = kwargs
        return _RespuestaFalsa(self._contenido)


class _ClienteQueFalla:
    """Cliente que lanza la excepción indicada."""

    def __init__(self, excepcion: Exception):
        self._excepcion = excepcion
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        raise self._excepcion


TRES_PARRAFOS = (
    "Primer párrafo con el diagnóstico y su cifra.\n\n"
    "Segundo párrafo con la advertencia sobre el ruido.\n\n"
    "Tercer párrafo con el plan de acción priorizado.")


@pytest.fixture(scope="module")
def resumen(integrado):
    """Resumen estadístico de la operación completa."""
    return ai_insights.construir_resumen(
        integrado.ssot, "Sin filtros: se analiza la operación completa.",
        float(integrado.ssot["Ingreso_Bruto"].sum()),
        integrado.diagnostico_fantasma)


# --------------------------------------------------------------------------
# El resumen: la frontera de confianza del módulo
# --------------------------------------------------------------------------


class TestConstruirResumen:
    """Todo lo que el modelo puede decir tiene que salir de aquí."""

    def test_incluye_las_cinco_preguntas(self, resumen):
        for prefijo in ("p1_", "p2_", "p3_", "p4_", "p5_"):
            assert any(k.startswith(prefijo) for k in resumen)

    def test_cifras_clave_presentes(self, resumen):
        assert resumen["p3_ingreso"] == "13,138,474"
        assert resumen["p3_skus"] == "480"
        assert resumen["p1_skus"] == "878"

    def test_incluye_los_veredictos(self, resumen):
        """Sin ellos el modelo recomendaría actuar sobre ruido."""
        veredictos = [v for k, v in resumen.items()
                      if k.endswith("_veredicto")]
        assert len(veredictos) >= 7
        assert all(v in {"Hallazgo sólido", "Sin evidencia",
                         "Significativo pero irrelevante"}
                   for v in veredictos)

    def test_traduce_el_coeficiente_a_lenguaje_no_tecnico(self, resumen):
        """El prompt prohíbe citar estadística; la traducción ocurre aquí."""
        assert "prácticamente nula" in resumen["p1_pricing_valor"]

    def test_es_serializable(self, resumen):
        """Debe poder descargarse como evidencia auditable."""
        assert json.dumps(resumen, ensure_ascii=False)

    def test_recorte_vacio_falla_con_mensaje_claro(self):
        with pytest.raises(ValueError, match="no contiene transacciones"):
            ai_insights.construir_resumen(pd.DataFrame(), "vacío")

    def test_respeta_el_recorte_del_usuario(self, integrado):
        """Requisito de la guía: la IA analiza solo lo filtrado."""
        seleccion = filters.Filtros(canales=("Online",))
        recorte = filters.aplicar_filtros(integrado.ssot, seleccion)
        resumen = ai_insights.construir_resumen(
            recorte, seleccion.describir(),
            float(integrado.ssot["Ingreso_Bruto"].sum()))

        assert "Online" in resumen["recorte"]
        assert resumen["transacciones"] == f"{len(recorte):,}"
        assert float(resumen["pct_ingreso"].replace(",", ".")) < 100

    def test_sin_venta_fantasma_no_afirma_falla_de_catalogo(self, integrado):
        """Un recorte sin SKU huérfanos no debe heredar ese diagnóstico."""
        seleccion = filters.Filtros(categorias=("Laptops",))
        recorte = filters.aplicar_filtros(integrado.ssot, seleccion)
        resumen = ai_insights.construir_resumen(recorte,
                                                seleccion.describir())

        assert resumen["p3_ingreso"] == "0"
        assert "No aplica" in resumen["p3_origen"]


# --------------------------------------------------------------------------
# El prompt
# --------------------------------------------------------------------------


class TestPrompt:
    """El prompt es el control principal contra la alucinación."""

    def test_prohibe_inventar_cifras(self):
        sistema = ai_insights.PROMPT_SISTEMA
        assert "exclusivamente las cifras" in sistema
        assert "No inventes" in sistema

    def test_prohibe_actuar_sobre_hallazgos_no_solidos(self):
        """La defensa que evita 'cambie de operador' sobre una rho de 0,04."""
        sistema = ai_insights.PROMPT_SISTEMA
        assert "PROHIBIDO" in sistema
        assert "Sin evidencia" in sistema
        assert "Significativo pero irrelevante" in sistema

    def test_exige_exactamente_tres_parrafos(self):
        assert "tres párrafos" in ai_insights.PROMPT_SISTEMA

    def test_prohibe_jerga_tecnica(self):
        assert "nombres de columnas" in ai_insights.PROMPT_SISTEMA

    def test_usuario_contiene_las_cifras_del_resumen(self, resumen):
        _, usuario = ai_insights.construir_prompt(resumen)
        assert resumen["p3_ingreso"] in usuario
        assert resumen["p1_perdida"] in usuario
        assert resumen["recorte"] in usuario

    def test_usuario_no_deja_marcadores_sin_rellenar(self, resumen):
        _, usuario = ai_insights.construir_prompt(resumen)
        assert "{" not in usuario and "}" not in usuario

    def test_resumen_incompleto_falla_ruidosamente(self):
        with pytest.raises(ai_insights.ErrorIA, match="incompleto"):
            ai_insights.construir_prompt({"recorte": "x"})


# --------------------------------------------------------------------------
# Gestión de la clave
# --------------------------------------------------------------------------


@pytest.fixture
def sin_secretos_streamlit(monkeypatch):
    """Neutraliza ``st.secrets`` para aislar la lectura desde el entorno.

    ``obtener_clave`` consulta los secretos de Streamlit antes que la variable
    de entorno, que es el orden correcto en producción. Pero eso hace que estas
    pruebas dependan de si la máquina tiene un `secrets.toml` local: en la del
    desarrollador pasaban y en una limpia también, hasta que apareció el
    archivo y empezaron a leer la clave real. Vaciar los secretos aquí las
    vuelve herméticas y reproducibles en cualquier entorno.
    """
    import streamlit as st
    monkeypatch.setattr(st, "secrets", {}, raising=False)


class TestGestionDeClave:
    """La clave nunca vive en el código."""

    def test_lee_de_variable_de_entorno(
            self, monkeypatch, sin_secretos_streamlit):
        monkeypatch.setenv(config.NOMBRE_VAR_ENTORNO_GROQ, "clave-de-prueba")
        assert ai_insights.obtener_clave() == "clave-de-prueba"

    def test_ignora_clave_vacia(self, monkeypatch, sin_secretos_streamlit):
        monkeypatch.setenv(config.NOMBRE_VAR_ENTORNO_GROQ, "   ")
        with pytest.raises(ai_insights.ClaveNoConfigurada):
            ai_insights.obtener_clave()

    def test_sin_clave_da_mensaje_accionable(
            self, monkeypatch, sin_secretos_streamlit):
        monkeypatch.delenv(config.NOMBRE_VAR_ENTORNO_GROQ, raising=False)
        with pytest.raises(ai_insights.ClaveNoConfigurada) as excinfo:
            ai_insights.obtener_clave()
        assert "console.groq.com" in excinfo.value.sugerencia

    def test_los_secretos_tienen_prioridad_sobre_el_entorno(self, monkeypatch):
        """En la nube solo existe st.secrets; debe ganar si está presente."""
        import streamlit as st
        monkeypatch.setattr(
            st, "secrets", {config.NOMBRE_VAR_ENTORNO_GROQ: "desde-secretos"},
            raising=False)
        monkeypatch.setenv(config.NOMBRE_VAR_ENTORNO_GROQ, "desde-entorno")
        assert ai_insights.obtener_clave() == "desde-secretos"

    def test_ninguna_clave_real_esta_versionada(self):
        """Ninguna clave real puede estar en un archivo que git rastree.

        Se recorren los archivos **que git tiene rastreados**, no una lista de
        extensiones. Una versión anterior de esta prueba filtraba por `*.py` y
        `*.toml`, y por eso no detectó una clave real dentro de
        `.streamlit/secrets.toml.example`: su extensión efectiva es `.example`.
        Preguntarle a git qué versiona elimina esa clase de hueco por completo.

        Se busca la *forma* de una clave de Groq —el prefijo seguido de una
        cadena larga sin separadores— y no el prefijo suelto, para que los
        marcadores de posición de las plantillas no den falsos positivos.
        """
        import re
        import subprocess
        from pathlib import Path

        patron = re.compile(r"gsk_[A-Za-z0-9]{20,}")
        raiz = Path(ai_insights.__file__).resolve().parent.parent

        rastreados = subprocess.run(
            ["git", "ls-files"], cwd=raiz, capture_output=True, text=True,
            encoding="utf-8", errors="ignore")
        if rastreados.returncode != 0:
            pytest.skip("El proyecto no es un repositorio git")

        for relativa in rastreados.stdout.splitlines():
            archivo = raiz / relativa
            if not archivo.is_file():
                continue
            texto = archivo.read_text(encoding="utf-8", errors="ignore")
            assert not patron.search(texto), (
                f"Clave de API real versionada en {relativa}. Muévala a "
                f".streamlit/secrets.toml o a .env, que están ignorados.")

    def test_la_plantilla_no_usa_el_prefijo_real(self):
        """La plantilla no debe imitar la forma de una clave.

        Si el marcador de posición empieza por el prefijo real, la protección
        de secretos de GitHub puede bloquear el push por un falso positivo, y
        además invita a sobrescribirlo con la clave verdadera en el archivo
        equivocado.
        """
        from pathlib import Path

        raiz = Path(ai_insights.__file__).resolve().parent.parent
        plantilla = raiz / ".streamlit" / "secrets.toml.example"
        if not plantilla.exists():
            pytest.skip("No hay plantilla de secretos")

        contenido = plantilla.read_text(encoding="utf-8")
        assert "gsk_" not in contenido, (
            "El marcador de posición no debe empezar por el prefijo real de "
            "una clave de Groq")
        assert config.NOMBRE_VAR_ENTORNO_GROQ in contenido


# --------------------------------------------------------------------------
# Llamada al modelo y manejo de errores
# --------------------------------------------------------------------------


class TestGenerarRecomendaciones:
    """La app nunca debe caerse por un fallo del proveedor."""

    def test_devuelve_tres_parrafos(self, resumen):
        cliente = _ClienteFalso(TRES_PARRAFOS)
        resultado = ai_insights.generar_recomendaciones(resumen, cliente)

        assert len(resultado.parrafos) == 3
        assert resultado.modelo == config.MODELO_GROQ
        assert resultado.tokens_salida == 300

    def test_envia_los_parametros_configurados(self, resumen):
        cliente = _ClienteFalso(TRES_PARRAFOS)
        ai_insights.generar_recomendaciones(resumen, cliente)

        assert cliente.recibido["model"] == config.MODELO_GROQ
        assert cliente.recibido["temperature"] == config.TEMPERATURA_GROQ
        assert cliente.recibido["max_tokens"] == config.MAX_TOKENS_GROQ
        roles = [m["role"] for m in cliente.recibido["messages"]]
        assert roles == ["system", "user"]

    def test_no_envia_datos_individuales(self, resumen):
        """Solo salen cifras agregadas: ni un SKU ni un ID de transacción."""
        cliente = _ClienteFalso(TRES_PARRAFOS)
        ai_insights.generar_recomendaciones(resumen, cliente)
        enviado = cliente.recibido["messages"][1]["content"]

        assert "TRX-" not in enviado
        assert "PROD-" not in enviado or "PROD-2345" in enviado

    def test_normaliza_respuesta_con_vinetas(self, resumen):
        cliente = _ClienteFalso("- Uno\n\n- Dos\n\n- Tres")
        resultado = ai_insights.generar_recomendaciones(resumen, cliente)
        assert resultado.parrafos == ["Uno", "Dos", "Tres"]

    def test_normaliza_respuesta_con_saltos_simples(self, resumen):
        cliente = _ClienteFalso("Uno\nDos\nTres")
        resultado = ai_insights.generar_recomendaciones(resumen, cliente)
        assert len(resultado.parrafos) == 3

    def test_recorta_si_devuelve_mas_de_tres(self, resumen):
        cliente = _ClienteFalso("A\n\nB\n\nC\n\nD\n\nE")
        resultado = ai_insights.generar_recomendaciones(resumen, cliente)
        assert len(resultado.parrafos) == 3

    def test_respuesta_vacia_es_error_controlado(self, resumen):
        cliente = _ClienteFalso("   ")
        with pytest.raises(ai_insights.ServicioNoDisponible):
            ai_insights.generar_recomendaciones(resumen, cliente)

    def test_conserva_la_traza_de_lo_enviado(self, resumen):
        """Auditabilidad: debe poder verificarse qué recibió el modelo."""
        cliente = _ClienteFalso(TRES_PARRAFOS)
        resultado = ai_insights.generar_recomendaciones(resumen, cliente)

        assert resultado.resumen_enviado == resumen
        assert resumen["p3_ingreso"] in resultado.prompt_usuario


class TestTraduccionDeErrores:
    """Cada fallo del proveedor debe dar un mensaje que el usuario entienda."""

    def _lanzar(self, resumen, excepcion):
        cliente = _ClienteQueFalla(excepcion)
        with pytest.raises(ai_insights.ErrorIA) as excinfo:
            ai_insights.generar_recomendaciones(resumen, cliente)
        return excinfo.value

    def test_clave_invalida(self, resumen):
        import groq
        import httpx
        error = groq.AuthenticationError(
            "invalid api key",
            response=httpx.Response(401, request=httpx.Request("POST", "/")),
            body=None)
        traducido = self._lanzar(resumen, error)
        assert isinstance(traducido, ai_insights.ErrorAutenticacion)
        assert "rechazada" in traducido.mensaje

    def test_limite_de_uso(self, resumen):
        import groq
        import httpx
        error = groq.RateLimitError(
            "rate limited",
            response=httpx.Response(429, request=httpx.Request("POST", "/")),
            body=None)
        traducido = self._lanzar(resumen, error)
        assert isinstance(traducido, ai_insights.LimiteDeUso)
        assert "Espere" in traducido.sugerencia

    def test_tiempo_agotado(self, resumen):
        import groq
        import httpx
        error = groq.APITimeoutError(request=httpx.Request("POST", "/"))
        traducido = self._lanzar(resumen, error)
        assert isinstance(traducido, ai_insights.TiempoAgotado)
        assert str(config.TIMEOUT_GROQ_SEG) in traducido.mensaje

    def test_modelo_retirado(self, resumen):
        import groq
        import httpx
        error = groq.NotFoundError(
            "model not found",
            response=httpx.Response(404, request=httpx.Request("POST", "/")),
            body=None)
        traducido = self._lanzar(resumen, error)
        assert isinstance(traducido, ai_insights.ModeloNoDisponible)
        assert config.MODELO_GROQ in traducido.mensaje

    def test_fallo_de_red(self, resumen):
        import groq
        import httpx
        error = groq.APIConnectionError(request=httpx.Request("POST", "/"))
        traducido = self._lanzar(resumen, error)
        assert isinstance(traducido, ai_insights.ServicioNoDisponible)

    def test_error_inesperado_no_escapa(self, resumen):
        """Cualquier excepción debe llegar a la UI como ErrorIA presentable."""
        traducido = self._lanzar(resumen, RuntimeError("algo raro"))
        assert isinstance(traducido, ai_insights.ErrorIA)
        assert traducido.mensaje and traducido.sugerencia

    def test_todos_los_errores_traen_mensaje_y_sugerencia(self, resumen):
        traducido = self._lanzar(resumen, ValueError("x"))
        assert traducido.mensaje.strip()
        assert traducido.sugerencia.strip()
