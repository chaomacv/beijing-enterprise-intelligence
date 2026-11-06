"""Conservative identity linkage; fuzzy similarity ranks review candidates only."""
import difflib
import re
import unicodedata
from collections import defaultdict

from .common import stable_id

CODE_CHARS = '0123456789ABCDEFGHJKLMNPQRTUWXY'
CODE_WEIGHTS = (1, 3, 9, 27, 19, 26, 16, 17, 20, 29, 25, 13, 8, 24, 10, 30, 28)


def normalize(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value or '')).casefold()


def valid_code(value):
    code = re.sub(r'\s+', '', (value or '').upper())
    if len(code) != 18 or any(c not in CODE_CHARS for c in code) or not code[2:8].isdigit(): return None
    check = CODE_CHARS[(31 - sum(CODE_CHARS.index(c) * w for c, w in zip(code[:17], CODE_WEIGHTS)) % 31) % 31]
    return code if code[-1] == check else None


class Resolver:
    def __init__(self):
        self.entities = {}
        self.codes = {}
        self.name_address = defaultdict(set)
        self.grams = defaultdict(set)
        self.decisions = []
        self.members = {}

    def assign(self, mention):
        name, address = normalize(mention['name']), normalize(mention.get('address'))
        code = valid_code(mention.get('credit_code'))
        mention_id = mention['mention_id']
        key = (name, address)
        candidates = set()
        # Limit each inverted list; overflow is explicitly sent to review.
        overflow = False
        for gram in {name[i:i + 3] for i in range(max(1, len(name) - 2))}:
            group = self.grams.get(gram, set())
            if len(group) > 100:
                overflow = True
            candidates.update(sorted(group)[:100])
        candidates.update(self.name_address.get(key, set()))
        if code and code in self.codes:
            eid = self.codes[code]
            reason, decision = 'same_checksum_valid_credit_code', 'MATCH'
        else:
            compatible = [e for e in self.name_address.get(key, set())
                          if address and not (code and self.entities[e]['credit_code'] and self.entities[e]['credit_code'] != code)]
            # A code-bearing mention never bridges two separately known identities.
            if not code and len(compatible) == 1:
                eid = compatible[0]
                reason, decision = 'exact_name_and_address', 'MATCH'
            else:
                eid = 'E_' + stable_id('code', code) if code else 'E_' + stable_id('provisional', mention_id)
                reason = 'new_valid_code' if code else 'insufficient_identity_evidence'
                decision = 'NEW' if code or not candidates else 'REVIEW'
                self.entities.setdefault(eid, {'entity_id': eid, 'credit_code': code, 'names': [], 'addresses': [],
                                               'identity_status': 'code_checksum_valid' if code else 'provisional'})
                if code: self.codes[code] = eid
        entity = self.entities[eid]
        if mention['name'] not in entity['names']: entity['names'].append(mention['name'])
        if mention.get('address') and mention['address'] not in entity['addresses']: entity['addresses'].append(mention['address'])
        self.name_address[key].add(eid)
        for gram in {name[i:i + 3] for i in range(max(1, len(name) - 2))}: self.grams[gram].add(eid)
        ranked = []
        for other in sorted(candidates - {eid})[:100]:
            target = self.entities[other]
            conflict = bool(code and target['credit_code'] and code != target['credit_code'])
            score = max((difflib.SequenceMatcher(None, name, normalize(n)).ratio() for n in target['names']), default=0)
            ranked.append({'entity_id': other, 'name_similarity': round(score, 4),
                           'decision': 'NON_MATCH' if conflict else 'REVIEW', 'credit_code_conflict': conflict})
        self.decisions.append({'mention_id': mention_id, 'entity_id': eid, 'decision': decision, 'reason': reason,
                               'raw_code': mention.get('credit_code'), 'valid_code': code,
                               'candidate_overflow': overflow, 'candidates': sorted(ranked, key=lambda x: -x['name_similarity'])})
        self.members[mention_id] = eid
        return eid


def resolve_results(results):
    resolver = Resolver()
    mentions = []
    for result in results:
        for index, entity in enumerate(result['entities']):
            mention = {'mention_id': stable_id(result['record_id'], index), 'record_id': result['record_id'],
                       'index': index, 'name': entity['name']['value'], 'role': entity['role'],
                       'credit_code': entity['credit_code']['value'] if entity['credit_code'] else None,
                       'address': entity['address']['value'] if entity['address'] else None}
            mentions.append(mention)
    # Strong identifiers first, so incomplete records can link conservatively afterwards.
    for mention in sorted(mentions, key=lambda m: (not bool(valid_code(m['credit_code'])), m['mention_id'])):
        mention['entity_id'] = resolver.assign(mention)
    return resolver, mentions
