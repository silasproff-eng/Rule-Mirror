import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:strategy_audit_app/app.dart';
import 'package:strategy_audit_app/core/credential_store.dart';
import 'package:strategy_audit_app/features/analysis/analysis_gateway.dart';
import 'package:strategy_audit_app/features/analysis/analysis_screen.dart';
import 'package:strategy_audit_app/features/strategies/strategy_catalog.dart';

import 'support/fake_gateway.dart';

class _EmptyCredentialStore implements CredentialStore {
  @override
  Future<void> clear() async {}

  @override
  Future<String?> readEmail() async => null;

  @override
  Future<String?> readRefreshToken() async => null;

  @override
  Future<void> writeSession(String refreshToken, String email) async {}
}

class _StoredCredentialStore implements CredentialStore {
  String? refreshToken = 'stored-refresh';
  String? email = 'silas@example.com';

  @override
  Future<void> clear() async {
    refreshToken = null;
    email = null;
  }

  @override
  Future<String?> readEmail() async => email;

  @override
  Future<String?> readRefreshToken() async => refreshToken;

  @override
  Future<void> writeSession(String refreshToken, String email) async {
    this.refreshToken = refreshToken;
    this.email = email;
  }
}

void main() {
  testWidgets('mascot opens an accessible keyword command search',
      (tester) async {
    final gateway = HttpAnalysisGateway(
        credentialStore: _EmptyCredentialStore(),
        client: MockClient((request) async => http.Response('{}', 200)));
    await tester.pumpWidget(StrategyAuditApp(gateway: gateway));
    await tester.pumpAndSettle();

    final mascot = find.bySemanticsLabel('Open Rule Mirror commands');
    expect(mascot, findsOneWidget);
    await tester.tap(mascot);
    await tester.pumpAndSettle();

    expect(find.text('Ask the mascot'), findsOneWidget);
    await tester.enterText(
        find.byType(TextField).last, 'opening range breakout');
    await tester.pump();
    expect(find.text('Opening Range Breakout'), findsOneWidget);
    await tester.enterText(
        find.byType(TextField).last, 'search public accounts');
    await tester.pump();
    expect(find.textContaining('Sign in to search public accounts'),
        findsOneWidget);
  });

  testWidgets('account creation requires explicit legal agreement',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
        home: AnalysisScreen(onThemeChanged: () {}, gateway: FakeGateway())));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Create a private account'));
    await tester.pump();

    expect(
        find.textContaining('I agree to the Terms of Service'), findsOneWidget);
    expect(find.text('Read Terms'), findsOneWidget);
    expect(find.text('Read Privacy'), findsOneWidget);
  });

  testWidgets('restored sessions open the overview workspace', (tester) async {
    final gateway = HttpAnalysisGateway(
        credentialStore: _StoredCredentialStore(),
        client: MockClient((request) async {
          if (request.url.path.endsWith('/auth/refresh')) {
            return http.Response(
                jsonEncode({
                  'access_token': 'access',
                  'refresh_token': 'rotated-refresh'
                }),
                200);
          }
          if (request.url.path.endsWith('/account/profile')) {
            return http.Response(
                jsonEncode({
                  'username': 'member-test',
                  'display_name': 'Silas',
                  'public_profile': false,
                  'metrics': {
                    'portfolio_value': 0,
                    'total_pnl': 0,
                    'win_rate': null,
                    'discipline': null
                  }
                }),
                200);
          }
          return http.Response('[]', 200);
        }));

    await tester.pumpWidget(StrategyAuditApp(gateway: gateway));
    await tester.pump(const Duration(milliseconds: 600));
    await tester.pumpAndSettle();

    expect(find.text('Welcome back, Silas.'), findsOneWidget);
  });

  test('strategy catalog matches canonical unique slugs', () {
    expect(strategyCatalog.length, 52);
    expect(strategyCatalog.map((value) => value.slug).toSet().length,
        strategyCatalog.length);
    expect(strategyBySlug('vwap-reclaim').name, 'VWAP Reclaim');
    expect(strategyBySlug('opening-range-breakout').profile, 'breakout');
    expect(strategyBySlug('macd-cross').summary,
        contains('EMA 9 and EMA 20 alignment'));
  });
}
