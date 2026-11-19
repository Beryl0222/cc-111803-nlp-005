import json
from pathlib import Path

from nlp_customs_description_normalizer.review import parse_description, review
from nlp_customs_description_normalizer.review_cli import load_case

FIXTURES = Path(__file__).parents[1] / 'fixtures'


def load_main(upto_round=None):
    return load_case(FIXTURES / 'review-case.json', FIXTURES / 'business.json',
                     upto_round=upto_round)


def load_corrections_case():
    case = json.loads((FIXTURES / 'review-corrections.json').read_text(encoding='utf-8'))
    registry = json.loads((FIXTURES / 'business.json').read_text(encoding='utf-8'))
    return case, registry


def test_parse_outer_box_free_description():
    result = parse_description('轴套 A17 两盒，盒内各五只，另加两只黄铜备件')
    assert result['unparsed'] == []
    main, spare = result['segments']
    assert main['designation'] == '轴套'
    assert main['size'] == 'A17'
    assert main['material'] is None
    assert main['count'] == 2 and main['unit'] == '盒'
    assert main['inner'] == {'count': 5, 'unit': '只'}
    assert main['role'] == '商品' and main['relation'] == '主项'
    assert spare['designation'] == '备件'
    assert spare['material'] == '黄铜'
    assert spare['count'] == 2 and spare['unit'] == '只'
    assert spare['role'] == '配件' and spare['relation'] == '另计'
    assert spare['text'] == '另加两只黄铜备件'


def test_parse_mixed_box_inspection():
    result = parse_description('钢轴套 A17 一盒五只，另一盒钢轴套三只及黄铜备件 A17 两只')
    first, second, spare = result['segments']
    assert first['material'] == '钢' and first['inner'] == {'count': 5, 'unit': '只'}
    assert first['container'] == '盒#1'
    assert second['count'] == 3 and second['unit'] == '只'
    assert spare['designation'] == '备件' and spare['material'] == '黄铜'
    assert spare['size'] == 'A17' and spare['relation'] == '另计'
    assert second['container'] == spare['container'] == '盒#2'


def test_parse_invoice_lists_accessory_as_tao_with_unknown_relation():
    result = parse_description('轴套 A17 十只，备件两套')
    main, spare = result['segments']
    assert main['count'] == 10 and main['unit'] == '只'
    assert spare['unit'] == '套'
    assert spare['role'] == '配件' and spare['relation'] == '未明'


def test_parse_unhandled_clause_is_kept_for_review():
    result = parse_description('轴套 A17 两盒，质保一年')
    assert result['unparsed'] == ['质保一年']


def test_first_review_flags_unstated_material_and_size():
    report = load_main(upto_round=1)
    items = {item['id']: item for item in report['items']}
    assert items['D-1']['decision'] == '待核'
    assert any('材质' in issue for issue in items['D-1']['issues'])
    assert items['D-2']['decision'] == '待核'
    assert items['D-3']['decision'] == '待核'
    assert any('规格' in issue for issue in items['D-3']['issues'])
    assert any('材质' in note for note in report['pending'])
    assert any('规格' in note for note in report['pending'])


def test_independently_verifiable_quantity_proceeds_during_rereview():
    report = load_main(upto_round=1)
    items = {item['id']: item for item in report['items']}
    assert items['D-4']['decision'] == '待申报'
    assert items['D-4']['conversion'] == '1 盒 × 5 只/盒 = 5 只（包装登记）'
    assert report['balance']['PO-18/1']['reserved'] == 5


def test_rereview_after_late_packing_list_updates_conclusions():
    report = load_main()
    items = {item['id']: item for item in report['items']}
    first = items['D-1']
    assert first['decision'] == '待申报'
    assert first['quantity'] == 5
    assert first['conversion'] == '1 盒 × 5 只/盒 = 5 只'
    assert first['evidence'][0]['document'] == 'INS-7'
    assert '一盒五只' in first['evidence'][0]['text']
    assert 'PK-9' in first['note'] and 'INS-7' in first['note']
    spare = items['D-3']
    assert spare['decision'] == '待申报'
    assert spare['quantity'] == 2
    assert items['D-2']['decision'] == '订单余额不足'


def test_splits_competing_for_the_same_purchase_balance_are_listed():
    report = load_main()
    contention = {entry['line']: entry for entry in report['contentions']}
    assert contention['PO-18/1']['items'] == ['D-1', 'D-2', 'D-4']
    assert contention['PO-18/1']['requested'] == 11
    assert contention['PO-18/1']['available'] == 5
    assert 'PO-18/2' not in contention


def test_invoice_accessory_listed_as_tao_stays_pending():
    report = load_main()
    assert any('INV-4' in note and '套' in note for note in report['pending'])
    assert any('INV-4' in note and '另计' in note for note in report['pending'])


def test_batches_distinguish_documents_of_one_shipment_from_two_shipments():
    report = load_main()
    batches = report['batches']
    assert set(batches) == {'B-1', 'B-2'}
    assert set(batches['B-1']['documents']) == {'INV-4', 'INS-7'}
    assert batches['B-1']['superseded'] == ['PK-9']
    assert batches['B-2']['documents'] == ['PK-10']
    items = {item['id']: item for item in report['items']}
    assert items['D-4']['evidence'][0]['batch'] == 'B-2'


def test_submitted_declarations_can_be_looked_up():
    report = load_main()
    submitted = {entry['id']: entry for entry in report['submitted']}
    assert submitted['DEC-1']['current'] == 5
    assert submitted['DEC-1']['submitted'] == 5
    assert 'DEC-2' not in submitted


def test_review_conclusion_states_relation_to_existing_declarations():
    report = load_main()
    items = {item['id']: item for item in report['items']}
    relation = items['D-1']['relation']
    assert relation['kind'] == '新报'
    assert relation['existing'] == [{'id': 'DEC-1', 'current': 5}]


def test_offset_correction_releases_balance_without_double_deduction():
    case, registry = load_corrections_case()
    report = review(case, registry)
    correction = report['corrections'][0]
    assert correction['status'] == '有效'
    assert correction['target'] == 'DEC-1'
    assert correction['effect'] == 'PO-18/1 净占用 5 → 3'
    balance = report['balance']['PO-18/1']
    assert balance['occupied'] == 3
    assert balance['remaining'] == 10 - 3 - 6
    items = {item['id']: item for item in report['items']}
    assert items['D-1']['decision'] == '待申报'
    assert items['D-2']['decision'] == '待申报'
    submitted = {entry['id']: entry for entry in report['submitted']}
    assert submitted['DEC-1']['current'] == 3
    assert submitted['DEC-1']['corrections'] == ['C-1']


def test_redeclaration_replaces_submitted_quantity_instead_of_stacking():
    case, registry = load_corrections_case()
    case['corrections'] = [{'id': 'C-2', 'kind': '重报', 'target': 'DEC-1', 'quantity': 3}]
    report = review(case, registry)
    assert report['balance']['PO-18/1']['occupied'] == 3
    assert report['corrections'][0]['status'] == '有效'


def test_supplementary_declaration_consumes_balance_once():
    case, registry = load_corrections_case()
    case['corrections'] = [{'id': 'C-3', 'kind': '补报', 'target': 'DEC-1', 'quantity': 2}]
    report = review(case, registry)
    assert report['balance']['PO-18/1']['occupied'] == 7
    items = {item['id']: item for item in report['items']}
    assert items['D-1']['decision'] == '订单余额不足'


def test_correction_must_target_a_submitted_declaration():
    case, registry = load_corrections_case()
    case['corrections'] = [
        {'id': 'C-4', 'kind': '冲减', 'target': 'DEC-2', 'quantity': 1},
        {'id': 'C-5', 'kind': '冲减', 'target': 'DEC-9', 'quantity': 1},
        {'id': 'C-6', 'kind': '冲减', 'target': 'DEC-1', 'quantity': 99},
        {'id': 'C-7', 'kind': '改报', 'target': 'DEC-1', 'quantity': 1},
    ]
    report = review(case, registry)
    assert [entry['status'] for entry in report['corrections']] == ['无效'] * 4
    assert report['balance']['PO-18/1']['occupied'] == 5
