import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:strategy_audit_app/features/analysis/analysis_screen.dart';

import 'support/fake_gateway.dart';

void main() {
  setUpAll(() async {
    final loader = FontLoader('Roboto')
      ..addFont(rootBundle.load('assets/fonts/Roboto-Regular.ttf'));
    final iconLoader = FontLoader('MaterialIcons')
      ..addFont(rootBundle.load('assets/fonts/MaterialIcons-Regular.otf'));
    await Future.wait([loader.load(), iconLoader.load()]);
  });
  Future<void> pumpAt(WidgetTester tester, Size size) async {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    await tester.pumpWidget(MaterialApp(
        theme: ThemeData(
            colorScheme: ColorScheme.fromSeed(
                seedColor: const Color(0xff315e51),
                surface: const Color(0xfff7f7f4)),
            useMaterial3: true,
            fontFamily: 'Roboto'),
        home: AnalysisScreen(
            onThemeChanged: () {},
            authenticated: true,
            gateway: FakeGateway(),
            fileSelector: () async =>
                SelectedFile('fills.csv', Uint8List.fromList([1, 2, 3])))));
    await tester.pumpAndSettle();
  }

  testWidgets('dark authentication golden', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    await tester.pumpWidget(MaterialApp(
        theme: ThemeData(
            colorScheme: ColorScheme.fromSeed(
                seedColor: const Color(0xff8cbcac),
                brightness: Brightness.dark,
                surface: const Color(0xff151918)),
            useMaterial3: true,
            fontFamily: 'Roboto'),
        home: AnalysisScreen(onThemeChanged: () {}, gateway: FakeGateway())));
    await tester.pumpAndSettle();
    await expectLater(find.byType(AnalysisScreen),
        matchesGoldenFile('goldens/auth_dark_390.png'));
  });

  testWidgets('mobile upload golden', (tester) async {
    await pumpAt(tester, const Size(390, 844));
    await expectLater(find.byType(AnalysisScreen),
        matchesGoldenFile('goldens/upload_390.png'));
  });

  testWidgets('desktop analysis golden', (tester) async {
    await pumpAt(tester, const Size(1440, 1100));
    await tester.tap(find.text('Select CSV'));
    await tester.pumpAndSettle();
    await tester.ensureVisible(find.text('Import and analyze'));
    await tester.tap(find.text('Import and analyze'));
    await tester.pump(const Duration(seconds: 2));
    await expectLater(find.byType(AnalysisScreen),
        matchesGoldenFile('goldens/result_1440.png'));
  });
}
