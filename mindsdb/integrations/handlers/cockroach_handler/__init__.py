from mindsdb.integrations.libs.const import HANDLER_TYPE

from .__about__ import __version__ as version, __description__ as description
try:
    from .cockroach_handler import CockroachHandler as Handler
    import_error = None
except Exception as e:
    Handler = None
    import_error = e

title = 'CockroachDB'
name = 'cockroach'
type = HANDLER_TYPE.DATA

__all__ = [
    'Handler', 'version', 'name', 'type', 'title',
    'description', 'import_error'
]
