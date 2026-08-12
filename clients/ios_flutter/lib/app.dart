import 'dart:async';
import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
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
      navigationBarTheme: NavigationBarThemeData(
          indicatorColor: colors.primary.withValues(alpha: 0.18),
          labelTextStyle: WidgetStatePropertyAll(
              TextStyle(color: colors.primary, fontWeight: FontWeight.w600)),
          iconTheme:
              WidgetStatePropertyAll(IconThemeData(color: colors.primary))),
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
  late final HttpAnalysisGateway gateway;
  final TextEditingController topSearch = TextEditingController();
  bool signedIn = false;

  void _resetToSignIn() {
    if (pages.hasClients) pages.jumpToPage(2);
    setState(() {
      signedIn = false;
      tab = 2;
    });
  }

  @override
  void initState() {
    super.initState();
    gateway = HttpAnalysisGateway(onAuthenticationExpired: _resetToSignIn);
    Future<void>.delayed(const Duration(milliseconds: 700), () {
      if (mounted) setState(() => ready = true);
    });
  }

  @override
  void dispose() {
    animation.dispose();
    pages.dispose();
    topSearch.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!ready) {
      return const _SplashScreen();
    }
    return Scaffold(
      appBar: tab == 2
          ? null
          : AppBar(
              leading: const Padding(
                  padding: EdgeInsets.only(left: 12),
                  child: RuleMirrorMascot(size: 34)),
              leadingWidth: 54,
              centerTitle: true,
              title:
                  _AccountSearchButton(gateway: gateway, signedIn: signedIn)),
      body: FadeTransition(
          opacity: CurvedAnimation(parent: animation, curve: Curves.easeOut),
          child: PageView(
              controller: pages,
              onPageChanged: (value) => setState(() => tab = value),
              children: [
                const _HomeTab(),
                _DataTab(
                    key: ValueKey('portfolio-$signedIn'),
                    authenticated: signedIn,
                    title: 'My portfolio',
                    load: gateway.portfolio,
                    gateway: gateway,
                    importPortfolio: gateway.importPortfolio),
                AnalysisScreen(
                    key: ValueKey('analysis-$signedIn'),
                    onThemeChanged: widget.onThemeChanged,
                    gateway: gateway,
                    authenticated: signedIn,
                    onSearch: () => showSearch<String>(
                        context: context,
                        delegate: _AccountSearchDelegate(
                            gateway: gateway, signedIn: signedIn)),
                    onAuthenticated: () => setState(() => signedIn = true)),
                _DataTab(
                    key: ValueKey('trades-$signedIn'),
                    authenticated: signedIn,
                    title: 'Trades',
                    load: gateway.trades,
                    gateway: gateway,
                    deleteTrade: gateway.deleteTrade),
                _SearchTab(
                    key: ValueKey('profile-$signedIn'),
                    authenticated: signedIn,
                    gateway: gateway,
                    onThemeChanged: widget.onThemeChanged,
                    onSignedOut: _resetToSignIn),
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

class _AccountSearchButton extends StatelessWidget {
  const _AccountSearchButton({required this.gateway, required this.signedIn});
  final HttpAnalysisGateway gateway;
  final bool signedIn;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 330),
        child: Material(
            color: Theme.of(context).colorScheme.surfaceContainerLowest,
            borderRadius: BorderRadius.circular(999),
            child: InkWell(
                borderRadius: BorderRadius.circular(999),
                onTap: () => showSearch<String>(
                    context: context,
                    delegate: _AccountSearchDelegate(
                        gateway: gateway, signedIn: signedIn)),
                child: const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                    child: Row(mainAxisSize: MainAxisSize.min, children: [
                      Icon(Icons.search, size: 19),
                      SizedBox(width: 9),
                      Text('Search accounts')
                    ])))));
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
              width: 214,
              height: 214,
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                  color: Colors.white, borderRadius: BorderRadius.circular(22)),
              child: Image.asset('assets/rulemirror-logo.png',
                  fit: BoxFit.contain)),
          const SizedBox(height: 22),
          Text('A clearer record of your decisions',
              style: TextStyle(color: moss, fontWeight: FontWeight.w500)),
          const SizedBox(height: 28),
          SizedBox(
              width: 22,
              height: 22,
              child: CircularProgressIndicator(strokeWidth: 2, color: moss))
        ])));
  }
}

class _AccountSearchDelegate extends SearchDelegate<String> {
  _AccountSearchDelegate({required this.gateway, required this.signedIn});
  final HttpAnalysisGateway gateway;
  final bool signedIn;

  @override
  List<Widget>? buildActions(BuildContext context) => [
        if (query.isNotEmpty)
          IconButton(onPressed: () => query = '', icon: const Icon(Icons.clear))
      ];

  @override
  Widget? buildLeading(BuildContext context) => IconButton(
      onPressed: () => close(context, ''), icon: const Icon(Icons.arrow_back));

  @override
  Widget buildResults(BuildContext context) {
    if (!signedIn || query.trim().length < 2) {
      return const Center(
          child: Text('Enter at least two characters after signing in.'));
    }
    return FutureBuilder<List<AccountProfile>>(
        future: gateway.searchAccounts(query.trim()),
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError || snapshot.data!.isEmpty) {
            return const Center(child: Text('No public accounts found.'));
          }
          return ListView(
              children: snapshot.data!
                  .map((account) => ListTile(
                      onTap: () => _showPublicProfile(context, account),
                      leading: const CircleAvatar(child: Icon(Icons.person)),
                      title: Text(account.displayName ?? account.username),
                      subtitle: Text(account.username),
                      trailing:
                          Text(account.publicProfile ? 'Public' : 'Private')))
                  .toList());
        });
  }

  @override
  Widget buildSuggestions(BuildContext context) => buildResults(context);
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
  const _DataTab(
      {super.key,
      required this.authenticated,
      required this.title,
      required this.load,
      required this.gateway,
      this.deleteTrade,
      this.importPortfolio});
  final bool authenticated;
  final String title;
  final Future<Object> Function() load;
  final AnalysisGateway gateway;
  final Future<void> Function(String tradeId)? deleteTrade;
  final Future<PortfolioImportResult> Function(
      Uint8List bytes, String filename)? importPortfolio;

  @override
  State<_DataTab> createState() => _DataTabState();
}

class _SearchTab extends StatefulWidget {
  const _SearchTab(
      {super.key,
      required this.authenticated,
      required this.gateway,
      required this.onThemeChanged,
      required this.onSignedOut});
  final bool authenticated;
  final HttpAnalysisGateway gateway;
  final VoidCallback onThemeChanged;
  final VoidCallback onSignedOut;

  @override
  State<_SearchTab> createState() => _SearchTabState();
}

class _SearchTabState extends State<_SearchTab> {
  final query = TextEditingController();
  final name = TextEditingController();
  bool publicProfile = false;
  Future<List<AccountProfile>>? results;
  AccountProfile? profile;
  bool loadingProfile = false;
  bool saving = false;
  Timer? searchDebounce;
  int searchGeneration = 0;

  @override
  void initState() {
    super.initState();
    if (widget.authenticated) _loadProfile();
  }

  Future<void> _loadProfile() async {
    setState(() => loadingProfile = true);
    try {
      final value = await widget.gateway.profile();
      if (!mounted) return;
      name.text = value.displayName ?? '';
      setState(() {
        profile = value;
        publicProfile = value.publicProfile;
      });
    } on GatewayError catch (error) {
      if (mounted) _message(error.message);
    } finally {
      if (mounted) setState(() => loadingProfile = false);
    }
  }

  void _message(String text) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
  }

  Future<void> _saveProfile() async {
    if (saving) return;
    setState(() => saving = true);
    try {
      final value = await widget.gateway.updateProfile(name.text.trim());
      if (!mounted) return;
      setState(() => profile = value);
      _message('Profile saved.');
    } on GatewayError catch (error) {
      if (mounted) _message(error.message);
    } finally {
      if (mounted) setState(() => saving = false);
    }
  }

  Future<void> _setPublicProfile(bool value) async {
    try {
      await widget.gateway.setPublicProfile(value);
      if (mounted) setState(() => publicProfile = value);
    } on GatewayError catch (error) {
      if (mounted) _message(error.message);
    }
  }

  void _search() {
    searchDebounce?.cancel();
    searchGeneration++;
    final value = query.text.trim();
    if (value.length < 2) {
      _message('Enter at least two characters to search.');
      return;
    }
    setState(() => results = widget.gateway.searchAccounts(value));
  }

  void _scheduleSearch(String value) {
    searchDebounce?.cancel();
    ++searchGeneration;
    final normalized = value.trim();
    if (normalized.length < 2) {
      if (mounted) setState(() => results = null);
      return;
    }
    if (mounted) setState(() => results = null);
    searchDebounce = Timer(const Duration(milliseconds: 280), () {
      final future = widget.gateway.searchAccounts(normalized);
      if (mounted) setState(() => results = future);
    });
  }

  @override
  void dispose() {
    searchDebounce?.cancel();
    searchGeneration++;
    query.dispose();
    name.dispose();
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
          'Search public handles or display names and manage your workspace preferences.'),
      const SizedBox(height: 24),
      if (!widget.authenticated)
        const Card(
            child: Padding(
                padding: EdgeInsets.all(20),
                child: Text(
                    'Sign in from Analyze to manage your profile, search accounts, and view synced data.')))
      else ...[
        if (loadingProfile)
          const Padding(
              padding: EdgeInsets.all(16),
              child: Center(child: CircularProgressIndicator()))
        else ...[
          Card(
              child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(children: [
                    Row(children: [
                      const CircleAvatar(child: Icon(Icons.person_outline)),
                      const SizedBox(width: 12),
                      Expanded(
                          child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                            Text(profile?.displayName ?? 'Your workspace',
                                style: Theme.of(context)
                                    .textTheme
                                    .titleMedium
                                    ?.copyWith(fontWeight: FontWeight.w700)),
                            Text(widget.gateway.accountEmail ?? '',
                                style: Theme.of(context).textTheme.bodySmall)
                          ]))
                    ]),
                    const SizedBox(height: 16),
                    Row(children: [
                      _ProfileMetric(
                          label: 'P/L',
                          value: _money(profile?.metrics['total_pnl'])),
                      _ProfileMetric(
                          label: 'Win rate',
                          value: _percent(profile?.metrics['win_rate'])),
                      _ProfileMetric(
                          label: 'Discipline',
                          value: _score(profile?.metrics['discipline']))
                    ])
                  ]))),
          const SizedBox(height: 12),
          TextField(
              controller: name,
              textInputAction: TextInputAction.done,
              onSubmitted: (_) => _saveProfile(),
              decoration: const InputDecoration(
                  labelText: 'Display name',
                  prefixIcon: Icon(Icons.badge_outlined))),
          const SizedBox(height: 12),
          FilledButton.icon(
              onPressed: saving ? null : _saveProfile,
              icon: const Icon(Icons.save_outlined),
              label: Text(saving ? 'Saving…' : 'Save profile')),
          SwitchListTile.adaptive(
              title: const Text('Public profile'),
              subtitle: Text(publicProfile
                  ? 'Summary metrics are visible in account search.'
                  : 'Private by default.'),
              value: publicProfile,
              onChanged: _setPublicProfile),
          ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.dns_outlined),
              title: const Text('Connected server'),
              subtitle: Text(Uri.parse(AppConfig.apiBaseUrl).host))
        ]
      ],
      const SizedBox(height: 18),
      TextField(
          controller: query,
          enabled: widget.authenticated,
          onChanged: _scheduleSearch,
          textInputAction: TextInputAction.search,
          onSubmitted: (_) => _search(),
          decoration: InputDecoration(
              labelText: 'Search public handles or display names',
              prefixIcon: const Icon(Icons.search),
              suffixIcon: Padding(
                  padding: const EdgeInsets.all(7),
                  child: IconButton(
                      style: IconButton.styleFrom(
                          backgroundColor:
                              Theme.of(context).colorScheme.primary,
                          foregroundColor:
                              Theme.of(context).colorScheme.onPrimary,
                          shape: const CircleBorder()),
                      onPressed: widget.authenticated ? _search : null,
                      icon: const Icon(Icons.search, size: 18))))),
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
              return Column(children: [
                if (widget.gateway.lastSearchWasLimited)
                  const Padding(
                      padding: EdgeInsets.only(bottom: 8),
                      child: Text(
                          'Showing the first 20 matches. Refine your search to see more.')),
                ...snapshot.data!.map((account) => ListTile(
                    onTap: () => _showPublicProfile(context, account),
                    leading: const CircleAvatar(child: Icon(Icons.person)),
                    title: Text(account.displayName ?? account.username),
                    subtitle: Text(account.username),
                    trailing:
                        Text(account.publicProfile ? 'Public' : 'Private'))),
              ]);
            }),
      const SizedBox(height: 24),
      OutlinedButton.icon(
          onPressed: widget.onThemeChanged,
          icon: const Icon(Icons.brightness_6_outlined),
          label: const Text('Toggle appearance')),
      OutlinedButton.icon(
          onPressed: !widget.authenticated
              ? null
              : () async {
                  try {
                    await widget.gateway.logout();
                  } on GatewayError catch (error) {
                    if (mounted) _message(error.message);
                  } finally {
                    widget.onSignedOut();
                  }
                },
          icon: const Icon(Icons.logout),
          label: const Text('Sign out')),
      TextButton(
          onPressed: !widget.authenticated
              ? null
              : () async {
                  final confirm = await showDialog<bool>(
                      context: context,
                      builder: (context) => AlertDialog(
                              title: const Text('Delete account?'),
                              content: const Text(
                                  'This removes your imports, trades, analyses, and sessions.'),
                              actions: [
                                TextButton(
                                    onPressed: () =>
                                        Navigator.pop(context, false),
                                    child: const Text('Cancel')),
                                FilledButton(
                                    onPressed: () =>
                                        Navigator.pop(context, true),
                                    child: const Text('Delete'))
                              ]));
                  if (confirm == true) {
                    try {
                      await widget.gateway.deleteAccount();
                      widget.onSignedOut();
                    } on GatewayError catch (error) {
                      if (mounted) _message(error.message);
                    }
                  }
                },
          child: const Text('Delete account')),
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
            child: const Text('Privacy Policy')),
      ]),
    ]));
  }
}

class _ProfileMetric extends StatelessWidget {
  const _ProfileMetric({required this.label, required this.value});
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) => Expanded(
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label, style: Theme.of(context).textTheme.labelSmall),
        const SizedBox(height: 3),
        Text(value,
            style: Theme.of(context)
                .textTheme
                .titleSmall
                ?.copyWith(fontWeight: FontWeight.w700))
      ]));
}

String _money(dynamic value) {
  if (value is! num) return '—';
  return '${value >= 0 ? '+' : '-'}\$${value.abs().toStringAsFixed(2)}';
}

String _percent(dynamic value) {
  if (value is! num) return '—';
  return '${value.toStringAsFixed(1)}%';
}

String _score(dynamic value) {
  if (value is! num) return '—';
  return '${value.round()}/100';
}

Future<void> _showPublicProfile(
    BuildContext context, AccountProfile account) async {
  await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => SafeArea(
          child: Padding(
              padding: const EdgeInsets.fromLTRB(24, 6, 24, 30),
              child: Column(mainAxisSize: MainAxisSize.min, children: [
                const CircleAvatar(radius: 28, child: Icon(Icons.person)),
                const SizedBox(height: 12),
                Text(account.displayName ?? account.username,
                    style: Theme.of(context)
                        .textTheme
                        .titleLarge
                        ?.copyWith(fontWeight: FontWeight.w700)),
                const SizedBox(height: 4),
                Text(account.username,
                    style: Theme.of(context).textTheme.bodyMedium),
                const SizedBox(height: 22),
                Row(children: [
                  _ProfileMetric(
                      label: 'P/L',
                      value: _money(account.metrics['total_pnl'])),
                  _ProfileMetric(
                      label: 'Win rate',
                      value: _percent(account.metrics['win_rate'])),
                  _ProfileMetric(
                      label: 'Discipline',
                      value: _score(account.metrics['discipline']))
                ])
              ]))));
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
  Future<Object>? request;
  bool importingPortfolio = false;
  DateTime? portfolioImportedAt;

  Future<void> _refresh() async {
    final next = widget.load();
    setState(() => request = next);
    await next;
  }

  Future<void> _importPortfolio() async {
    if (widget.importPortfolio == null || importingPortfolio) return;
    final picked = await FilePicker.platform.pickFiles(
        type: FileType.custom, allowedExtensions: ['csv'], withData: true);
    final file = picked?.files.single;
    if (file == null || file.bytes == null) return;
    setState(() => importingPortfolio = true);
    try {
      final result = await widget.importPortfolio!(file.bytes!, file.name);
      if (mounted) setState(() => portfolioImportedAt = result.importedAt);
      if (!mounted) return;
      await _refresh();
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Portfolio imported and synced.')));
      }
    } on GatewayError catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(error.message)));
      }
    } finally {
      if (mounted) setState(() => importingPortfolio = false);
    }
  }

  Future<void> _deleteTrade(TradeHistory trade) async {
    final confirm = await showDialog<bool>(
        context: context,
        builder: (dialogContext) => AlertDialog(
                title: const Text('Delete trade?'),
                content: Text('Remove ${trade.symbol} from your history?'),
                actions: [
                  TextButton(
                      onPressed: () => Navigator.pop(dialogContext, false),
                      child: const Text('Cancel')),
                  FilledButton(
                      onPressed: () => Navigator.pop(dialogContext, true),
                      child: const Text('Delete'))
                ]));
    if (confirm != true || widget.deleteTrade == null) return;
    try {
      await widget.deleteTrade!(trade.tradeId);
      if (!mounted) return;
      await _refresh();
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('Trade deleted.')));
      }
    } on GatewayError catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(error.message)));
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!widget.authenticated) {
      return _InfoTab(
          title: widget.title,
          detail: 'Sign in from Analyze to load your Rule Mirror data.');
    }
    request ??= widget.load();
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
                    detail: 'Your data could not be loaded right now.',
                    onRetry: () => _refresh());
              }
              final value = snapshot.data;
              if (value is PortfolioSummary) {
                return RefreshIndicator(
                    onRefresh: _refresh,
                    child:
                        ListView(padding: const EdgeInsets.all(24), children: [
                      Text(widget.title,
                          style: Theme.of(context)
                              .textTheme
                              .headlineMedium
                              ?.copyWith(fontWeight: FontWeight.w700)),
                      const SizedBox(height: 8),
                      Text(portfolioImportedAt != null
                          ? 'Synced ${MaterialLocalizations.of(context).formatMediumDate(portfolioImportedAt!.toLocal())} at ${MaterialLocalizations.of(context).formatTimeOfDay(TimeOfDay.fromDateTime(portfolioImportedAt!.toLocal()))}'
                          : value.portfolioValue == null
                              ? 'Pull down to refresh your synced holdings.'
                              : 'Portfolio value: \$${value.portfolioValue!.toStringAsFixed(2)}'),
                      const SizedBox(height: 16),
                      FilledButton.icon(
                          onPressed:
                              importingPortfolio ? null : _importPortfolio,
                          icon: const Icon(Icons.upload_file_outlined),
                          label: Text(importingPortfolio
                              ? 'Importing…'
                              : 'Import portfolio CSV')),
                      const SizedBox(height: 16),
                      if (value.holdings.isEmpty)
                        const Card(
                            child: Padding(
                                padding: EdgeInsets.all(24),
                                child: Text(
                                    'No holdings yet. Import a portfolio or purchase-history CSV to sync this account.'))),
                      ...value.holdings.map((holding) => Card(
                          child: ListTile(
                              title: Text(holding.symbol),
                              subtitle: Text(
                                  '${holding.quantity} units · ${holding.source}'),
                              trailing: Text(holding.marketValue == null
                                  ? '—'
                                  : '\$${holding.marketValue!.toStringAsFixed(2)}')))),
                    ]));
              }
              if (value is List<TradeHistory>) {
                return RefreshIndicator(
                    onRefresh: _refresh,
                    child:
                        ListView(padding: const EdgeInsets.all(24), children: [
                      Text(widget.title,
                          style: Theme.of(context)
                              .textTheme
                              .headlineMedium
                              ?.copyWith(fontWeight: FontWeight.w700)),
                      const SizedBox(height: 16),
                      if (widget.title == 'Trades' &&
                          widget.gateway.lastTradesWasLimited)
                        const Text(
                            'Showing the 200 most recent trades. Refine your imports to review more precisely.'),
                      if (value.isEmpty)
                        const Card(
                            child: Padding(
                                padding: EdgeInsets.all(24),
                                child: Text(
                                    'No reconstructed trades yet. Import an execution CSV from Analyze to start your history.'))),
                      ...value.map((trade) => Card(
                          child: ListTile(
                              title: Text(trade.symbol),
                              subtitle: Text(
                                  '${trade.direction} · ${trade.closedAt == null ? 'Open' : 'Closed'}'),
                              trailing: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Text(trade.realizedPnl == null
                                        ? '—'
                                        : '\$${trade.realizedPnl!.toStringAsFixed(2)}'),
                                    IconButton(
                                        tooltip: 'Delete trade',
                                        onPressed: widget.deleteTrade == null
                                            ? null
                                            : () => _deleteTrade(trade),
                                        icon: const Icon(Icons.delete_outline))
                                  ])))),
                    ]));
              }
              final detail = value is PortfolioSummary
                  ? '${value.holdings.length} holdings · ${value.portfolioValue == null ? 'No value yet' : '\$${value.portfolioValue!.toStringAsFixed(2)}'}'
                  : value is List<TradeHistory>
                      ? '${value.length} reconstructed trades'
                      : 'Data synced';
              return _InfoTab(
                  title: widget.title, detail: detail, onRetry: _refresh);
            }));
  }
}

class _InfoTab extends StatelessWidget {
  const _InfoTab({required this.title, required this.detail, this.onRetry});
  final String title;
  final String detail;
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
                    ]))));
  }
}
