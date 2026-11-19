import re
from collections import defaultdict

NUMBER_WORDS = {'一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5,
                '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
MATERIALS = ('不锈钢', '黄铜', '塑料', '钢', '铜', '铝')
CONTAINER_UNITS = ('盒', '箱')
PIECE_UNITS = ('只', '件', '个')
ACCESSORY_WORDS = ('备件', '配件')
CORRECTION_KINDS = ('补报', '冲减', '重报')

CLAUSE_SPLIT = re.compile(r'[，,；;。]')
INNER_NOTE = re.compile(r'^(盒|箱)内各([一二三四五六七八九十两]|\d+)\s*(只|件|个)$')
COUNT_UNIT = re.compile(r'([一二三四五六七八九十两]|\d+)\s*(只|盒|套|箱|件|个)')
MARKER_SEPARATE = re.compile(r'^另加')
MARKER_INCLUDED = re.compile(r'^(其中|含)')
MARKER_OTHER_CONTAINER = re.compile(r'^另(?=[一二三四五六七八九十两\d]+\s*[盒箱])')
TOKEN = re.compile(
    r'(?P<count>(?:[一二三四五六七八九十两]|\d+)\s*(?:只|盒|套|箱|件|个))'
    r'|(?P<size>[A-Za-z][\w-]*)'
    r'|(?P<material>不锈钢|黄铜|塑料|钢|铜|铝)'
    r'|(?P<sep>及|和)'
    r'|(?P<name>[^\W\d_一二三四五六七八九十两，,；;。及和]+)'
    r'|(?P<other>\S)'
)


def parse_count(token):
    token = token.strip()
    if token.isdigit():
        return int(token)
    return NUMBER_WORDS[token]


def _gather_name(tokens):
    gathered = {'material': None, 'name': None, 'size': None}
    consumed = 0
    for kind, value in tokens:
        if kind in ('count', 'sep'):
            break
        if kind == 'material' and gathered['material'] is None:
            gathered['material'] = value
        elif kind == 'size':
            gathered['size'] = value
        elif kind == 'name':
            gathered['name'] = (gathered['name'] or '') + value
        consumed += 1
    return gathered, consumed


def _has_name_before_count(tokens):
    for kind, _ in tokens:
        if kind == 'count':
            return False
        if kind == 'name':
            return True
    return False


def parse_description(text):
    """把装箱或发票的自由描述拆成商品段，并保留原文片段。

    每段给出品名、材质、规格、包装数量和配件关系（主项、另计、包含或未明）。
    单据没有写明的属性保持 None，由复核环节标为待核，不从目录猜测。
    """
    segments = []
    unparsed = []
    last_container_segment = None
    container_counter = 0
    for raw_clause in CLAUSE_SPLIT.split(text):
        clause = raw_clause.strip()
        if not clause:
            continue
        inner = INNER_NOTE.match(clause)
        if inner:
            if last_container_segment is None:
                unparsed.append(clause)
            else:
                last_container_segment['inner'] = {'count': parse_count(inner.group(2)),
                                                   'unit': inner.group(3)}
            continue
        clause_relation = None
        body = clause
        marker = MARKER_SEPARATE.match(body)
        if marker:
            clause_relation = '另计'
            body = body[marker.end():]
        else:
            marker = MARKER_INCLUDED.match(body)
            if marker:
                clause_relation = '包含'
                body = body[marker.end():]
            else:
                marker = MARKER_OTHER_CONTAINER.match(body)
                if marker:
                    body = body[marker.end():]
        tokens = [(match.lastgroup, match.group()) for match in TOKEN.finditer(body)]
        handled = False
        pending = {'material': None, 'name': None, 'size': None}
        sep_relation = None
        current_container = None

        def emit(count, unit):
            designation = pending['name']
            role = '配件' if designation and any(word in designation for word in ACCESSORY_WORDS) else '商品'
            if role == '商品':
                relation = '主项'
            else:
                relation = sep_relation or clause_relation or '未明'
            segment = {
                'designation': designation,
                'material': pending['material'],
                'size': pending['size'],
                'count': count,
                'unit': unit,
                'inner': None,
                'container': current_container,
                'role': role,
                'relation': relation,
                'text': clause,
            }
            segments.append(segment)
            return segment

        index = 0
        while index < len(tokens):
            kind, value = tokens[index]
            if kind == 'material':
                if pending['name'] is None and pending['material'] is None:
                    pending['material'] = value
            elif kind == 'size':
                pending['size'] = value
            elif kind == 'name':
                pending['name'] = (pending['name'] or '') + value
            elif kind == 'sep':
                sep_relation = '另计'
            elif kind == 'count':
                match = COUNT_UNIT.fullmatch(value)
                count = parse_count(match.group(1))
                unit = match.group(2)
                if pending['name'] is not None:
                    segment = emit(count, unit)
                    handled = True
                    if unit in CONTAINER_UNITS:
                        last_container_segment = segment
                        if count == 1:
                            container_counter += 1
                            segment['container'] = f'{unit}#{container_counter}'
                        else:
                            container_counter += count
                    pending = {'material': None, 'name': None, 'size': None}
                    sep_relation = None
                elif unit in CONTAINER_UNITS:
                    if _has_name_before_count(tokens[index + 1:]):
                        container_counter += 1
                        current_container = f'{unit}#{container_counter}'
                    else:
                        emit(count, unit)
                        pending = {'material': None, 'name': None, 'size': None}
                        sep_relation = None
                    handled = True
                else:
                    gathered, consumed = _gather_name(tokens[index + 1:])
                    if gathered['name'] is not None:
                        pending = gathered
                        emit(count, unit)
                        index += consumed
                        pending = {'material': None, 'name': None, 'size': None}
                        sep_relation = None
                    elif unit in PIECE_UNITS and last_container_segment is not None:
                        last_container_segment['inner'] = {'count': count, 'unit': unit}
                    else:
                        emit(count, unit)
                        pending = {'material': None, 'name': None, 'size': None}
                        sep_relation = None
                    handled = True
            index += 1
        if not handled:
            unparsed.append(clause)
    return {'segments': segments, 'unparsed': unparsed}


class DocumentSet:
    """同一批到货可以对应多份单据；后到的单据可以取代先到的单据。"""

    def __init__(self, documents, upto_round=None):
        self.documents = {}
        for document in documents:
            if upto_round is not None and document.get('round', 1) > upto_round:
                continue
            self.documents[document['id']] = document

    def _superseded_ids(self):
        return {document['supersedes'] for document in self.documents.values()
                if document.get('supersedes')}

    def effective(self):
        superseded = self._superseded_ids()
        return [document for document in self.documents.values()
                if document['id'] not in superseded]

    def effective_for(self, document_id):
        document = self.documents.get(document_id)
        if document is None:
            return None, []
        chain = []
        while True:
            successor = next((candidate for candidate in self.documents.values()
                              if candidate.get('supersedes') == document['id']), None)
            if successor is None:
                return document, chain
            chain.append(successor['id'])
            document = successor

    def batches(self):
        superseded = self._superseded_ids()
        grouped = {}
        for document in self.documents.values():
            batch = grouped.setdefault(document.get('batch', '未批注'),
                                       {'documents': [], 'superseded': []})
            key = 'superseded' if document['id'] in superseded else 'documents'
            batch[key].append(document['id'])
        return grouped


class Ledger:
    """已提交申报台账。补报、冲减、重报必须指明已提交申报标识。"""

    def __init__(self, declarations):
        self.records = {}
        for declaration in declarations:
            if not declaration.get('submitted'):
                continue
            if not declaration.get('id'):
                raise ValueError('已提交申报必须有标识')
            self.records[declaration['id']] = {
                'id': declaration['id'],
                'line': declaration['line'],
                'designation': declaration.get('designation'),
                'submitted': declaration['quantity'],
                'current': declaration['quantity'],
                'corrections': [],
            }

    def occupied(self, line):
        return sum(record['current'] for record in self.records.values()
                   if record['line'] == line)

    def apply(self, correction):
        kind = correction.get('kind')
        target = correction.get('target')
        quantity = correction.get('quantity')
        record = self.records.get(target)

        def invalid(reason):
            return {'id': correction.get('id'), 'kind': kind, 'target': target,
                    'quantity': quantity, 'status': '无效', 'reason': reason}

        if record is None:
            return invalid('更正对象必须是已提交申报')
        if kind not in CORRECTION_KINDS:
            return invalid(f'未知更正类型‘{kind}’')
        if type(quantity) is not int or quantity < 1:
            return invalid('更正数量须为正整数')
        old = record['current']
        if kind == '冲减':
            if quantity > old:
                return invalid('冲减数量超过已提交数量')
            record['current'] = old - quantity
        elif kind == '重报':
            record['current'] = quantity
        else:
            record['current'] = old + quantity
        record['corrections'].append(correction.get('id'))
        return {'id': correction.get('id'), 'kind': kind, 'target': target,
                'quantity': quantity, 'status': '有效',
                'effect': f"{record['line']} 净占用 {old} → {record['current']}"}

    def submitted_view(self):
        return [dict(record) for record in self.records.values()]


def attribute_segment(segment, catalog):
    designation = segment['designation']
    if designation is None:
        return []
    lines = []
    for line, entry in catalog.items():
        if designation not in entry.get('names', []):
            continue
        if segment['material'] and entry.get('material') and segment['material'] != entry['material']:
            continue
        if segment['size'] and entry.get('size') and segment['size'] != entry['size']:
            continue
        lines.append(line)
    return lines


def segment_base_quantity(segment, entry):
    if segment['unit'] in PIECE_UNITS:
        return segment['count']
    if segment.get('inner'):
        return segment['count'] * segment['inner']['count']
    if entry and segment['unit'] in entry.get('units', {}):
        return segment['count'] * entry['units'][segment['unit']]
    return None


def review(case, registry, upto_round=None):
    catalog = {entry['line']: entry for entry in case.get('catalog', [])}
    documents = DocumentSet(case.get('documents', []), upto_round=upto_round)
    ledger = Ledger(registry.get('declarations', []))
    corrections = [ledger.apply(correction) for correction in case.get('corrections', [])]
    purchased = {line['line']: line['quantity'] for line in registry['purchase_lines']}
    available = {line: quantity - ledger.occupied(line) for line, quantity in purchased.items()}
    available_before = dict(available)

    parsed = {document['id']: parse_description(document['text'])
              for document in documents.effective()}
    pending = []
    attributed = {}
    pools = {}
    for document in documents.effective():
        result = parsed[document['id']]
        for clause in result['unparsed']:
            pending.append(f"{document['id']}: 无法解析的原文‘{clause}’")
        for segment in result['segments']:
            lines = attribute_segment(segment, catalog)
            if not lines:
                pending.append(f"{document['id']}: 原文‘{segment['text']}’无法归入采购行")
                continue
            if len(lines) > 1:
                pending.append(f"{document['id']}: 原文‘{segment['text']}’可归入多个采购行"
                               f"（{'、'.join(lines)}），待确认")
                continue
            line = lines[0]
            attributed.setdefault((document['id'], line), []).append(segment)
            base = segment_base_quantity(segment, catalog[line])
            if base is None:
                pending.append(f"{document['id']}: 原文‘{segment['text']}’"
                               f"单位‘{segment['unit']}’无换算依据")
            else:
                pools.setdefault((document['id'], line), []).append({**segment, 'remaining': base})
            if segment['role'] == '配件' and segment['relation'] == '未明':
                pending.append(f"{document['id']}: 配件‘{segment['text']}’是否另计待确认")

    def evaluate_row(row):
        line = row.get('line')
        entry = catalog.get(line)
        issues = []
        evidence = []
        quantity = None
        conversion = None
        note = None
        doc, chain = documents.effective_for(row.get('packing_slip'))
        if doc is None:
            decision = '需核对装箱依据'
            issues.append(f"装箱单据缺失： {row.get('packing_slip')}")
        else:
            decision = None
            if chain:
                note = f"装箱依据更新为 {doc['id']}（取代 {row.get('packing_slip')}）"
            segments = attributed.get((doc['id'], line), [])
            if entry is None:
                issues.append(f'采购行 {line} 未登记目录')
            elif row.get('designation') not in entry.get('names', []):
                issues.append('品名与目录不符')
            if not segments:
                issues.append('装箱单据未列出该商品')
            else:
                materials = {segment['material'] for segment in segments if segment['material']}
                if not materials:
                    issues.append('材质未在单据写明，待核')
                elif row.get('material') and row['material'] not in materials:
                    issues.append('材质与单据不符')
                sizes = {segment['size'] for segment in segments if segment['size']}
                if not sizes:
                    issues.append('规格未在单据写明，待核')
                elif row.get('size') and row['size'] not in sizes:
                    issues.append('规格与单据不符')
            count = row.get('count')
            unit = row.get('unit')
            if entry is not None:
                if type(count) is not int or count < 1:
                    issues.append('包装件数须为正整数')
                elif unit not in entry.get('units', {}):
                    issues.append(f'单位‘{unit}’无换算依据')
                else:
                    inner = next((segment['inner'] for segment in segments
                                  if segment['unit'] == unit and segment.get('inner')), None)
                    if unit in PIECE_UNITS:
                        quantity = count
                        conversion = f'{count} {unit}'
                    elif inner is not None:
                        quantity = count * inner['count']
                        conversion = f"{count} {unit} × {inner['count']} 只/{unit} = {quantity} 只"
                    else:
                        per = entry['units'][unit]
                        quantity = count * per
                        conversion = f'{count} {unit} × {per} 只/{unit} = {quantity} 只（包装登记）'
            if quantity is not None:
                pool = pools.get((doc['id'], line), [])
                support = sum(segment['remaining'] for segment in pool)
                if support < quantity:
                    issues.append(f'装箱数量不足： 单据支持 {support} 只')
                else:
                    needed = quantity
                    matched = []
                    ordered = sorted(pool, key=lambda segment: 0 if segment['unit'] == unit else 1)
                    for segment in ordered:
                        if needed <= 0:
                            break
                        if segment['remaining'] <= 0:
                            continue
                        take = min(segment['remaining'], needed)
                        segment['remaining'] -= take
                        needed -= take
                        matched.append(segment)
                    seen = set()
                    for segment in matched:
                        key = (doc['id'], segment['text'])
                        if key in seen:
                            continue
                        seen.add(key)
                        evidence.append({'document': doc['id'], 'batch': doc.get('batch'),
                                         'text': segment['text']})
                    accessory = [segment for segment in matched if segment['role'] == '配件']
                    if accessory:
                        relations = {segment['relation'] for segment in accessory}
                        if '包含' in relations:
                            issues.append('配件数量已包含在主项中，不应另计')
                        elif '未明' in relations:
                            issues.append('配件是否另计待确认')
        existing = [{'id': record['id'], 'current': record['current']}
                    for record in ledger.submitted_view() if record['line'] == line]
        relation = {'kind': '新报'}
        if existing:
            relation['existing'] = existing
        description = None
        if quantity is not None:
            description = f"{row.get('material')}{row.get('designation')}（{row.get('size')}）{quantity} 只"
        item = {
            'id': row.get('id'),
            'line': line,
            'designation': row.get('designation'),
            'decision': decision,
            'quantity': quantity,
            'conversion': conversion,
            'description': description,
            'evidence': evidence,
            'issues': issues,
            'relation': relation,
            'packing_slip': row.get('packing_slip'),
        }
        if note:
            item['note'] = note
        return item

    items = [evaluate_row(row) for row in case.get('draft', [])]
    clean = {}
    for item in items:
        if item['decision'] is None and item['issues']:
            item['decision'] = '待核'
        if item['decision'] is None:
            clean.setdefault(item['line'], []).append(item)
    reserved = defaultdict(int)
    for item in items:
        if item['decision'] is not None:
            continue
        line = item['line']
        if item['quantity'] is not None and item['quantity'] <= available.get(line, 0):
            available[line] -= item['quantity']
            reserved[line] += item['quantity']
            item['decision'] = '待申报'
        else:
            item['decision'] = '订单余额不足'
    contentions = []
    for line, rows in clean.items():
        requested = sum(item['quantity'] for item in rows)
        if requested > available_before.get(line, 0):
            contentions.append({'line': line, 'items': [item['id'] for item in rows],
                                'requested': requested,
                                'available': available_before.get(line, 0)})
    for item in items:
        for issue in item['issues']:
            pending.append(f"{item['id']}: {issue}")
    return {
        'items': items,
        'corrections': corrections,
        'contentions': contentions,
        'pending': pending,
        'batches': documents.batches(),
        'submitted': ledger.submitted_view(),
        'balance': {line: {'purchased': purchased[line],
                           'occupied': ledger.occupied(line),
                           'reserved': reserved[line],
                           'remaining': available[line]}
                    for line in purchased},
    }
