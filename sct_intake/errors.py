"""Shared exceptions for the SCT intake pipeline.

Convention:
- ``SCTError`` base for provider/transport/I/O failures raised by this package.
- ``ExtractionError`` (legacy import name ``FieldExtractionError``) for failures
  while calling an OpenAI-compatible chat endpoint or parsing its response.
- ``EmbeddingError`` for failures while producing/validating embeddings.
- Builtin ``ValueError``/``TypeError`` remain the signals for bad *content* or
  bad *argument types* supplied by callers/models, exactly as before.
"""


class SCTError(RuntimeError):
    """Base class for pipeline failures."""


class ExtractionError(SCTError):
    """A field-extraction (chat-completions) call could not produce a result."""


#: Backwards-compatible alias so ``from client_upload import FieldExtractionError``
#: and code catching the old name keep working after the package split.
FieldExtractionError = ExtractionError


class EmbeddingError(SCTError):
    """An embedding provider could not produce valid vectors."""
