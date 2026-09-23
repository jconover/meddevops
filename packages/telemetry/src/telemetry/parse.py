"""Parse and serialize JSON Lines procedure logs."""

from pydantic import BaseModel, ValidationError

from telemetry.models import Event, ProcedureHeader, ProcedureLog


class LogValidationError(ValueError):
    """The file is not a valid procedure log. Retrying will not help."""


def parse_log(data: bytes) -> ProcedureLog:
    """Parse a JSON Lines log: a procedure header line followed by event lines."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise LogValidationError("file is not valid UTF-8") from e
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise LogValidationError("empty file")
    header = _validate(ProcedureHeader, lines[0], line_no=1)
    events = [_validate(Event, line, line_no=n) for n, line in enumerate(lines[1:], start=2)]
    return ProcedureLog(header=header, events=events)


def dump_log(log: ProcedureLog) -> str:
    """Serialize a log back to JSON Lines."""
    return "\n".join(m.model_dump_json() for m in [log.header, *log.events]) + "\n"


def _validate[M: BaseModel](model: type[M], line: str, line_no: int) -> M:
    try:
        return model.model_validate_json(line)
    except ValidationError as e:
        err = e.errors()[0]
        field = ".".join(str(part) for part in err["loc"]) or "json"
        raise LogValidationError(f"line {line_no}: {field}: {err['msg']}") from e
