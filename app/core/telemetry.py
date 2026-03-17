"""
app/core/telemetry.py
OpenTelemetry tracing — sends to Arize Phoenix when available.

arize-phoenix is a DEV dependency not installed in the Railway image.
This module degrades gracefully: if Phoenix SDK is not present, tracing
is a no-op. OTEL SDK itself IS installed (lightweight, ~5MB) so spans
are still collected — they just have no exporter if Phoenix isn't running.
"""
from __future__ import annotations

import contextlib
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, NullSpanExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
_provider: TracerProvider | None = None


def configure_tracing() -> None:
    """
    Set up OTEL tracing. Degrades gracefully if Phoenix is not reachable.
    Called once at FastAPI startup.
    """
    global _provider
    settings = get_settings()

    try:
        # Try to wire up the OTLP exporter → Phoenix
        exporter = OTLPSpanExporter(endpoint=settings.phoenix_collector_endpoint)
        _provider = TracerProvider()
        _provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(_provider)

        # Auto-instrument OpenAI calls if the instrumentation package is present
        try:
            from openinference.instrumentation.openai import OpenAIInstrumentor
            OpenAIInstrumentor().instrument()
            logger.info("otel_tracing_ready", endpoint=settings.phoenix_collector_endpoint)
        except ImportError:
            logger.info("otel_openai_instrumentation_skipped", reason="openinference not installed")

    except Exception as exc:
        # Phoenix not running or OTLP export fails — use no-op provider
        logger.warning("otel_tracing_degraded", error=str(exc), reason="using no-op tracer")
        _provider = TracerProvider()
        _provider.add_span_processor(BatchSpanProcessor(NullSpanExporter()))
        trace.set_tracer_provider(_provider)


def get_tracer(component: str = "hedge-fund-ai") -> trace.Tracer:
    return trace.get_tracer(component)


class traced:
    """
    Async context manager that wraps a block in a named OTEL span.

    Usage:
        async with traced("news_agent", ticker="AAPL"):
            ...

    Safe to use even when tracing is a no-op — spans just don't export.
    """

    def __init__(self, name: str, **attributes: str | int | float) -> None:
        self._name = name
        self._attrs = attributes
        self._span: trace.Span | None = None

    async def __aenter__(self) -> trace.Span:
        tracer = get_tracer()
        self._span = tracer.start_span(self._name)
        for k, v in self._attrs.items():
            self._span.set_attribute(k, str(v))
        return self._span

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self._span is not None:
            if exc_type is not None:
                with contextlib.suppress(Exception):
                    self._span.record_exception(exc_val)
                    self._span.set_status(
                        trace.StatusCode.ERROR, str(exc_val)
                    )
            with contextlib.suppress(Exception):
                self._span.end()
        return False
