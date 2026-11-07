"""Strict source-bound extraction contracts and an explicitly named rule baseline."""
import json

from .common import ontology, text

STATUSES = {'EXTRACTED', 'NO_EVENT', 'REVIEW'}
EVENT_STATUSES = {'confirmed', 'proposed', 'removed', 'revoked', 'unknown'}
ROLES = {'subject', 'supplier', 'buyer', 'authority', 'other'}
CONTRACT_VERSION = 'extraction-v2-source-title'


def obj(properties):
    return {'type': 'object', 'properties': properties, 'required': list(properties), 'additionalProperties': False}


REF = obj({'field': {'type': 'string'}, 'value': {'type': 'string'}})
NULL_REF = {'anyOf': [REF, {'type': 'null'}]}
ENTITY = obj({'role': {'type': 'string', 'enum': sorted(ROLES)}, 'name': REF,
              'credit_code': NULL_REF, 'address': NULL_REF})
EVENT = obj({'subject_index': {'type': 'integer'}, 'event_type': {'type': 'string', 'enum': list(ontology()['events'])},
             'status': {'type': 'string', 'enum': sorted(EVENT_STATUSES)}, 'date': NULL_REF, 'amount': NULL_REF,
             'document_no': NULL_REF, 'evidence': {'type': 'array', 'items': REF, 'minItems': 1}})
RESULT = obj({'record_id': {'type': 'string'}, 'status': {'type': 'string', 'enum': sorted(STATUSES)},
              'entities': {'type': 'array', 'items': ENTITY}, 'events': {'type': 'array', 'items': EVENT}})
EXTRACTION_SCHEMA = obj({'results': {'type': 'array', 'items': RESULT}})
SCREEN_SCHEMA = obj({'decision': {'type': 'string', 'enum': ['KEEP', 'REVIEW', 'DROP']},
                     'event_types': {'type': 'array', 'items': {'type': 'string', 'enum': list(ontology()['events'])}},
                     'reason': {'type': 'string'}, 'evidence_fields': {'type': 'array', 'items': {'type': 'string'}}})


def validate_ref(ref, row, filename=None):
    if not isinstance(ref, dict) or set(ref) != {'field', 'value'}:
        raise ValueError('Invalid source reference')
    value = ref['value']
    cells = {**row['cells'], **({'__filename__':filename} if filename else {})}
    if not isinstance(value, str) or not value or ref['field'] not in cells or value not in text(cells[ref['field']]):
        raise ValueError('Evidence is absent from the cited source cell')


def validate_results(data, records, card=None):
    if not isinstance(data, dict) or set(data) != {'results'} or not isinstance(data['results'], list):
        raise ValueError('Invalid extraction result')
    expected = {r['record_id']: r for r in records}
    ids = [r.get('record_id') for r in data['results']]
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise ValueError('Missing, duplicated, or foreign source record IDs')
    for result in data['results']:
        if set(result) != {'record_id', 'status', 'entities', 'events'} or result['status'] not in STATUSES:
            raise ValueError('Invalid record status')
        row = expected[result['record_id']]
        if not isinstance(result['entities'], list) or not isinstance(result['events'], list):
            raise ValueError('Expected arrays')
        if result['status'] == 'REVIEW' and (result['entities'] or result['events']):
            raise ValueError('Uncertain facts must not enter the confirmed fact store')
        if result['status'] == 'NO_EVENT' and result['events']:
            raise ValueError('NO_EVENT cannot contain events')
        if result['status'] == 'EXTRACTED' and not result['events']:
            raise ValueError('EXTRACTED requires at least one event')
        for entity in result['entities']:
            if set(entity) != {'role', 'name', 'credit_code', 'address'} or entity['role'] not in ROLES:
                raise ValueError('Invalid entity contract')
            validate_ref(entity['name'], row)
            for field in ('credit_code', 'address'):
                if entity[field] is not None: validate_ref(entity[field], row)
        for event in result['events']:
            if set(event) != {'subject_index', 'event_type', 'status', 'date', 'amount', 'document_no', 'evidence'}:
                raise ValueError('Invalid event contract')
            index = event['subject_index']
            if type(index) is not int or not 0 <= index < len(result['entities']): raise ValueError('Invalid event subject')
            if event['event_type'] not in ontology()['events'] or event['status'] not in EVENT_STATUSES:
                raise ValueError('Unknown event type/status')
            if not event['evidence']: raise ValueError('Missing event evidence')
            for ref in event['evidence']: validate_ref(ref, row, (card or {}).get('filename'))
            for field in ('date', 'amount', 'document_no'):
                if event[field] is not None: validate_ref(event[field], row)
    return data['results']


def validate_screen(data, card):
    if not isinstance(data, dict) or set(data) != {'decision', 'event_types', 'reason', 'evidence_fields'}:
        raise ValueError('Invalid file-screen contract')
    if data['decision'] not in {'KEEP', 'REVIEW', 'DROP'} or not isinstance(data['reason'], str):
        raise ValueError('Invalid screening decision')
    if any(t not in ontology()['events'] for t in data['event_types']): raise ValueError('Unknown event type')
    if any(f not in set(card['columns']) | {'__filename__'} for f in data['evidence_fields']):
        raise ValueError('Screening cited an absent field')
    if data['decision'] == 'KEEP' and not data['evidence_fields']: raise ValueError('KEEP requires a cited field')
    return data


def review_result(record_id, reason=None):
    return {'record_id': record_id, 'status': 'REVIEW', 'entities': [], 'events': []}


def first_ref(cells, aliases):
    for key in aliases:
        value = cells.get(key)
        if value is not None and text(value).strip(): return {'field': key, 'value': text(value).strip()}
    return None


class RuleBaseline:
    name = 'rules-v1-explicit-baseline'
    def screen(self, card):
        ont = ontology()
        fields = [f for f in card['columns'] if f in ont['name_fields']]
        types = [key for key, item in ont['events'].items() if any(k in card['filename'] for k in item['keywords'])]
        if card['quality_flags']: decision = 'REVIEW'
        elif fields: decision = 'KEEP'
        elif types: decision = 'REVIEW'
        else: decision = 'DROP'
        return {'decision': decision, 'event_types': types, 'reason': 'Explicit filename/header rule baseline', 'evidence_fields': fields or ['__filename__']}

    def extract(self, records, card):
        ont = ontology()
        types = self.screen(card)['event_types']
        result = []
        for row in records:
            cells = row['cells']
            name = first_ref(cells, ont['name_fields'])
            if not name:
                result.append(review_result(row['record_id'])); continue
            role = {'供应商': 'supplier', '采购人': 'buyer'}.get(name['field'], 'subject')
            entity = {'role': role, 'name': name, 'credit_code': first_ref(cells, ont['code_fields']), 'address': first_ref(cells, ont['address_fields'])}
            full = ' '.join(cells.values())
            status = 'unknown'
            if any(k in full for k in ('拟支持', '拟认定', '拟推荐', '拟培训')) or '拟培训' in card['filename']: status = 'proposed'
            elif any(k in full for k in ('撤销', '撤回')): status = 'revoked'
            elif '移出' in full: status = 'removed'
            elif any(k in full for k in ('已认定', '已批准', '已处罚', '已中标', '已拨付')): status = 'confirmed'
            events = []
            # An explicit row fact is required. Filename-only categories do not create events.
            fact = first_ref(cells, ['事件内容', '处罚内容', '处罚结果', '认定结果', '状态', '结果'])
            if fact and fact['value'] not in ('合格', '检查合格', '未发现问题', '无'):
                for typ in types:
                    events.append({'subject_index': 0, 'event_type': typ, 'status': status,
                                   'date': first_ref(cells, ont['date_fields']),
                                   'amount': first_ref(cells, ['金额', '罚款金额', '罚款金额（万元）']),
                                   'document_no': first_ref(cells, ont['document_fields']), 'evidence': [fact]})
            result.append({'record_id': row['record_id'], 'status': 'EXTRACTED' if events else 'NO_EVENT', 'entities': [entity], 'events': events})
        return validate_results({'results': result}, records, card)
