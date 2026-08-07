import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:strategy_audit_app/features/analysis/analysis_screen.dart';
import 'package:strategy_audit_app/features/analysis/analysis_gateway.dart';

import 'support/fake_gateway.dart';

void main() {
  Future<void> pumpAt(WidgetTester tester, Size size) async {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    await tester.pumpWidget(MaterialApp(
        home: AnalysisScreen(
            onThemeChanged: () {},
            authenticated: true,
            gateway: FakeGateway(),
            fileSelector: () async =>
                SelectedFile('fills.csv', Uint8List.fromList([1, 2, 3])))));
    await tester.pumpAndSettle();
  }

  testWidgets('upload to deterministic result flow works at mobile width',
      (tester) async {
    await pumpAt(tester, const Size(390, 844));
    expect(find.text('Analyze actual execution quality'), findsOneWidget);
    await tester.tap(find.text('Select CSV'));
    await tester.pumpAndSettle();
    expect(find.text('Confirm the execution fields'), findsOneWidget);
    await tester.ensureVisible(find.text('Import and analyze'));
    await tester.tap(find.text('Import and analyze'));
    await tester.pump(const Duration(seconds: 2));
    expect(find.text('AAPL · VWAP Reclaim'), findsOneWidget);
    expect(find.text('82'), findsOneWidget);
  });

  testWidgets('provider failure is reachable with retry', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    await tester.pumpWidget(MaterialApp(
        home: AnalysisScreen(
            onThemeChanged: () {},
            authenticated: true,
            gateway: FakeGateway(
                analysisFailure: const GatewayError(
                    'provider_failure', 'Provider unavailable.',
                    canRetryAnalysis: true),
                failAnalysisOnce: true),
            fileSelector: () async =>
                SelectedFile('fills.csv', Uint8List.fromList([1])))));
    await tester.tap(find.text('Select CSV'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Import and analyze'));
    await tester.tap(find.text('Import and analyze'));
    await tester.pump(const Duration(seconds: 1));
    await tester.pumpAndSettle();
    expect(find.text('Analysis could not finish'), findsOneWidget);
    expect(find.text('Provider unavailable.'), findsOneWidget);
    expect(find.text('Retry analysis'), findsOneWidget);
    await tester.tap(find.text('Retry analysis'));
    await tester.pumpAndSettle();
    expect(find.text('AAPL · VWAP Reclaim'), findsOneWidget);
  });

  testWidgets('preview failure returns to file selection with accurate copy',
      (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    await tester.pumpWidget(MaterialApp(
        home: AnalysisScreen(
            onThemeChanged: () {},
            authenticated: true,
            gateway: FakeGateway(
                previewFailure:
                    const GatewayError('network_error', 'Service offline.')),
            fileSelector: () async =>
                SelectedFile('fills.csv', Uint8List.fromList([1])))));
    await tester.tap(find.text('Select CSV'));
    await tester.pumpAndSettle();
    expect(find.text('The file needs attention'), findsOneWidget);
    expect(find.text('Choose another file'), findsOneWidget);
  });

  testWidgets('multiple affected trades require explicit selection',
      (tester) async {
    final gateway = FakeGateway(affectedTrades: [
      sampleAffectedTrade,
      AffectedTrade(
          tradeId: 'trade-2',
          revisionId: 'revision-2',
          symbol: 'MSFT',
          direction: 'short',
          openedAt: DateTime.parse('2026-08-06T14:00:00Z'),
          closedAt: DateTime.parse('2026-08-06T14:20:00Z'),
          analysisEligible: true,
          changeType: 'created')
    ]);
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    await tester.pumpWidget(MaterialApp(
        home: AnalysisScreen(
            onThemeChanged: () {},
            authenticated: true,
            gateway: gateway,
            fileSelector: () async =>
                SelectedFile('fills.csv', Uint8List.fromList([1])))));
    await tester.tap(find.text('Select CSV'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Import and analyze'));
    await tester.tap(find.text('Import and analyze'));
    await tester.pumpAndSettle();
    expect(find.text('Choose a reconstructed trade'), findsOneWidget);
    expect(find.text('AAPL · long'), findsOneWidget);
    expect(find.text('MSFT · short'), findsOneWidget);
    await tester.tap(find.text('Analyze').last);
    await tester.pumpAndSettle();
    expect(gateway.selectedTrade?.tradeId, 'trade-2');
  });

  testWidgets('desktop layout exposes navigation and private status',
      (tester) async {
    await pumpAt(tester, const Size(1440, 1000));
    expect(find.text('Analyze'), findsOneWidget);
    expect(find.text('Private workspace'), findsOneWidget);
    expect(find.bySemanticsLabel('Change color theme'), findsOneWidget);
  });
}
