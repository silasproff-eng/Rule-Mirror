import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../../core/app_config.dart';
import 'analysis_models.dart';

class GatewayError implements Exception {
  const GatewayError(this.code, this.message, {this.canRetryAnalysis = false});
  final String code;
  final String message;
  final bool canRetryAnalysis;
  @override
  String toString() => message;
}

class ImportPreview {
  const ImportPreview(this.headers, this.mapping, this.issues);
  final List<String> headers;
  final Map<String, String> mapping;
  final List<dynamic> issues;
}

class AffectedTrade {
  const AffectedTrade(
      {required this.tradeId,
      required this.revisionId,
      required this.symbol,
      required this.direction,
      required this.openedAt,
      required this.closedAt,
      required this.analysisEligible,
      required this.changeType});

  final String tradeId;
  final String revisionId;
  final String symbol;
  final String direction;
  final DateTime openedAt;
  final DateTime? closedAt;
  final bool analysisEligible;
  final String changeType;

  factory AffectedTrade.fromJson(Map<String, dynamic> value) => AffectedTrade(
      tradeId: value['trade_id'] as String,
      revisionId: value['trade_revision_id'] as String,
      symbol: value['symbol'] as String,
      direction: value['direction'] as String,
      openedAt: DateTime.parse(value['opened_at'] as String),
      closedAt: value['closed_at'] == null
          ? null
          : DateTime.parse(value['closed_at'] as String),
      analysisEligible: value['analysis_eligible'] as bool,
      changeType: value['change_type'] as String);
}

abstract class AnalysisGateway {
  Future<void> healthCheck();
  Future<void> register(String email, String password);
  Future<void> login(String email, String password);
  Future<ImportPreview> preview(Uint8List bytes, String filename);
  Future<List<AffectedTrade>> importExecutions(Uint8List bytes, String filename,
      Map<String, String> mapping, String timezone);
  Future<AnalysisResult> analyzeTrade(AffectedTrade trade);
  Future<AnalysisResult> retryAnalysis();
}

class HttpAnalysisGateway implements AnalysisGateway {
  HttpAnalysisGateway({http.Client? client}) : client = client ?? http.Client();
  final http.Client client;
  String? accessToken;
  String? lastTradeId;
  String? lastTradeRevisionId;
  String? lastFailedRunId;

  @override
  Future<void> healthCheck() async {
    final base = AppConfig.apiBaseUrl.replaceFirst(RegExp(r'/api/v1/?$'), '');
    await _normalize(() async {
      final response = await client.get(Uri.parse('$base/health'));
      _decode(response);
    }, timeout: const Duration(seconds: 5));
  }

  Uri _uri(String path) => Uri.parse('${AppConfig.apiBaseUrl}$path');

  Map<String, String> get _headers => {'Authorization': 'Bearer $accessToken'};

  Future<Map<String, dynamic>> _tokens(
      String path, String email, String password) async {
    final response = await client.post(_uri(path),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'email': email, 'password': password}));
    final value = _decode(response);
    accessToken = value['access_token'] as String;
    return value;
  }

  @override
  Future<void> register(String email, String password) async {
    await _normalize(() => _tokens('/auth/register', email, password));
  }

  @override
  Future<void> login(String email, String password) async {
    await _normalize(() => _tokens('/auth/login', email, password));
  }

  @override
  Future<ImportPreview> preview(Uint8List bytes, String filename) async {
    return _normalize(() async {
      final request = http.MultipartRequest('POST', _uri('/imports/preview'))
        ..headers.addAll(_headers)
        ..files.add(
            http.MultipartFile.fromBytes('file', bytes, filename: filename));
      final response =
          await http.Response.fromStream(await client.send(request));
      final value = _decode(response);
      return ImportPreview(
          List<String>.from(value['headers'] as List),
          Map<String, String>.from(value['suggested_mapping'] as Map),
          List<dynamic>.from(value['validation_issues'] as List));
    });
  }

  @override
  Future<List<AffectedTrade>> importExecutions(Uint8List bytes, String filename,
      Map<String, String> mapping, String timezone) async {
    return _normalize(() async {
      final request = http.MultipartRequest('POST', _uri('/imports'))
        ..headers.addAll(_headers)
        ..fields['mapping'] = jsonEncode(mapping)
        ..fields['timezone'] = timezone
        ..files.add(
            http.MultipartFile.fromBytes('file', bytes, filename: filename));
      final imported =
          _decode(await http.Response.fromStream(await client.send(request)));
      final affected = imported['affected_trades'] as List<dynamic>;
      if (affected.isEmpty) {
        throw const GatewayError(
            'duplicate_only', 'Every execution in this file already exists.');
      }
      return affected
          .cast<Map<String, dynamic>>()
          .map(AffectedTrade.fromJson)
          .toList();
    });
  }

  @override
  Future<AnalysisResult> analyzeTrade(AffectedTrade trade) async {
    if (!trade.analysisEligible) {
      throw const GatewayError('trade_open',
          'The import changed an open trade. Add its closing execution before analysis.');
    }
    lastTradeId = trade.tradeId;
    lastTradeRevisionId = trade.revisionId;
    lastFailedRunId = null;
    return _normalize(() => _analyze(trade.tradeId),
        canRetryAnalysis: true, timeout: const Duration(seconds: 20));
  }

  @override
  Future<AnalysisResult> retryAnalysis() async {
    if (lastTradeId == null) {
      throw const GatewayError(
          'retry_unavailable', 'There is no imported trade to retry.');
    }
    return _normalize(
        () => _analyze(lastTradeId!, retryOfRunId: lastFailedRunId),
        canRetryAnalysis: true,
        timeout: const Duration(seconds: 20));
  }

  Future<AnalysisResult> _analyze(String tradeId,
      {String? retryOfRunId}) async {
    final requestBody = <String, dynamic>{'trade_id': tradeId};
    if (lastTradeRevisionId != null) {
      requestBody['trade_revision_id'] = lastTradeRevisionId;
    }
    if (retryOfRunId != null) {
      requestBody['retry_of_run_id'] = retryOfRunId;
    }
    final runResponse = await client.post(_uri('/analysis-runs'),
        headers: {..._headers, 'Content-Type': 'application/json'},
        body: jsonEncode(requestBody));
    final run = _decode(runResponse);
    for (var attempt = 0; attempt < 40; attempt += 1) {
      final statusResponse = await client
          .get(_uri('/analysis-runs/${run['id']}'), headers: _headers);
      final status = _decode(statusResponse);
      if (status['status'] == 'failed') {
        lastFailedRunId = run['id'] as String;
        throw GatewayError(
            status['failure_code'] as String? ?? 'provider_failure',
            'Historical context could not be reconstructed.',
            canRetryAnalysis: status['retryable'] as bool? ?? true);
      }
      if (status['status'] == 'completed') {
        lastFailedRunId = null;
        final resultResponse = await client.get(
            _uri('/trade-analyses/${status['trade_analysis_id']}'),
            headers: _headers);
        return AnalysisResult.fromJson(_decode(resultResponse));
      }
      await Future<void>.delayed(const Duration(milliseconds: 250));
    }
    throw const GatewayError(
        'analysis_timeout', 'Analysis is taking longer than expected.',
        canRetryAnalysis: true);
  }

  Future<T> _normalize<T>(Future<T> Function() operation,
      {bool canRetryAnalysis = false,
      Duration timeout = const Duration(seconds: 15)}) async {
    try {
      return await operation().timeout(timeout);
    } on GatewayError {
      rethrow;
    } on TimeoutException {
      throw GatewayError('network_timeout',
          'The service did not respond in time. Check your connection and try again.',
          canRetryAnalysis: canRetryAnalysis);
    } on http.ClientException {
      throw GatewayError('network_unavailable',
          'The service is unavailable. Check your connection and try again.',
          canRetryAnalysis: canRetryAnalysis);
    } on FormatException {
      throw GatewayError(
          'invalid_response', 'The service returned an unreadable response.',
          canRetryAnalysis: canRetryAnalysis);
    } on TypeError {
      throw GatewayError(
          'invalid_response', 'The service returned an unexpected response.',
          canRetryAnalysis: canRetryAnalysis);
    }
  }

  Map<String, dynamic> _decode(http.Response response) {
    final decoded = jsonDecode(response.body.isEmpty ? '{}' : response.body);
    if (decoded is! Map<String, dynamic>) {
      throw const GatewayError(
          'invalid_response', 'The service returned an unexpected response.');
    }
    final value = decoded;
    if (response.statusCode >= 400) {
      final detail = value['detail'];
      if (detail is Map<String, dynamic>) {
        throw GatewayError(detail['code'] as String? ?? 'request_failed',
            detail['message'] as String? ?? 'The request failed.');
      }
      throw const GatewayError('request_failed', 'The request failed.');
    }
    return value;
  }
}
