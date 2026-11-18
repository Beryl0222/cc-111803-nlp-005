from pathlib import Path

from nlp_customs_description_normalizer.desk_cli import load_case


def test_submitted_items_consume_the_original_purchase_balance():
    fixture = Path(__file__).parents[1] / 'fixtures'
    output = load_case(fixture / 'work.json', fixture / 'business.json')
    assert output[0]['quantity'] == 5
    assert output[0]['decision'] == '待申报'
    assert output[1]['decision'] == '订单余额不足'
