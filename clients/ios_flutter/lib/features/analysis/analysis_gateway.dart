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

class PortfolioHolding {
  const PortfolioHolding(
      {required this.symbol,
      required this.quantity,
      this.marketValue,
      required this.source});
  final String symbol;
  final double quantity;
  final double? marketValue;
  final String source;
  factory PortfolioHolding.fromJson(Map<String, dynamic> value) =>
      PortfolioHolding(
          symbol: value['symbol'] as String,
          quantity: (value['quantity'] as num).toDouble(),
          marketValue: (value['market_value'] as num?)?.toDouble(),
          source: value['source'] as String);
}

class PortfolioSummary {
  const PortfolioSummary({this.portfolioValue, required this.holdings});
  final double? portfolioValue;
  final List<PortfolioHolding> holdings;
  factory PortfolioSummary.fromJson(
          Map<String, dynamic> value) =>
      PortfolioSummary(
          portfolioValue: (value['portfolio_value'] as num?)?.toDouble(),
          holdings: (value['holdings'] as List<dynamic>)
              .map((item) =>
                  PortfolioHolding.fromJson(item as Map<String, dynamic>))
              .toList());
}

class TradeHistory {
  const TradeHistory(
      {required this.tradeId,
      required this.symbol,
      required this.direction,
      required this.openedAt,
      this.closedAt,
      this.realizedPnl,
      this.score,
      required this.analyzed});
  final String tradeId;
  final String symbol;
  final String direction;
  final DateTime openedAt;
  final DateTime? closedAt;
  final double? realizedPnl;
  final double? score;
  final bool analyzed;
  factory TradeHistory.fromJson(Map<String, dynamic> value) => TradeHistory(
      tradeId: value['trade_id'] as String,
      symbol: value['symbol'] as String,
      direction: value['direction'] as String,
      openedAt: DateTime.parse(value['opened_at'] as String),
      closedAt: value['closed_at'] == null
          ? null
          : DateTime.parse(value['closed_at'] as String),
      realizedPnl: (value['realized_pnl'] as num?)?.toDouble(),
      score: (value['score'] as num?)?.toDouble(),
      analyzed: value['analyzed'] as bool);
}

class AccountProfile {
  const AccountProfile(
      {required this.username,
      this.displayName,
      required this.publicProfile,
      required this.metrics});
  final String username;
  final String? displayName;
  final bool publicProfile;
  final Map<String, dynamic> metrics;
  factory AccountProfile.fromJson(Map<String, dynamic> value) => AccountProfile(
      username: value['username'] as String,
      displayName: value['display_name'] as String?,
      publicProfile: value['public_profile'] as bool,
      metrics: Map<String, dynamic>.from(value['metrics'] as Map));
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
  Future<PortfolioSummary> portfolio();
  Future<void> importPortfolio(Uint8List bytes, String filename);
  Future<List<TradeHistory>> trades();
  Future<void> deleteTrade(String tradeId);
  Future<AccountProfile> profile();
  Future<AccountProfile> updateProfile(String displayName);
  Future<void> setPublicProfile(bool enabled);
  Future<List<AccountProfile>> searchAccounts(String query);
  Future<ImportPreview> preview(Uint8List bytes, String filename);
  Future<List<AffectedTrade>> importExecutions(Uint8List bytes, String filename,
      Map<String, String> mapping, String timezone);
  Future<AnalysisResult> analyzeTrade(AffectedTrade trade);
  Future<AnalysisResult> retryAnalysis();
}

class HttpAnalysisGateway implements AnalysisGateway {
  HttpAnalysisGateway({http.Client? client, this.onAuthenticationExpired})
      : client = client ?? http.Client();
  final http.Client client;
  final void Function()? onAuthenticationExpired;
  String? accessToken;
  String? refreshToken;
  String? accountEmail;
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

  Future<http.Response> _authenticated(
      Future<http.Response> Function(Map<String, String> headers)
          request) async {
    var response = await request(_headers);
    if (response.statusCode != 401) return response;
    final token = refreshToken;
    if (token == null) {
      _clearAuthentication(notify: true);
      throw const GatewayError('authentication_required',
          'Your session has ended. Please sign in again.');
    }
    try {
      final refreshed = _decode(await client.post(_uri('/auth/refresh'),
          headers: {'Content-Type': 'application/json'},
          body: jsonEncode({'refresh_token': token})));
      accessToken = refreshed['access_token'] as String;
      refreshToken = refreshed['refresh_token'] as String?;
      response = await request(_headers);
      if (response.statusCode != 401) return response;
    } catch (_) {}
    _clearAuthentication(notify: true);
    throw const GatewayError('authentication_required',
        'Your session has ended. Please sign in again.');
  }

  void _clearAuthentication({bool notify = false}) {
    accessToken = null;
    refreshToken = null;
    accountEmail = null;
    if (notify) onAuthenticationExpired?.call();
  }

  Future<Map<String, dynamic>> _tokens(
      String path, String email, String password) async {
    final response = await client.post(_uri(path),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'email': email, 'password': password}));
    final value = _decode(response);
    accessToken = value['access_token'] as String;
    refreshToken = value['refresh_token'] as String?;
    accountEmail = email;
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
  Future<PortfolioSummary> portfolio() async => _normalize(() async {
        final value = _decode(await _authenticated(
            (headers) => client.get(_uri('/portfolio'), headers: headers)));
        return PortfolioSummary.fromJson(value);
      });

  @override
  Future<void> importPortfolio(Uint8List bytes, String filename) async =>
      _normalize(() async {
        _decode(await _authenticated((headers) async {
          final request =
              http.MultipartRequest('POST', _uri('/portfolio/import'))
                ..headers.addAll(headers)
                ..files.add(http.MultipartFile.fromBytes('file', bytes,
                    filename: filename));
          return http.Response.fromStream(await client.send(request));
        }));
      });

  @override
  Future<List<TradeHistory>> trades() async => _normalize(() async {
        final response = await _authenticated(
            (headers) => client.get(_uri('/trades'), headers: headers));
        final decoded = _decodeList(response);
        return decoded
            .map((item) => TradeHistory.fromJson(item as Map<String, dynamic>))
            .toList();
      });

  @override
  Future<void> deleteTrade(String tradeId) async => _normalize(() async {
        _decode(await _authenticated((headers) =>
            client.delete(_uri('/trades/$tradeId'), headers: headers)));
      });

  @override
  Future<AccountProfile> profile() async => _normalize(() async {
        if (accountEmail == null) {
          throw const GatewayError(
              'auth_required', 'Sign in to load your profile.');
        }
        final value = _decode(await _authenticated((headers) => client.get(
            _uri('/accounts/${Uri.encodeComponent(accountEmail!)}'),
            headers: headers)));
        return AccountProfile.fromJson(value);
      });

  @override
  Future<AccountProfile> updateProfile(String displayName) async =>
      _normalize(() async {
        final response = await _authenticated((headers) => client.put(
            _uri('/account/profile'),
            headers: {...headers, 'Content-Type': 'application/json'},
            body: jsonEncode({'display_name': displayName})));
        return AccountProfile.fromJson(_decode(response));
      });

  Future<void> logout() async {
    if (refreshToken == null) return;
    try {
      await _normalize(() async {
        _decode(await client.post(_uri('/auth/logout'),
            headers: {'Content-Type': 'application/json'},
            body: jsonEncode({'refresh_token': refreshToken})));
      });
    } finally {
      _clearAuthentication();
    }
  }

  Future<void> deleteAccount() async {
    await _normalize(() async => _decode(await _authenticated(
        (headers) => client.delete(_uri('/account'), headers: headers))));
    _clearAuthentication();
  }

  @override
  Future<void> setPublicProfile(bool enabled) async => _normalize(() async {
        _decode(await _authenticated((headers) => client.put(
            _uri('/account/public-profile?enabled=$enabled'),
            headers: headers)));
      });

  @override
  Future<List<AccountProfile>> searchAccounts(String query) async =>
      _normalize(() async {
        final response = await _authenticated((headers) => client.get(
            _uri('/accounts/search?q=${Uri.encodeQueryComponent(query)}'),
            headers: headers));
        final decoded = _decodeList(response);
        return decoded
            .map(
                (item) => AccountProfile.fromJson(item as Map<String, dynamic>))
            .toList();
      });

  @override
  Future<ImportPreview> preview(Uint8List bytes, String filename) async {
    return _normalize(() async {
      final response = await _authenticated((headers) async {
        final request = http.MultipartRequest('POST', _uri('/imports/preview'))
          ..headers.addAll(headers)
          ..files.add(
              http.MultipartFile.fromBytes('file', bytes, filename: filename));
        return http.Response.fromStream(await client.send(request));
      });
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
      final imported = _decode(await _authenticated((headers) async {
        final request = http.MultipartRequest('POST', _uri('/imports'))
          ..headers.addAll(headers)
          ..fields['mapping'] = jsonEncode(mapping)
          ..fields['timezone'] = timezone
          ..files.add(
              http.MultipartFile.fromBytes('file', bytes, filename: filename));
        return http.Response.fromStream(await client.send(request));
      }));
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
    final runResponse = await _authenticated((headers) => client.post(
        _uri('/analysis-runs'),
        headers: {...headers, 'Content-Type': 'application/json'},
        body: jsonEncode(requestBody)));
    final run = _decode(runResponse);
    for (var attempt = 0; attempt < 40; attempt += 1) {
      final statusResponse = await _authenticated((headers) =>
          client.get(_uri('/analysis-runs/${run['id']}'), headers: headers));
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
        final resultResponse = await _authenticated((headers) => client.get(
            _uri('/trade-analyses/${status['trade_analysis_id']}'),
            headers: headers));
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

  List<dynamic> _decodeList(http.Response response) {
    if (response.statusCode >= 400) {
      _decode(response);
    }
    final value = jsonDecode(response.body.isEmpty ? '[]' : response.body);
    if (value is! List<dynamic>) {
      throw const GatewayError(
          'invalid_response', 'The service returned an unexpected response.');
    }
    return value;
  }
}
