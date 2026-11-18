from collections import defaultdict


class CommodityCatalog:
    def __init__(self, entries):
        self.entries = {item['line']: item for item in entries}

    def confirm(self, item):
        entry = self.entries[item['line']]
        if item['designation'] not in entry['names'] or item['material'] != entry['material']:
            raise ValueError('品名或材质与采购记录不一致')
        if item['size'] != entry['size']:
            raise ValueError('申报规格待核')
        if item['unit'] not in entry['units']:
            raise ValueError('没有该包装单位的数量依据')
        count = item['count']
        if type(count) is not int or count < 1:
            raise ValueError('包装件数须为正整数')
        return count * entry['units'][item['unit']]


class StockBalance:
    def __init__(self, purchases, lodged):
        self.purchases = {line['line']: line['quantity'] for line in purchases}
        self.lodged = defaultdict(int)
        for item in lodged:
            if item['submitted']:
                self.lodged[item['line']] += item['quantity']

    def reserve(self, requests):
        available = {line: quantity - self.lodged[line] for line, quantity in self.purchases.items()}
        decisions = []
        for line, quantity in requests:
            accepted = 0 < quantity <= available[line]
            if accepted:
                available[line] -= quantity
            decisions.append(accepted)
        return decisions


class ClearanceReview:
    def __init__(self, slips):
        self.slips = {slip['id']: slip for slip in slips}

    def evaluate(self, row, quantity, accepted):
        slip = self.slips.get(row['packing_slip'])
        if not slip or slip['line'] != row['line']:
            decision = '需核对装箱依据'
        elif not accepted:
            decision = '订单余额不足'
        else:
            decision = '待申报'
        return {'id': row['id'], 'quantity': quantity, 'decision': decision, 'packing_slip': row['packing_slip']}


def assess(data, docs):
    catalog = CommodityCatalog(data['catalog'])
    converted = [(row['line'], catalog.confirm(row)) for row in data['draft']]
    reservations = StockBalance(docs['purchase_lines'], docs['declarations']).reserve(converted)
    review = ClearanceReview(data['slips'])
    return [review.evaluate(row, quantity, accepted)
            for row, (_, quantity), accepted in zip(data['draft'], converted, reservations)]
