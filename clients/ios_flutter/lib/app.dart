import 'package:flutter/material.dart';

import 'core/app_config.dart';
import 'features/analysis/analysis_gateway.dart';
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
  late final PageController pages = PageController(initialPage: tab);
  final HttpAnalysisGateway gateway = HttpAnalysisGateway();

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
    pages.dispose();
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
          child: PageView(
              controller: pages,
              onPageChanged: (value) => setState(() => tab = value),
              children: [
                const _HomeTab(),
                _DataTab(title: 'My portfolio', load: gateway.portfolio),
                AnalysisScreen(
                    onThemeChanged: widget.onThemeChanged, gateway: gateway),
                _DataTab(title: 'Trades', load: gateway.trades),
                _SearchTab(
                    gateway: gateway, onThemeChanged: widget.onThemeChanged),
              ])),
      bottomNavigationBar: NavigationBar(
          selectedIndex: tab,
          onDestinationSelected: (value) => pages.animateToPage(value,
              duration: const Duration(milliseconds: 260),
              curve: Curves.easeOutCubic),
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
    const forest = Color(0xff102d24);
    const moss = Color(0xff8eb9a0);
    return ColoredBox(
        color: forest,
        child: Center(
            child:
                Column(mainAxisAlignment: MainAxisAlignment.center, children: [
          Container(
              width: 62,
              height: 62,
              decoration: BoxDecoration(
                  color: moss, borderRadius: BorderRadius.circular(18)),
              child: Icon(Icons.analytics_outlined, color: forest, size: 32)),
          const SizedBox(height: 22),
          Text('Rule Mirror',
              style: Theme.of(context)
                  .textTheme
                  .headlineSmall
                  ?.copyWith(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          Text('A clearer record of your decisions',
              style: TextStyle(color: moss)),
          const SizedBox(height: 28),
          SizedBox(
              width: 22,
              height: 22,
              child: CircularProgressIndicator(strokeWidth: 2, color: moss))
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
                          Text('Rule Mirror',
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

class _DataTab extends StatefulWidget {
  const _DataTab({required this.title, required this.load});
  final String title;
  final Future<Object> Function() load;

  @override
  State<_DataTab> createState() => _DataTabState();
}

class _SearchTab extends StatefulWidget {
  const _SearchTab({required this.gateway, required this.onThemeChanged});
  final HttpAnalysisGateway gateway;
  final VoidCallback onThemeChanged;

  @override
  State<_SearchTab> createState() => _SearchTabState();
}

class _SearchTabState extends State<_SearchTab> {
  final query = TextEditingController();
  Future<List<AccountProfile>>? results;

  @override
  void dispose() {
    query.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
        child: ListView(padding: const EdgeInsets.all(24), children: [
      Text('Profile & settings',
          style: Theme.of(context)
              .textTheme
              .headlineMedium
              ?.copyWith(fontWeight: FontWeight.w700)),
      const SizedBox(height: 8),
      const Text(
          'Search public accounts by email and manage your workspace preferences.'),
      const SizedBox(height: 24),
      TextField(
          controller: query,
          textInputAction: TextInputAction.search,
          onSubmitted: (value) => setState(
              () => results = widget.gateway.searchAccounts(value.trim())),
          decoration: InputDecoration(
              labelText: 'Search accounts by email',
              prefixIcon: const Icon(Icons.search),
              suffixIcon: IconButton(
                  onPressed: () => setState(() => results =
                      widget.gateway.searchAccounts(query.text.trim())),
                  icon: const Icon(Icons.arrow_forward)))),
      const SizedBox(height: 16),
      if (results != null)
        FutureBuilder<List<AccountProfile>>(
            future: results,
            builder: (context, snapshot) {
              if (snapshot.connectionState != ConnectionState.done) {
                return const Center(child: CircularProgressIndicator());
              }
              if (snapshot.hasError) {
                return const Text('Search is unavailable right now.');
              }
              return Column(
                  children: snapshot.data!
                      .map((account) => ListTile(
                          leading:
                              const CircleAvatar(child: Icon(Icons.person)),
                          title: Text(account.displayName ?? account.username),
                          subtitle: Text(account.username),
                          trailing: Text(
                              account.publicProfile ? 'Public' : 'Private')))
                      .toList());
            }),
      const SizedBox(height: 24),
      OutlinedButton.icon(
          onPressed: widget.onThemeChanged,
          icon: const Icon(Icons.brightness_6_outlined),
          label: const Text('Toggle appearance')),
      const SizedBox(height: 12),
      Row(children: [
        TextButton(
            onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                builder: (_) =>
                    const _LegalPage(title: 'Terms of Service', sections: [
                      'Agreement',
                      'Rule Mirror is educational analytics, not financial advice.',
                      'Use the service lawfully and keep your account secure.',
                      'Contact silas@rulemirror.com.'
                    ]))),
            child: const Text('Terms of Service')),
        TextButton(
            onPressed: () => Navigator.of(context).push(MaterialPageRoute(
                builder: (_) =>
                    const _LegalPage(title: 'Privacy Policy', sections: [
                      'What we collect',
                      'We use account and import data to provide the service.',
                      'Public profiles share summary metrics only.',
                      'Contact silas@rulemirror.com.'
                    ]))),
            child: const Text('Privacy Policy'))
      ]),
    ]));
  }
}

class _LegalPage extends StatelessWidget {
  const _LegalPage({required this.title, required this.sections});
  final String title;
  final List<String> sections;

  @override
  Widget build(BuildContext context) => Scaffold(
      appBar: AppBar(title: Text(title)),
      body: ListView(padding: const EdgeInsets.all(24), children: [
        Text('Last updated August 7, 2026',
            style: Theme.of(context).textTheme.labelMedium),
        const SizedBox(height: 20),
        ...sections.map((section) => Padding(
            padding: const EdgeInsets.only(bottom: 18),
            child: Text(section, style: Theme.of(context).textTheme.bodyLarge)))
      ]));
}

class _DataTabState extends State<_DataTab> {
  late Future<Object> request = widget.load();

  @override
  Widget build(BuildContext context) {
    return SafeArea(
        child: FutureBuilder<Object>(
            future: request,
            builder: (context, snapshot) {
              if (snapshot.connectionState != ConnectionState.done) {
                return const Center(child: CircularProgressIndicator());
              }
              if (snapshot.hasError) {
                return _InfoTab(
                    title: widget.title,
                    detail:
                        'Sign in to load your Rule Mirror data, then pull to refresh.',
                    onRetry: () => setState(() => request = widget.load()));
              }
              final value = snapshot.data;
              final detail = value is PortfolioSummary
                  ? '${value.holdings.length} holdings · ${value.portfolioValue == null ? 'No value yet' : '\$${value.portfolioValue!.toStringAsFixed(2)}'}'
                  : value is List<TradeHistory>
                      ? '${value.length} reconstructed trades'
                      : 'Data synced';
              return _InfoTab(
                  title: widget.title,
                  detail: detail,
                  onRetry: () => setState(() => request = widget.load()));
            }));
  }
}

class _InfoTab extends StatelessWidget {
  const _InfoTab(
      {required this.title,
      required this.detail,
      this.onThemeChanged,
      this.onRetry});
  final String title;
  final String detail;
  final VoidCallback? onThemeChanged;
  final VoidCallback? onRetry;

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
                      if (onRetry != null) ...[
                        const SizedBox(height: 20),
                        OutlinedButton.icon(
                            onPressed: onRetry,
                            icon: const Icon(Icons.refresh),
                            label: const Text('Refresh'))
                      ],
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
