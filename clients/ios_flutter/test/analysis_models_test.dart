import 'package:flutter_test/flutter_test.dart';
import 'package:strategy_audit_app/features/analysis/analysis_models.dart';

void main() {
  test('maps API rules without raw market payload', () {
    final result = AnalysisResult.fromJson({
      'symbol': 'NVDA',
      'entry_time': '2026-08-05T14:17:32Z',
      'strategy': {'name': 'VWAP Reclaim', 'version': 1},
      'derived_context': {'provider': 'mock'},
      'feedback': <dynamic>[],
      'score': 82,
      'rules': [
        {
          'rule': 'reclaim_relative_volume',
          'label': 'Reclaim relative volume',
          'measurement': '1.21',
          'threshold': '>= 1.50',
          'weight': 15,
          'result': 'FAIL',
        },
      ],
      'bars': [
        {'open': 100}
      ],
    });
    expect(result.symbol, 'NVDA');
    expect(result.rules.single.status, RuleStatus.failed);
  });

  test('preserves unavailable scores', () {
    final result = AnalysisResult.fromJson({
      'symbol': 'TSLA',
      'entry_time': '2026-08-05T14:17:32Z',
      'strategy': {'name': 'VWAP Reclaim', 'version': 1},
      'derived_context': {'provider': 'mock'},
      'feedback': <dynamic>[],
      'rules': <dynamic>[]
    });
    expect(result.score, isNull);
    expect(result.symbol, 'TSLA');
  });
}
