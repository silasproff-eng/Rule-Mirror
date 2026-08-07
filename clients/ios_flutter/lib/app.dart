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
      home: _LaunchShell(
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

class _LaunchShell extends StatefulWidget {
  const _LaunchShell({required this.onThemeChanged});
  final VoidCallback onThemeChanged;

  @override
  State<_LaunchShell> createState() => _LaunchShellState();
}

class _LaunchShellState extends State<_LaunchShell>
    with SingleTickerProviderStateMixin {
  late final AnimationController animation = AnimationController(
      vsync: this, duration: const Duration(milliseconds: 1100))
    ..forward();
  int tab = 2;
  bool ready = false;

  @override
  void initState() {
    super.initState();
    Future<void>.delayed(const Duration(milliseconds: 700), () {
      if (mounted) setState(() => ready = true);
    });
  }

  @override
  void dispose() {
    animation.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!ready) {
      return const _SplashScreen();
    }
    return Scaffold(
      body: FadeTransition(
          opacity: CurvedAnimation(parent: animation, curve: Curves.easeOut),
          child: IndexedStack(index: tab, children: [
            const _HomeTab(),
            const _InfoTab(
                title: 'My portfolio',
                detail:
                    'Your holdings and portfolio value will appear here after a holdings import.'),
            AnalysisScreen(onThemeChanged: widget.onThemeChanged),
            const _InfoTab(
                title: 'Trades',
                detail:
                    'Your reconstructed trade history will appear here after you import an execution export.'),
            _InfoTab(
                title: 'Profile & settings',
                detail:
                    'Manage your workspace, privacy, appearance, and public profile.',
                onThemeChanged: widget.onThemeChanged),
          ])),
      bottomNavigationBar: NavigationBar(
          selectedIndex: tab,
          onDestinationSelected: (value) => setState(() => tab = value),
          destinations: const [
            NavigationDestination(
                icon: Icon(Icons.grid_view_outlined),
                selectedIcon: Icon(Icons.grid_view),
                label: 'Overview'),
            NavigationDestination(
                icon: Icon(Icons.account_balance_wallet_outlined),
                selectedIcon: Icon(Icons.account_balance_wallet),
                label: 'Portfolio'),
            NavigationDestination(
                icon: Icon(Icons.analytics_outlined),
                selectedIcon: Icon(Icons.analytics),
                label: 'Analyze'),
            NavigationDestination(
                icon: Icon(Icons.list_alt_outlined),
                selectedIcon: Icon(Icons.list_alt),
                label: 'Trades'),
            NavigationDestination(
                icon: Icon(Icons.person_outline),
                selectedIcon: Icon(Icons.person),
                label: 'Profile'),
          ]),
    );
  }
}

class _SplashScreen extends StatelessWidget {
  const _SplashScreen();

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return ColoredBox(
        color: colors.surface,
        child: Center(
            child:
                Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          Container(
              width: 62,
              height: 62,
              decoration: BoxDecoration(
                  color: colors.primary,
                  borderRadius: BorderRadius.circular(18)),
              child: Icon(Icons.analytics_outlined,
                  color: colors.onPrimary, size: 32)),
          const SizedBox(height: 22),
          Text('RuleMirror',
              style: Theme.of(context)
                  .textTheme
                  .headlineSmall
                  ?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          Text('A clearer record of your decisions',
              style: TextStyle(color: colors.onSurfaceVariant)),
          const SizedBox(height: 28),
          SizedBox(
              width: 22,
              height: 22,
              child: CircularProgressIndicator(
                  strokeWidth: 2, color: colors.primary))
        ])));
  }
}

class _HomeTab extends StatelessWidget {
  const _HomeTab();

  @override
  Widget build(BuildContext context) {
    return SafeArea(
        child: Center(
            child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 720),
                child: Padding(
                    padding: const EdgeInsets.all(28),
                    child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text('RuleMirror',
                              style: Theme.of(context).textTheme.labelLarge),
                          const SizedBox(height: 12),
                          Text('See the decision clearly.',
                              style: Theme.of(context)
                                  .textTheme
                                  .displaySmall
                                  ?.copyWith(fontWeight: FontWeight.w700)),
                          const SizedBox(height: 14),
                          const Text(
                              'Review your process, keep your records private, and build a clearer history over time.'),
                          const SizedBox(height: 28),
                          Card(
                              child: ListTile(
                                  leading:
                                      const Icon(Icons.upload_file_outlined),
                                  title: const Text(
                                      'Start with an execution export'),
                                  subtitle: const Text(
                                      'Analyze is ready when you are.'))),
                        ])))));
  }
}

class _InfoTab extends StatelessWidget {
  const _InfoTab(
      {required this.title, required this.detail, this.onThemeChanged});
  final String title;
  final String detail;
  final VoidCallback? onThemeChanged;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
        child: Center(
            child: Padding(
                padding: const EdgeInsets.all(28),
                child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(title,
                          style: Theme.of(context)
                              .textTheme
                              .headlineMedium
                              ?.copyWith(fontWeight: FontWeight.w700)),
                      const SizedBox(height: 12),
                      Text(detail, textAlign: TextAlign.center),
                      if (onThemeChanged != null) ...[
                        const SizedBox(height: 28),
                        OutlinedButton.icon(
                            onPressed: onThemeChanged,
                            icon: const Icon(Icons.brightness_6_outlined),
                            label: const Text('Toggle appearance'))
                      ]
                    ]))));
  }
}
