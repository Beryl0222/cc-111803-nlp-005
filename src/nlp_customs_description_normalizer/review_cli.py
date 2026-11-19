import argparse
import json
from pathlib import Path

from .review import review


def load_case(case_path, registry_path, upto_round=None):
    case = json.loads(Path(case_path).read_text(encoding='utf-8'))
    registry = json.loads(Path(registry_path).read_text(encoding='utf-8'))
    return review(case, registry, upto_round=upto_round)


def main():
    parser = argparse.ArgumentParser(description='复核申报草稿、单据与已提交申报的关系')
    parser.add_argument('--case', type=Path, default=Path('fixtures/review-case.json'))
    parser.add_argument('--registry', type=Path, default=Path('fixtures/business.json'))
    parser.add_argument('--round', type=int, default=None, dest='round',
                        help='只使用第几轮复核前已收到的单据')
    args = parser.parse_args()
    try:
        result = load_case(args.case, args.registry, upto_round=args.round)
    except (OSError, KeyError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
