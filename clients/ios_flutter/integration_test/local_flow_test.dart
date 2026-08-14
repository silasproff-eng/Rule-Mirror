import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:strategy_audit_app/features/analysis/analysis_screen.dart';

import '../test/support/fake_gateway.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('local sample upload reaches analysis evidence', (tester) async {
    await tester.pumpWidget(MaterialApp(
        home: AnalysisScreen(
            onThemeChanged: () {},
            authenticated: true,
            gateway: FakeGateway(),
            fileSelector: () async =>
                SelectedFile('fills.csv', Uint8List.fromList([1, 2, 3])))));
    await tester.tap(find.text('Select CSV'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Import and analyze'));
    await tester.tap(find.text('Import and analyze'));
    await tester.pump(const Duration(seconds: 2));
    expect(find.text('Rule evidence'), findsOneWidget);
    expect(find.text('Reclaim relative volume'), findsOneWidget);
  });
}
