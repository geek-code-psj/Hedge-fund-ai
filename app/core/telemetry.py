"""
app/core/telemetry.py
Arize Phoenix tracing — runs against a local Docker container.
Zero data egress. MNPI-safe.

LLM calls are instrumented if the relevant instrumentor is available.
"""
from __future__ import annotations

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
try:
    from openinference.instrumentation.openai import OpenAIInstrumentor
    _HAS_OPENAI_INSTRUMENTOR = True
except ImportError:
    _HAS_OPENAI_INSTRUMENTOR = False

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_provider: TracerProvider | None = None


def configure_tracing() -> None:
    """Call once at application startup."""
    global _provider
    settings = get_settings()

    exporter = OTLPSpanExporter(endpoint=settings.phoenix_collector_endpoint)
    _provider = TracerProvider()
    _provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(_provider)

    if _HAS_OPENAI_INSTRUMENTOR:
        OpenAIInstrumentor().instrument()

    logger.info("tracing_configured", endpoint=settings.phoenix_collector_endpoint)


def get_tracer(component: str = "hedge-fund-ai") -> trace.Tracer:
    return trace.get_tracer(component)


class traced:
    """
    Async context manager / decorator to wrap a coroutine in a named span.

    Usage:
        async with traced("news_agent", ticker="AAPL"):
            ...
    """

    def __init__(self, name: str, **attributes: str | int | float) -> None:
        self._name = name
        self._attrs = attributes
        self._span = None

    async def __aenter__(self):
        tracer = get_tracer()
        self._span = tracer.start_span(self._name)
        for k, v in self._attrs.items():
            self._span.set_attribute(k, v)
        return self._span

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._span:
            if exc_type:
                self._span.record_exception(exc_val)
                self._span.set_status(trace.StatusCode.ERROR, str(exc_val))
            self._span.end()
        return False
