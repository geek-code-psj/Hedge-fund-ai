"""
app/core/telemetry.py
OpenTelemetry tracing — zero hard dependencies at module level.
Every import is inside try/except so a missing or mismatched package
cannot crash the server on startup.
"""
from __future__ import annotations
import contextlib

# ── Lazy globals ──────────────────────────────────────────────────────────────
_provider = None
_logger = None


def _get_logger():
    global _logger
    if _logger is None:
        from app.core.logging import get_logger
        _logger = get_logger(__name__)
    return _logger


def configure_tracing() -> None:
    """Called once at FastAPI startup. Never raises."""
    global _provider
    try:
        from app.core.config import get_settings
        settings = get_settings()

        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        # Build a no-op exporter inline — avoids importing NullSpanExporter
        # which was removed in newer opentelemetry-sdk versions
        try:
            from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
            class _NoOp(SpanExporter):
                def export(self, spans):
                    return SpanExportResult.SUCCESS
                def shutdown(self):
                    pass
        except Exception:
            _NoOp = None

        try:
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
            exporter = OTLPSpanExporter(endpoint=settings.phoenix_collector_endpoint)
        except Exception:
            exporter = _NoOp() if _NoOp else None

        _provider = TracerProvider()
        if exporter:
            _provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(_provider)

        # Auto-instrument OpenAI — optional
        try:
            from openinference.instrumentation.openai import OpenAIInstrumentor
            OpenAIInstrumentor().instrument()
        except Exception:
            pass

        _get_logger().info("otel_tracing_ready")

    except Exception as exc:
        _get_logger().warning("otel_tracing_skipped", error=str(exc))


def get_tracer(component: str = "hedge-fund-ai"):
    try:
        from opentelemetry import trace
        return trace.get_tracer(component)
    except Exception:
        # Return a no-op tracer duck-type if OTEL not available
        class _NoOpTracer:
            def start_span(self, name, **kw):
                return _NoOpSpan()
        return _NoOpTracer()


class _NoOpSpan:
    """Fallback span used when OTEL is unavailable."""
    def set_attribute(self, k, v): pass
    def record_exception(self, exc): pass
    def set_status(self, *a, **kw): pass
    def end(self): pass


class traced:
    """
    Async context manager — wraps a block in a named OTEL span.
    Completely safe to use even when OTEL is unavailable.
    """
    def __init__(self, name: str, **attributes) -> None:
        self._name = name
        self._attrs = attributes
        self._span = None

    async def __aenter__(self):
        try:
            tracer = get_tracer()
            self._span = tracer.start_span(self._name)
            for k, v in self._attrs.items():
                self._span.set_attribute(k, str(v))
        except Exception:
            self._span = _NoOpSpan()
        return self._span

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self._span is not None:
            if exc_type is not None:
                with contextlib.suppress(Exception):
                    self._span.record_exception(exc_val)
                    self._span.set_status("ERROR", str(exc_val))
            with contextlib.suppress(Exception):
                self._span.end()
        return False
