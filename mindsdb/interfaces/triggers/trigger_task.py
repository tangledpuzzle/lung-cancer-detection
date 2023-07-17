import copy
import traceback
from mindsdb_sql import parse_sql
from mindsdb_sql.parser.ast import Data, Identifier
from mindsdb_sql.planner.utils import query_traversal

from mindsdb.interfaces.storage import db

from mindsdb.api.mysql.mysql_proxy.controllers.session_controller import SessionController
from mindsdb.api.mysql.mysql_proxy.executor.executor_commands import ExecuteCommands

from mindsdb.interfaces.database.projects import ProjectController
from mindsdb.utilities import log


class TriggerTask:
    def __init__(self, trigger_id):
        self.trigger_id = trigger_id
        self.command_executor = None

    def run(self, stop_event):
        trigger = db.Triggers.query.get(self.trigger_id)
        try:
            self._run(trigger, stop_event)
        except Exception:
            trigger.last_error = str(traceback.format_exc())
            db.session.commit()

    def _run(self, trigger, stop_event):
        log.logger.info(f'trigger starting: {trigger.name}')

        # parse query
        self.query = parse_sql(trigger.query_str, dialect='mindsdb')

        session = SessionController()

        # prepare executor
        project_controller = ProjectController()
        project = project_controller.get(trigger.project_id)

        session.database = project.name

        self.command_executor = ExecuteCommands(session, executor=None)

        # subscribe
        database = session.integration_controller.get_by_id(trigger.database_id)
        data_handler = session.integration_controller.get_handler(database['name'])
        data_handler.subscribe(stop_event, self._callback, trigger.table_name)

    def _callback(self, row, key):
        log.logger.debug(f'trigger call: {row}, {key}')

        trigger = db.Triggers.query.get(self.trigger_id)

        try:
            row.update(key)
            table = [
                row
            ]

            # inject data to query
            query = copy.deepcopy(self.query)

            def find_table(node, is_table, **kwargs):

                if is_table:
                    if (
                            isinstance(node, Identifier)
                            and len(node.parts) == 1
                            and node.parts[0] == 'TABLE_DELTA'
                    ):
                        # replace with data
                        return Data(table, alias=node.alias)

            query_traversal(query, find_table)

            # exec query
            ret = self.command_executor.execute_command(query)
            if ret.error_code is not None:
                trigger.last_error = ret.error_message

        except Exception:
            trigger.last_error = str(traceback.format_exc())

        db.session.commit()


