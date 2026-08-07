enum RuleStatus { passed, failed, insufficient, notApplicable }

class RuleEvidence {
  const RuleEvidence(
      this.label, this.measurement, this.threshold, this.status, this.weight);
  final String label;
  final String measurement;
  final String threshold;
  final RuleStatus status;
  final int weight;
}

class AnalysisResult {
  const AnalysisResult(
      {required this.symbol,
      required this.strategyName,
      required this.strategyVersion,
      required this.entryTime,
      required this.score,
      required this.rules,
      required this.feedback,
      required this.provider});
  final String symbol;
  final String strategyName;
  final int strategyVersion;
  final DateTime entryTime;
  final int? score;
  final List<RuleEvidence> rules;
  final List<Map<String, String>> feedback;
  final String provider;

  factory AnalysisResult.fromJson(Map<String, dynamic> value) {
    final rules = (value['rules'] as List<dynamic>? ?? []).map((dynamic item) {
      final row = item as Map<String, dynamic>;
      final status = switch (row['result'] as String) {
        'PASS' => RuleStatus.passed,
        'FAIL' => RuleStatus.failed,
        'INSUFFICIENT_DATA' => RuleStatus.insufficient,
        _ => RuleStatus.notApplicable,
      };
      return RuleEvidence(
          row['label'] as String,
          row['measurement']?.toString() ?? 'Unavailable',
          row['threshold']?.toString() ?? 'None',
          status,
          row['weight'] as int);
    }).toList();
    final strategy = value['strategy'] as Map<String, dynamic>;
    final derived = value['derived_context'] as Map<String, dynamic>;
    return AnalysisResult(
        symbol: value['symbol'] as String,
        strategyName: strategy['name'] as String,
        strategyVersion: strategy['version'] as int,
        entryTime: DateTime.parse(value['entry_time'] as String),
        score: value['score'] as int?,
        rules: rules,
        feedback: (value['feedback'] as List<dynamic>)
            .map((dynamic item) => Map<String, String>.from(item as Map))
            .toList(),
        provider: derived['provider'] as String);
  }
}
