import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:strategy_audit_app/features/analysis/analysis_gateway.dart';

void main() {
  test('refreshes once after an expired access token and retries trades',
      () async {
    var tradeRequests = 0;
    final gateway = HttpAnalysisGateway(client: MockClient((request) async {
      if (request.url.path.endsWith('/auth/refresh')) {
        return http.Response(
            jsonEncode(
                {'access_token': 'new-access', 'refresh_token': 'new-refresh'}),
            200);
      }
      if (request.url.path.endsWith('/trades')) {
        tradeRequests += 1;
        return tradeRequests == 1
            ? http.Response(
                jsonEncode({
                  'detail': {'code': 'expired', 'message': 'expired'}
                }),
                401)
            : http.Response('[]', 200);
      }
      return http.Response('{}', 404);
    }))
      ..accessToken = 'old-access'
      ..refreshToken = 'refresh';
    expect(await gateway.trades(), isEmpty);
    expect(gateway.accessToken, 'new-access');
    expect(tradeRequests, 2);
  });

  test('clears authentication when refresh fails', () async {
    final gateway = HttpAnalysisGateway(
        client: MockClient((request) async => http.Response(
            jsonEncode({
              'detail': {'code': 'invalid_refresh_token', 'message': 'invalid'}
            }),
            401)))
      ..accessToken = 'old-access'
      ..refreshToken = 'bad-refresh';
    await expectLater(
        gateway.trades(),
        throwsA(isA<GatewayError>()
            .having((value) => value.code, 'code', 'authentication_required')));
    expect(gateway.accessToken, isNull);
    expect(gateway.refreshToken, isNull);
  });

  test('real HTTP adapter maps import through completed analysis', () async {
    Map<String, dynamic>? analysisRequest;
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
        analysisRequest = jsonDecode(request.body) as Map<String, dynamic>;
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
    final result = await gateway.analyzeTrade(affected.single,
        strategySlug: 'vwap-reclaim');
    expect(result.symbol, 'AMD');
    expect(result.rules.single.label, 'EMA alignment');
    expect(analysisRequest?['strategy_slug'], 'vwap-reclaim');
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

  test('import history preserves array contract and cap metadata', () async {
    final gateway = HttpAnalysisGateway(
        client: MockClient((request) async => http.Response(
            jsonEncode([
              {
                'id': 'batch-1',
                'display_name': 'orders.csv',
                'status': 'completed',
                'created_at': '2026-08-07T14:30:00+00:00',
                'accepted_execution_count': 4,
                'affected_trade_count': 2,
                'duplicate_count': 1,
                'error_count': 0
              }
            ]),
            200,
            headers: {'x-result-limit': '20'})))
      ..accessToken = 'token';

    final history = await gateway.importHistory();

    expect(history.single.displayName, 'orders.csv');
    expect(history.single.acceptedExecutionCount, 4);
    expect(gateway.lastImportsWasLimited, isTrue);
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
        expect(body['strategy_slug'], 'opening-range-breakout');
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
        gateway.analyzeTrade(affected.single,
            strategySlug: 'opening-range-breakout'),
        throwsA(isA<GatewayError>()));
    final result = await gateway.retryAnalysis();
    expect(result.symbol, 'AAPL');
    expect(runPosts, 2);
  });
}
