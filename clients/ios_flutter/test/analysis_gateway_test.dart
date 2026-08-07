import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:strategy_audit_app/features/analysis/analysis_gateway.dart';

void main() {
  test('real HTTP adapter maps import through completed analysis', () async {
    final client = MockClient((request) async {
      if (request.url.path.endsWith('/imports')) {
        return http.Response(
            jsonEncode({
              'affected_trades': [
                {
                  'trade_id': 'trade-1',
                  'trade_revision_id': 'revision-1',
                  'analysis_eligible': true,
                  'symbol': 'AMD',
                  'direction': 'long',
                  'opened_at': '2026-08-05T14:17:32Z',
                  'closed_at': '2026-08-05T14:45:00Z',
                  'change_type': 'created'
                }
              ]
            }),
            201);
      }
      if (request.url.path.endsWith('/analysis-runs')) {
        return http.Response(
            jsonEncode({'id': 'run-1', 'status': 'queued'}), 202);
      }
      if (request.url.path.endsWith('/analysis-runs/run-1')) {
        return http.Response(
            jsonEncode(
                {'status': 'completed', 'trade_analysis_id': 'analysis-1'}),
            200);
      }
      return http.Response(
          jsonEncode({
            'symbol': 'AMD',
            'entry_time': '2026-08-05T14:17:32Z',
            'strategy': {'name': 'VWAP Reclaim', 'version': 1},
            'score': 80,
            'data_sufficiency': 'sufficient',
            'derived_context': {'provider': 'mock'},
            'rules': [
              {
                'rule': 'ema_9_above_20',
                'label': 'EMA alignment',
                'result': 'PASS',
                'measurement': '101 / 100',
                'threshold': 'EMA9 > EMA20',
                'weight': 15
              }
            ],
            'feedback': [],
            'comparison': {'status': 'insufficient_sample'}
          }),
          200);
    });
    final gateway = HttpAnalysisGateway(client: client)..accessToken = 'token';
    final affected = await gateway.importExecutions(Uint8List.fromList([1, 2]),
        'fills.csv', {'symbol': 'Symbol'}, 'America/New_York');
    final result = await gateway.analyzeTrade(affected.single);
    expect(result.symbol, 'AMD');
    expect(result.rules.single.label, 'EMA alignment');
  });

  test('real HTTP adapter exposes typed provider failure', () async {
    var calls = 0;
    final client = MockClient((request) async {
      calls += 1;
      if (calls == 1) {
        return http.Response(
            jsonEncode({
              'affected_trades': [
                {
                  'trade_id': 'trade-1',
                  'trade_revision_id': 'revision-1',
                  'analysis_eligible': true,
                  'symbol': 'AMD',
                  'direction': 'long',
                  'opened_at': '2026-08-05T14:17:32Z',
                  'closed_at': '2026-08-05T14:45:00Z',
                  'change_type': 'created'
                }
              ]
            }),
            201);
      }
      if (calls == 2) {
        return http.Response(jsonEncode({'id': 'run-1'}), 202);
      }
      return http.Response(
          jsonEncode({
            'status': 'failed',
            'failure_code': 'provider_error',
            'retryable': true
          }),
          200);
    });
    final gateway = HttpAnalysisGateway(client: client)..accessToken = 'token';
    final affected = await gateway.importExecutions(Uint8List.fromList([1]),
        'fills.csv', {'symbol': 'Symbol'}, 'America/New_York');
    expect(
        () => gateway.analyzeTrade(affected.single),
        throwsA(isA<GatewayError>()
            .having((value) => value.canRetryAnalysis, 'can retry', isTrue)));
  });

  test('transport and malformed responses become handled gateway errors',
      () async {
    final offline = HttpAnalysisGateway(
        client: MockClient(
            (request) => throw http.ClientException('offline', request.url)));
    await expectLater(
        offline.login('person@example.com', 'a-secure-password'),
        throwsA(isA<GatewayError>()
            .having((value) => value.code, 'code', 'network_unavailable')));

    final malformed = HttpAnalysisGateway(
        client: MockClient((request) async => http.Response('[]', 200)));
    await expectLater(
        malformed.login('person@example.com', 'a-secure-password'),
        throwsA(isA<GatewayError>()
            .having((value) => value.code, 'code', 'invalid_response')));
  });

  test('duplicate and accepted-but-open imports remain distinct', () async {
    final duplicate = HttpAnalysisGateway(
        client: MockClient((request) async =>
            http.Response(jsonEncode({'affected_trades': []}), 201)))
      ..accessToken = 'token';
    await expectLater(
        duplicate.importExecutions(Uint8List.fromList([1]), 'fills.csv',
            {'symbol': 'Symbol'}, 'America/New_York'),
        throwsA(isA<GatewayError>()
            .having((value) => value.code, 'code', 'duplicate_only')));

    final open = HttpAnalysisGateway(
        client: MockClient((request) async => http.Response(
            jsonEncode({
              'affected_trades': [
                {
                  'trade_id': 'trade-open',
                  'trade_revision_id': 'revision-open',
                  'analysis_eligible': false,
                  'symbol': 'AAPL',
                  'direction': 'long',
                  'opened_at': '2026-08-05T14:17:32Z',
                  'closed_at': null,
                  'change_type': 'created'
                }
              ]
            }),
            201)))
      ..accessToken = 'token';
    final affected = await open.importExecutions(Uint8List.fromList([1]),
        'fills.csv', {'symbol': 'Symbol'}, 'America/New_York');
    expect(affected.single.analysisEligible, isFalse);
    await expectLater(
        open.analyzeTrade(affected.single),
        throwsA(isA<GatewayError>()
            .having((value) => value.code, 'code', 'trade_open')));
  });

  test('retry starts a fresh run for the retained affected trade', () async {
    var runPosts = 0;
    final client = MockClient((request) async {
      if (request.url.path.endsWith('/imports')) {
        return http.Response(
            jsonEncode({
              'affected_trades': [
                {
                  'trade_id': 'affected-trade',
                  'trade_revision_id': 'revision-1',
                  'analysis_eligible': true,
                  'symbol': 'AAPL',
                  'direction': 'long',
                  'opened_at': '2026-08-05T14:17:32Z',
                  'closed_at': '2026-08-05T14:45:00Z',
                  'change_type': 'created'
                }
              ]
            }),
            201);
      }
      if (request.url.path.endsWith('/analysis-runs')) {
        runPosts += 1;
        final body = jsonDecode(request.body) as Map<String, dynamic>;
        expect(body['trade_id'], 'affected-trade');
        expect(body['trade_revision_id'], 'revision-1');
        if (runPosts == 2) {
          expect(body['retry_of_run_id'], 'run-1');
        }
        return http.Response(jsonEncode({'id': 'run-$runPosts'}), 202);
      }
      if (request.url.path.endsWith('/analysis-runs/run-1')) {
        return http.Response(
            jsonEncode({
              'status': 'failed',
              'failure_code': 'provider_error',
              'retryable': true
            }),
            200);
      }
      if (request.url.path.endsWith('/analysis-runs/run-2')) {
        return http.Response(
            jsonEncode(
                {'status': 'completed', 'trade_analysis_id': 'analysis-1'}),
            200);
      }
      return http.Response(
          jsonEncode({
            'symbol': 'AAPL',
            'entry_time': '2026-08-05T14:17:32Z',
            'strategy': {'name': 'VWAP Reclaim', 'version': 1},
            'score': 80,
            'derived_context': {'provider': 'mock'},
            'rules': [],
            'feedback': []
          }),
          200);
    });
    final gateway = HttpAnalysisGateway(client: client)..accessToken = 'token';
    final affected = await gateway.importExecutions(Uint8List.fromList([1]),
        'fills.csv', {'symbol': 'Symbol'}, 'America/New_York');
    await expectLater(
        gateway.analyzeTrade(affected.single), throwsA(isA<GatewayError>()));
    final result = await gateway.retryAnalysis();
    expect(result.symbol, 'AAPL');
    expect(runPosts, 2);
  });
}
