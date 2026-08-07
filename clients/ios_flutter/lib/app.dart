import 'package:flutter/material.dart';

import 'core/app_config.dart';
import 'features/analysis/analysis_screen.dart';

class StrategyAuditApp extends StatefulWidget {
  const StrategyAuditApp({super.key});

  @override
  State<StrategyAuditApp> createState() => _StrategyAuditAppState();
}

class _StrategyAuditAppState extends State<StrategyAuditApp> {
  ThemeMode mode = ThemeMode.system;

  @override
  Widget build(BuildContext context) {
    const seed = Color(0xff315e51);
    final light = ColorScheme.fromSeed(
        seedColor: seed,
        brightness: Brightness.light,
        surface: const Color(0xfff7f7f4));
    final dark = ColorScheme.fromSeed(
        seedColor: const Color(0xff8cbcac),
        brightness: Brightness.dark,
        surface: const Color(0xff151918));
    return MaterialApp(
      title: AppConfig.displayName,
      debugShowCheckedModeBanner: false,
      themeMode: mode,
      theme: _theme(light),
      darkTheme: _theme(dark),
      home: AnalysisScreen(
          onThemeChanged: () => setState(() => mode =
              mode == ThemeMode.dark ? ThemeMode.light : ThemeMode.dark)),
    );
  }

  ThemeData _theme(ColorScheme colors) {
    return ThemeData(
      colorScheme: colors,
      useMaterial3: true,
      fontFamily: 'Roboto',
      scaffoldBackgroundColor: colors.surface,
      visualDensity: VisualDensity.standard,
      focusColor: colors.primary.withValues(alpha: 0.14),
      dividerColor: colors.outlineVariant,
      cardTheme: CardThemeData(
          margin: EdgeInsets.zero,
          elevation: 0,
          color: colors.surfaceContainerLowest,
          shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(10),
              side: BorderSide(color: colors.outlineVariant))),
      inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: colors.surfaceContainerLowest,
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
          contentPadding:
              const EdgeInsets.symmetric(horizontal: 14, vertical: 13)),
    );
  }
}
