import 'dart:typed_data';

import 'package:strategy_audit_app/features/analysis/analysis_gateway.dart';
import 'package:strategy_audit_app/features/analysis/analysis_models.dart';

class FakeGateway implements AnalysisGateway {
  FakeGateway(
      {AnalysisResult? result,
      this.previewFailure,
      this.analysisFailure,
      this.failAnalysisOnce = false,
      List<AffectedTrade>? affectedTrades})
      : result = result ?? sampleResult,
        affectedTrades = affectedTrades ?? [sampleAffectedTrade];
  final AnalysisResult result;
  final GatewayError? previewFailure;
  final GatewayError? analysisFailure;
  final bool failAnalysisOnce;
  final List<AffectedTrade> affectedTrades;
  bool hasFailedAnalysis = false;
  AffectedTrade? selectedTrade;
  Map<String, String>? submittedMapping;

  @override
  Future<void> login(String email, String password) async {}

  @override
  Future<void> register(String email, String password) async {}

  @override
  Future<ImportPreview> preview(Uint8List bytes, String filename) async {
    if (previewFailure != null) throw previewFailure!;
    return const ImportPreview([
      'Symbol',
      'Side',
      'Quantity',
      'Price',
      'Execution Time'
    ], {
      'symbol': 'Symbol',
      'side': 'Side',
      'quantity': 'Quantity',
      'price': 'Price',
      'executed_at': 'Execution Time'
    }, []);
  }

  @override
  Future<List<AffectedTrade>> importExecutions(Uint8List bytes, String filename,
      Map<String, String> mapping, String timezone) async {
    submittedMapping = mapping;
    return affectedTrades;
  }

  @override
  Future<AnalysisResult> analyzeTrade(AffectedTrade trade) async {
    selectedTrade = trade;
    if (analysisFailure != null && (!failAnalysisOnce || !hasFailedAnalysis)) {
      hasFailedAnalysis = true;
      throw analysisFailure!;
    }
    return result;
  }

  @override
  Future<AnalysisResult> retryAnalysis() async {
    if (analysisFailure != null && !failAnalysisOnce) {
      throw analysisFailure!;
    }
    return result;
  }
}

final sampleAffectedTrade = AffectedTrade(
    tradeId: 'trade-1',
    revisionId: 'revision-1',
    symbol: 'AAPL',
    direction: 'long',
    openedAt: DateTime.parse('2026-08-05T14:17:32Z'),
    closedAt: DateTime.parse('2026-08-05T14:45:00Z'),
    analysisEligible: true,
    changeType: 'created');

final sampleResult = AnalysisResult(
  symbol: 'AAPL',
  strategyName: 'VWAP Reclaim',
  strategyVersion: 1,
  entryTime: DateTime.parse('2026-08-05T14:17:32Z'),
  score: 82,
  provider: 'mock',
  feedback: const [
    {
      'rule': 'prior_close_below_vwap',
      'category': 'matched',
      'sentence': 'Price was below VWAP before the reclaim.'
    },
    {
      'rule': 'reclaim_relative_volume',
      'category': 'missed',
      'sentence': 'Reclaim volume was below the configured threshold.'
    },
  ],
  rules: const [
    RuleEvidence(
        'Prior close below VWAP', 'true', 'true', RuleStatus.passed, 20),
    RuleEvidence(
        'Reclaim relative volume', '1.21', '>= 1.50', RuleStatus.failed, 15),
  ],
);
