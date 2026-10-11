"""Buffer, guard, operate, recheck, disclose. No model or source-write capability."""
import json
import sqlite3

from .contracts import Refusal, SEARCH_BYTES, encode, error, response, validate_request
from .generation import Manager
from .policy import relative_parts
from .store import Store, RECIPE


class Service:
    def __init__(self, manager):
        if not isinstance(manager, Manager): raise Refusal('index_unavailable')
        self.manager = manager

    @staticmethod
    def hint(page, generation, kind):
        return {'page_id': page['page_id'], 'locator': page['locator'],
                'title': page['title'], 'metadata': page['metadata'],
                'match_kind': kind, 'generation': generation}

    @staticmethod
    def filters_available(db, filters):
        fields = {key.rsplit('_', 1)[0] if key.endswith(('_from','_to')) else key for key in filters}
        fields.discard('tag'); fields.discard('category')
        if not fields: return
        available = set()
        for row in db.db.execute('SELECT metadata FROM pages'):
            meta = json.loads(row['metadata'])
            available.update(key for key in fields if meta.get(key))
        if fields - available: raise Refusal('unsupported_filter')

    def lookup(self, db, pin, request):
        operation = request['operation']
        if operation == 'get':
            from .evidence import bundle
            return bundle(self.manager, db, pin, request)
        if operation == 'status':
            count = db.db.execute('SELECT count(*) FROM pages').fetchone()[0]
            return response(operation, {'pages':count, 'recipe':RECIPE}, generation=pin.generation)
        if operation == 'resolve':
            selector = request['selector']
            if selector['kind'] == 'path': relative_parts(selector['value'])
            pages = db.resolve(selector['kind'],selector['value'])
            state = 'not_found' if not pages else 'ok' if len(pages)==1 else 'ambiguous'
            value = {'pages':[self.hint(page,pin.generation,selector['kind']) for page in pages]}
        elif operation == 'search':
            self.filters_available(db, request['filters'])
            pages = db.search(request['query'],request['limit'],request['filters'])
            value = {'pages':[]}; state = 'ok' if pages else 'empty'
            for page in pages:
                value['pages'].append(dict(self.hint(page,pin.generation,'lexical'),
                                           excerpt=page['excerpt'], heading=page['heading']))
        else:
            # Evidence/citation operations are added by Stage 3; no cached fallback.
            raise Refusal('index_unavailable')
        admitted = {item['locator']:item for item in pin.manifest['snapshot']['inventory'] if item['eligible']}
        for page in pages:
            record = admitted.get(page['locator'])
            if not record or record['source_hash'] != page['source_hash'] or record['projection_hash'] != page['projection_hash']:
                raise Refusal('index_unavailable')
        return response(operation,value,state=state,generation=pin.generation)

    def handle(self, request):
        operation = request.get('operation','unknown') if type(request) is dict else 'unknown'
        if not isinstance(operation,str): operation='unknown'
        try:
            request=validate_request(request)
            with self.manager.pin() as pin:
                pin.check()
                with Store(pin.database_path,pin.generation) as db:
                    result=self.lookup(db,pin,request)
                    ceiling = request['byte_budget'] if operation == 'get' else SEARCH_BYTES
                    if len(encode(result)) > ceiling: raise Refusal('budget_exhausted')
                # Even an empty result or operational count needs this final guard.
                pin.check()
                return result
        except Refusal as refusal:
            return error(operation,refusal.code)
        except (OSError,sqlite3.Error,ValueError,KeyError,TypeError):
            return error(operation,'index_unavailable')
