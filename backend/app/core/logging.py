import contextvars
import json
import logging
from typing import Any


correlation_id_context: contextvars.ContextVar[str] = contextvars.ContextVar(
	"correlation_id",
	default="",
)


class CorrelationIdFilter(logging.Filter):
	def filter(self, record: logging.LogRecord) -> bool:
		record.correlation_id = correlation_id_context.get()
		return True


def configure_logging() -> None:
	root_logger = logging.getLogger()
	if not root_logger.handlers:
		logging.basicConfig(
			level=logging.INFO,
			format="%(asctime)s %(levelname)s correlation_id=%(correlation_id)s %(name)s %(message)s",
		)
	for handler in root_logger.handlers:
		if not any(isinstance(item, CorrelationIdFilter) for item in handler.filters):
			handler.addFilter(CorrelationIdFilter())


def set_correlation_id(value: str) -> contextvars.Token[str]:
	return correlation_id_context.set(value)


def get_correlation_id() -> str:
	return correlation_id_context.get()


def log_event(logger: logging.Logger, event: str, **fields: Any) -> None:
	payload = {"event": event, "correlation_id": get_correlation_id(), **fields}
	logger.info(json.dumps(payload, default=str, sort_keys=True))
