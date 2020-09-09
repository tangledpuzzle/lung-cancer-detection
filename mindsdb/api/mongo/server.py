import socketserver as SocketServer
import struct
import bson
from bson import codec_options
from collections import OrderedDict
from abc import abstractmethod

from mindsdb.api.mongo.classes import RespondersCollection

# from mindsdb.api.mongo.op_query_responders import responders as op_query_responders
from mindsdb.api.mongo.op_msg_responders import responders as op_msg_responders
import mindsdb.api.mongo.functions as helpers

from mindsdb.interfaces.datastore.datastore import DataStore
from mindsdb.interfaces.native.mindsdb import MindsdbNative

OP_REPLY = 1
OP_UPDATE = 2001
OP_INSERT = 2002
OP_QUERY = 2004
OP_GET_MORE = 2005
OP_DELETE = 2006
OP_KILL_CURSORS = 2007
OP_MSG = 2013

BYTE = '<b'
INT = '<i'
UINT = '<I'
LONG = '<q'


def unpack(format, buffer, start=0):
    end = start + struct.calcsize(format)
    return struct.unpack(format, buffer[start:end])[0], end


def get_utf8_string(buffer, start=0):
    end = buffer.index(b"\x00", start)
    s = buffer[start:end].decode('utf8')
    return s, end + 1


CODEC_OPTIONS = codec_options.CodecOptions(document_class=OrderedDict)


def decode_documents(buffer, start, content_size):
    docs = bson.decode_all(buffer[start:start + content_size], CODEC_OPTIONS)
    return docs, start + content_size


class OperationResponder():
    def __init__(self, responders):
        self.responders = responders

    @abstractmethod
    def handle(self, query_bytes):
        pass

    @abstractmethod
    def to_bytes(self, response, request_id):
        pass

    def get_match_responder(self, query):
        for responder in self.responders:
            if responder['match'](query):
                return responder['response']
        raise Exception('is no responder')


# NOTE probably, it need only for mongo version < 3.6
class OpInsertResponder(OperationResponder):
    def handle(self, buffer, request_id, mindsdb_env):
        flags, pos = unpack(UINT, buffer)
        namespace, pos = get_utf8_string(buffer, pos)
        query = bson.decode_all(buffer[pos:], CODEC_OPTIONS)
        responder = self.responders.find_match(query)
        assert responder is not None, 'query cant be processed'

        request_args = {
            'request_id': request_id
        }

        documents = responder.handle(query, request_args, mindsdb_env)

        return documents

    def to_bytes(self, response, request_id):
        pass


OP_MSG_FLAGS = {
    'checksumPresent': 0,
    'moreToCome': 1,
    'exhaustAllowed': 16
}


# NOTE used in mongo version > 3.6
class OpMsgResponder(OperationResponder):
    def handle(self, buffer, request_id, mindsdb_env):
        query = OrderedDict()
        flags, pos = unpack(UINT, buffer)

        checksum_present = bool(flags & (1 << OP_MSG_FLAGS['checksumPresent']))
        if checksum_present:
            msg_len = len(buffer) - 4
        else:
            msg_len = len(buffer)

        # sections
        while pos < msg_len:
            kind, pos = unpack(BYTE, buffer, pos)
            if kind == 0:
                # body
                section_size, _ = unpack(INT, buffer, pos)
                docs, pos = decode_documents(buffer, pos, section_size)
                query.update(docs[0])
            elif kind == 1:
                # Document
                section_size, pos = unpack(INT, buffer, pos)
                seq_id, pos = get_utf8_string(buffer, pos)
                docs_len = section_size - struct.calcsize(INT) - len(seq_id) - 1
                docs, pos = decode_documents(buffer, pos, docs_len)
                query[seq_id] = docs

        remaining = len(buffer) - pos
        if checksum_present:
            if remaining != 4:
                raise Exception('should be checksum at the end of message')
            # TODO read and check checksum
        elif remaining != 0:
            raise Exception('is bytes left after msg parsing')

        print(f'GET OpMSG={query}')

        responder = self.responders.find_match(query)
        assert responder is not None, 'query cant be processed'

        request_args = {
            'request_id': request_id,
            'database': query['$db']
        }

        documents = responder.handle(query, request_args, mindsdb_env)

        return documents

    def to_bytes(self, response, request_id):
        flags = struct.pack("<I", 0)  # TODO
        payload_type = struct.pack("<b", 0)  # TODO
        payload_data = bson.BSON.encode(response)
        data = b''.join([flags, payload_type, payload_data])

        reply_id = 0  # TODO add seq here
        response_to = request_id

        header = struct.pack("<iiii", 16 + len(data), reply_id, response_to, OP_MSG)
        return header + data


# NOTE used in any mongo shell version
class OpQueryResponder(OperationResponder):
    def handle(self, buffer, request_id, mindsdb_env):
        # https://docs.mongodb.com/manual/reference/mongodb-wire-protocol/#wire-op-query
        flags, pos = unpack(UINT, buffer)
        namespace, pos = get_utf8_string(buffer, pos)
        is_command = namespace.endswith('.$cmd')
        num_to_skip, pos = unpack(INT, buffer, pos)
        num_to_return, pos = unpack(INT, buffer, pos)
        docs = bson.decode_all(buffer[pos:], CODEC_OPTIONS)

        query = docs[0]  # docs = [query, returnFieldsSelector]

        print(f'GET OpQuery={query}')

        responder = self.responders.find_match(query)
        assert responder is not None, 'query cant be processed'

        request_args = {
            'num_to_skip': num_to_skip,
            'num_to_return': num_to_return,
            'request_id': request_id,
            'is_command': is_command
        }

        documents = responder.handle(query, request_args, mindsdb_env)

        return documents

    def to_bytes(self, request, request_id):
        flags = struct.pack("<i", 0)  # TODO
        cursor_id = struct.pack("<q", 0)  # TODO
        starting_from = struct.pack("<i", 0)  # TODO
        number_returned = struct.pack("<i", len([request]))
        reply_id = 123  # TODO
        response_to = request_id

        print(f'RET docs={request}')

        data = b''.join([flags, cursor_id, starting_from, number_returned])
        data += b''.join([bson.BSON.encode(doc) for doc in [request]])

        message = struct.pack("<i", 16 + len(data))
        message += struct.pack("<i", reply_id)
        message += struct.pack("<i", response_to)
        message += struct.pack("<i", OP_REPLY)

        return message + data


class MongoRequestHandler(SocketServer.BaseRequestHandler):
    _stopped = False

    def handle(self):
        while True:
            header = self._read_bytes(16)
            length, pos = unpack(INT, header)
            request_id, pos = unpack(INT, header, pos)
            response_to, pos = unpack(INT, header, pos)
            opcode, pos = unpack(INT, header, pos)
            print(f'GET length={length} id={request_id} opcode={opcode}')
            msg_bytes = self._read_bytes(length - pos)
            answer = self.get_answer(request_id, opcode, msg_bytes)
            self.request.send(answer)

    def get_answer(self, request_id, opcode, msg_bytes):
        if opcode not in self.server.operationsHandlersMap:
            raise NotImplementedError(f'Unknown opcode {opcode}')
        responder = self.server.operationsHandlersMap[opcode]
        assert responder is not None, 'error'
        response = responder.handle(msg_bytes, request_id, self.server.mindsdb_env)
        assert response is not None, 'error'
        return responder.to_bytes(response, request_id)

    def _read_bytes(self, length):
        buffer = b''
        while length:
            chunk = self.request.recv(length)
            if chunk == b'':
                raise Exception('Connection closed')

            length -= len(chunk)
            buffer += chunk
        return buffer


class MongoServer(SocketServer.TCPServer):
    def __init__(self, config):
        mongodb_config = config['api'].get('mongodb')
        assert mongodb_config is not None, 'is no mongodb config!'
        host = mongodb_config['host']
        port = mongodb_config['port']
        print(f'start mongo server on {host}:{port}')

        super().__init__((host, int(port)), MongoRequestHandler)

        self.mindsdb_env = {
            'config': config,
            'data_store': DataStore(config),
            'mindsdb_native': MindsdbNative(config)
        }

        respondersCollection = RespondersCollection()

        opQueryResponder = OpQueryResponder(respondersCollection)
        opMsgResponder = OpMsgResponder(respondersCollection)
        opInsertResponder = OpInsertResponder(respondersCollection)

        self.operationsHandlersMap = {
            OP_QUERY: opQueryResponder,
            OP_MSG: opMsgResponder,
            OP_INSERT: opInsertResponder
        }

        respondersCollection.add(
            when={'isMaster': helpers.is_true},
            result={
                'isMaster': True,   # lowercase?
                'minWireVersion': 0,
                'maxWireVersion': 6,
                'ok': 1
            }
        )

        respondersCollection.responders += op_msg_responders


def run_server(config):
    if config.get('debug') is True:
        SocketServer.TCPServer.allow_reuse_address = True
    with MongoServer(config) as srv:
        srv.serve_forever()
