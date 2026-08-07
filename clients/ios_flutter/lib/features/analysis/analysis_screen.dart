import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../../core/app_config.dart';
import 'analysis_models.dart';
import 'analysis_gateway.dart';

enum FlowStage {
  auth,
  upload,
  mapping,
  importing,
  selectingTrade,
  analyzing,
  result,
  error,
  insufficient
}

enum ErrorRecovery { auth, upload, mapping, retryAnalysis }

class AnalysisScreen extends StatefulWidget {
  const AnalysisScreen(
      {required this.onThemeChanged,
      this.gateway,
      this.fileSelector,
      this.authenticated = false,
      super.key});
  final VoidCallback onThemeChanged;
  final AnalysisGateway? gateway;
  final Future<SelectedFile?> Function()? fileSelector;
  final bool authenticated;

  @override
  State<AnalysisScreen> createState() => _AnalysisScreenState();
}

class _AnalysisScreenState extends State<AnalysisScreen> {
  late FlowStage stage;
  late final AnalysisGateway gateway;
  String errorTitle = '';
  String errorDetail = '';
  ErrorRecovery errorRecovery = ErrorRecovery.upload;
  Uint8List? bytes;
  String filename = '';
  ImportPreview? preview;
  List<AffectedTrade> affectedTrades = const [];
  AnalysisResult? result;

  @override
  void initState() {
    super.initState();
    gateway = widget.gateway ?? HttpAnalysisGateway();
    stage = widget.authenticated ? FlowStage.upload : FlowStage.auth;
  }

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= 900;
    return Scaffold(
      body: SafeArea(
        child: Row(
          children: [
            if (wide) _Sidebar(onThemeChanged: widget.onThemeChanged),
            Expanded(
              child: Column(
                children: [
                  _TopBar(
                      onThemeChanged: widget.onThemeChanged, showBrand: !wide),
                  Expanded(
                    child: SingleChildScrollView(
                      padding: EdgeInsets.symmetric(
                          horizontal: wide ? 48 : 20, vertical: wide ? 38 : 24),
                      child: Center(
                          child: ConstrainedBox(
                              constraints: const BoxConstraints(maxWidth: 1120),
                              child: _content(wide))),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _content(bool wide) {
    return switch (stage) {
      FlowStage.auth => _AuthPanel(onSubmit: _authenticate),
      FlowStage.upload => _UploadPanel(onContinue: _selectFile),
      FlowStage.mapping => _MappingPanel(
          preview: preview!,
          filename: filename,
          onBack: () => setState(() => stage = FlowStage.upload),
          onImport: _importAndAnalyze),
      FlowStage.importing => const _ProgressPanel(
          title: 'Normalizing executions',
          detail:
              'Reconstructing scale-ins, partial exits, and reversals in UTC.',
          progress: 0.46),
      FlowStage.selectingTrade => _TradeSelectionPanel(
          trades: affectedTrades,
          onSelect: _analyzeSelected,
          onBack: () => setState(() => stage = FlowStage.upload)),
      FlowStage.analyzing => const _ProgressPanel(
          title: 'Reconstructing market context',
          detail:
              'Evaluating completed one-minute bars before each execution. Raw market data stays on the backend.',
          progress: 0.78),
      FlowStage.result => _ResultView(
          result: result!,
          wide: wide,
          onReset: () => setState(() => stage = FlowStage.upload)),
      FlowStage.error => _ErrorPanel(
          title: errorTitle,
          detail: errorDetail,
          action: switch (errorRecovery) {
            ErrorRecovery.auth => 'Try signing in again',
            ErrorRecovery.upload => 'Choose another file',
            ErrorRecovery.mapping => 'Review mapping',
            ErrorRecovery.retryAnalysis => 'Retry analysis',
          },
          onAction: _recover),
      FlowStage.insufficient => _ResultView(
          result: result!,
          wide: wide,
          onReset: () => setState(() => stage = FlowStage.upload)),
    };
  }

  Future<void> _authenticate(
      String email, String password, bool register) async {
    try {
      if (register) {
        await gateway.register(email, password);
      } else {
        await gateway.login(email, password);
      }
      if (mounted) {
        setState(() => stage = FlowStage.upload);
      }
    } on GatewayError catch (error) {
      if (mounted) {
        setState(() {
          errorTitle = 'Sign in failed';
          errorDetail = error.message;
          errorRecovery = ErrorRecovery.auth;
          stage = FlowStage.error;
        });
      }
    }
  }

  Future<SelectedFile?> _defaultFileSelector() async {
    final picked = await FilePicker.platform.pickFiles(
        type: FileType.custom, allowedExtensions: ['csv'], withData: true);
    final file = picked?.files.single;
    if (file == null || file.bytes == null) {
      return null;
    }
    return SelectedFile(file.name, file.bytes!);
  }

  Future<void> _selectFile() async {
    try {
      final selected = await (widget.fileSelector ?? _defaultFileSelector)();
      if (selected == null) {
        return;
      }
      bytes = selected.bytes;
      filename = selected.name;
      final value = await gateway.preview(selected.bytes, selected.name);
      if (mounted) {
        setState(() {
          preview = value;
          stage = FlowStage.mapping;
        });
      }
    } on GatewayError catch (error) {
      if (mounted) {
        setState(() {
          errorTitle = 'The file needs attention';
          errorDetail = error.message;
          errorRecovery = ErrorRecovery.upload;
          stage = FlowStage.error;
        });
      }
    }
  }

  Future<void> _importAndAnalyze(
      Map<String, String> mapping, String timezone) async {
    setState(() => stage = FlowStage.importing);
    try {
      final trades =
          await gateway.importExecutions(bytes!, filename, mapping, timezone);
      if (mounted) {
        affectedTrades = trades;
        if (trades.length == 1 && trades.single.analysisEligible) {
          await _analyzeSelected(trades.single);
        } else if (trades.length == 1) {
          _showImportError(const GatewayError('trade_open',
              'The import changed an open trade. Add its closing execution before analysis.'));
        } else {
          setState(() => stage = FlowStage.selectingTrade);
        }
      }
    } on GatewayError catch (error) {
      _showImportError(error);
    }
  }

  void _showImportError(GatewayError error) {
    if (!mounted) return;
    setState(() {
      final duplicateOnly = error.code == 'duplicate_only';
      final tradeOpen = error.code == 'trade_open';
      errorTitle = duplicateOnly
          ? 'Nothing new to analyze'
          : tradeOpen
              ? 'This trade is still open'
              : 'Import could not finish';
      errorDetail = error.message;
      errorRecovery = duplicateOnly || tradeOpen
          ? ErrorRecovery.upload
          : ErrorRecovery.mapping;
      stage = FlowStage.error;
    });
  }

  Future<void> _analyzeSelected(AffectedTrade trade) async {
    setState(() => stage = FlowStage.analyzing);
    try {
      final value = await gateway.analyzeTrade(trade);
      if (mounted) {
        setState(() {
          result = value;
          stage =
              value.score == null ? FlowStage.insufficient : FlowStage.result;
        });
      }
    } on GatewayError catch (error) {
      _showAnalysisError(error);
    }
  }

  void _showAnalysisError(GatewayError error) {
    if (!mounted) return;
    setState(() {
      errorTitle = 'Analysis could not finish';
      errorDetail = error.message;
      errorRecovery = error.canRetryAnalysis
          ? ErrorRecovery.retryAnalysis
          : ErrorRecovery.upload;
      stage = FlowStage.error;
    });
  }

  void _recover() {
    if (errorRecovery == ErrorRecovery.retryAnalysis) {
      _retryAnalysis();
      return;
    }
    setState(() => stage = switch (errorRecovery) {
          ErrorRecovery.auth => FlowStage.auth,
          ErrorRecovery.upload => FlowStage.upload,
          ErrorRecovery.mapping => FlowStage.mapping,
          ErrorRecovery.retryAnalysis => FlowStage.analyzing,
        });
  }

  Future<void> _retryAnalysis() async {
    setState(() => stage = FlowStage.analyzing);
    try {
      final value = await gateway.retryAnalysis();
      if (mounted) {
        setState(() {
          result = value;
          stage =
              value.score == null ? FlowStage.insufficient : FlowStage.result;
        });
      }
    } on GatewayError catch (error) {
      _showAnalysisError(error);
    }
  }
}

class SelectedFile {
  const SelectedFile(this.name, this.bytes);
  final String name;
  final Uint8List bytes;
}

class _TradeSelectionPanel extends StatelessWidget {
  const _TradeSelectionPanel(
      {required this.trades, required this.onSelect, required this.onBack});
  final List<AffectedTrade> trades;
  final ValueChanged<AffectedTrade> onSelect;
  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const _PageHeading(
          kicker: 'Import complete',
          title: 'Choose a reconstructed trade',
          detail:
              'The file affected more than one trade. Select the closed trade you want to review.'),
      const SizedBox(height: 28),
      Card(
          child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                  children: trades
                      .map((trade) => ListTile(
                          contentPadding: const EdgeInsets.symmetric(
                              horizontal: 8, vertical: 6),
                          title: Text('${trade.symbol} · ${trade.direction}',
                              style:
                                  const TextStyle(fontWeight: FontWeight.w700)),
                          subtitle: Text(trade.analysisEligible
                              ? 'Opened ${trade.openedAt.toUtc().toIso8601String()} · Closed ${trade.closedAt!.toUtc().toIso8601String()}'
                              : 'Open trade · add a closing execution before analysis'),
                          trailing: FilledButton(
                              onPressed: trade.analysisEligible
                                  ? () => onSelect(trade)
                                  : null,
                              child: Text(trade.analysisEligible
                                  ? 'Analyze'
                                  : 'Waiting for close'))))
                      .toList()))),
      const SizedBox(height: 16),
      OutlinedButton(
          onPressed: onBack, child: const Text('Import another file'))
    ]);
  }
}

class _AuthPanel extends StatefulWidget {
  const _AuthPanel({required this.onSubmit});
  final Future<void> Function(String email, String password, bool register)
      onSubmit;

  @override
  State<_AuthPanel> createState() => _AuthPanelState();
}

class _AuthPanelState extends State<_AuthPanel> {
  final email = TextEditingController();
  final password = TextEditingController();
  String? error;
  bool busy = false;

  Future<void> submit(bool register) async {
    if (!email.text.contains('@') || password.text.length < 12) {
      setState(() => error =
          'Enter a valid email and a password of at least 12 characters.');
      return;
    }
    setState(() {
      busy = true;
      error = null;
    });
    await widget.onSubmit(email.text.trim(), password.text, register);
    if (mounted) setState(() => busy = false);
  }

  @override
  Widget build(BuildContext context) {
    return Center(
        child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520),
            child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const _PageHeading(
                      kicker: 'Private analysis',
                      title: 'Sign in to your workspace',
                      detail:
                          'Execution history is account-scoped and never public by default.'),
                  const SizedBox(height: 28),
                  Card(
                      child: Padding(
                          padding: const EdgeInsets.all(24),
                          child: Column(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: [
                                TextField(
                                    controller: email,
                                    keyboardType: TextInputType.emailAddress,
                                    autofillHints: const [AutofillHints.email],
                                    decoration: const InputDecoration(
                                        labelText: 'Email')),
                                const SizedBox(height: 14),
                                TextField(
                                    controller: password,
                                    obscureText: true,
                                    autofillHints: const [
                                      AutofillHints.password
                                    ],
                                    onSubmitted: (_) => submit(false),
                                    decoration: const InputDecoration(
                                        labelText: 'Password')),
                                if (error != null)
                                  Padding(
                                      padding: const EdgeInsets.only(top: 12),
                                      child: Text(error!,
                                          style: TextStyle(
                                              color: Theme.of(context)
                                                  .colorScheme
                                                  .error))),
                                const SizedBox(height: 20),
                                FilledButton(
                                    onPressed:
                                        busy ? null : () => submit(false),
                                    child:
                                        Text(busy ? 'Signing in…' : 'Sign in')),
                                const SizedBox(height: 10),
                                OutlinedButton(
                                    onPressed: busy ? null : () => submit(true),
                                    child: const Text('Create private account'))
                              ])))
                ])));
  }
}

class _Sidebar extends StatelessWidget {
  const _Sidebar({required this.onThemeChanged});
  final VoidCallback onThemeChanged;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Container(
      width: 238,
      decoration: BoxDecoration(
          color: colors.surfaceContainerLow,
          border: Border(right: BorderSide(color: colors.outlineVariant))),
      padding: const EdgeInsets.fromLTRB(18, 22, 18, 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const _Brand(),
          const SizedBox(height: 34),
          _NavItem(
              icon: Icons.radar_rounded,
              label: 'Analyze',
              selected: true,
              onTap: () {}),
          const Spacer(),
          Semantics(
              label: 'Change color theme',
              button: true,
              child: IconButton(
                  onPressed: onThemeChanged,
                  alignment: Alignment.centerLeft,
                  icon: const Icon(Icons.contrast_rounded),
                  tooltip: 'Change theme')),
          const Divider(height: 28),
          const Row(children: [
            CircleAvatar(radius: 16, child: Text('S')),
            SizedBox(width: 10),
            Expanded(
                child: Text('Local analyst',
                    style: TextStyle(fontWeight: FontWeight.w600)))
          ]),
        ],
      ),
    );
  }
}

class _TopBar extends StatelessWidget {
  const _TopBar({required this.onThemeChanged, required this.showBrand});
  final VoidCallback onThemeChanged;
  final bool showBrand;

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 64,
      padding: const EdgeInsets.symmetric(horizontal: 20),
      decoration: BoxDecoration(
          border: Border(
              bottom: BorderSide(color: Theme.of(context).dividerColor))),
      child: Row(children: [
        if (showBrand) const _Brand(),
        const Spacer(),
        if (showBrand)
          IconButton(
              onPressed: onThemeChanged,
              icon: const Icon(Icons.contrast_rounded),
              tooltip: 'Change theme'),
        const SizedBox(width: 8),
        if (!showBrand)
          const Chip(
              avatar: Icon(Icons.lock_outline, size: 16),
              label: Text('Private workspace'))
      ]),
    );
  }
}

class _Brand extends StatelessWidget {
  const _Brand();

  @override
  Widget build(BuildContext context) {
    return Semantics(
        label: '${AppConfig.displayName} home',
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          const _RuleMirrorMark(),
          const SizedBox(width: 10),
          Text(AppConfig.displayName,
              style: const TextStyle(
                  fontWeight: FontWeight.w700,
                  fontSize: 16,
                  letterSpacing: -.2))
        ]));
  }
}

class _RuleMirrorMark extends StatelessWidget {
  const _RuleMirrorMark();

  @override
  Widget build(BuildContext context) => const SizedBox(
      width: 29,
      height: 29,
      child: CustomPaint(painter: _RuleMirrorMarkPainter()));
}

class _RuleMirrorMarkPainter extends CustomPainter {
  const _RuleMirrorMarkPainter();

  @override
  void paint(Canvas canvas, Size size) {
    final scale = size.width / 29;
    canvas.drawRRect(
        RRect.fromRectAndRadius(Offset.zero & size, Radius.circular(7 * scale)),
        Paint()..color = const Color(0xff315e51));
    final light = Paint()..color = const Color(0xffd7f4ea);
    final mid = Paint()..color = const Color(0xff8cbcac);
    canvas.drawRect(
        Rect.fromLTWH(8 * scale, 7 * scale, 5 * scale, 15 * scale), light);
    canvas.drawRect(
        Rect.fromLTWH(16 * scale, 7 * scale, 5 * scale, 15 * scale), light);
    canvas.drawRect(
        Rect.fromLTWH(11 * scale, 11 * scale, 7 * scale, 7 * scale), mid);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class _NavItem extends StatelessWidget {
  const _NavItem(
      {required this.icon,
      required this.label,
      required this.onTap,
      this.selected = false});
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    return Padding(
        padding: const EdgeInsets.only(bottom: 5),
        child: Material(
            color: Colors.transparent,
            child: ListTile(
                dense: true,
                minTileHeight: 44,
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(7)),
                selected: selected,
                selectedTileColor:
                    Theme.of(context).colorScheme.primaryContainer,
                leading: Icon(icon, size: 20),
                title: Text(label,
                    style: const TextStyle(fontWeight: FontWeight.w600)),
                onTap: onTap)));
  }
}

class _UploadPanel extends StatelessWidget {
  const _UploadPanel({required this.onContinue});
  final VoidCallback onContinue;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const _PageHeading(
          kicker: 'New analysis',
          title: 'Analyze actual execution quality',
          detail:
              'Import a CSV of fills. We reconstruct each trade and evaluate the market conditions that existed before your entry.'),
      const SizedBox(height: 32),
      Card(
          child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Semantics(
                        button: true,
                        label: 'Choose execution CSV',
                        child: InkWell(
                            onTap: onContinue,
                            borderRadius: BorderRadius.circular(8),
                            child: Container(
                                constraints:
                                    const BoxConstraints(minHeight: 220),
                                decoration: BoxDecoration(
                                    border: Border.all(
                                        color: Theme.of(context)
                                            .colorScheme
                                            .outline,
                                        width: 1.2),
                                    borderRadius: BorderRadius.circular(8)),
                                child: Column(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
                                      Icon(Icons.upload_file_outlined,
                                          size: 38,
                                          color: Theme.of(context)
                                              .colorScheme
                                              .primary),
                                      const SizedBox(height: 16),
                                      const Text('Choose an execution CSV',
                                          style: TextStyle(
                                              fontSize: 18,
                                              fontWeight: FontWeight.w700)),
                                      const SizedBox(height: 7),
                                      Text(
                                          'Canonical fields or map your own columns',
                                          style: TextStyle(
                                              color: Theme.of(context)
                                                  .colorScheme
                                                  .onSurfaceVariant)),
                                      const SizedBox(height: 20),
                                      FilledButton(
                                          onPressed: onContinue,
                                          child: const Text('Select CSV'))
                                    ])))),
                    const SizedBox(height: 18),
                    const Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Icon(Icons.shield_outlined, size: 19),
                          SizedBox(width: 9),
                          Expanded(
                              child: Text(
                                  'Raw CSV bytes are validated in memory and never retained. Imported trading history remains private.'))
                        ])
                  ]))),
      const SizedBox(height: 18),
      _BoundaryNote()
    ]);
  }
}

class _MappingPanel extends StatefulWidget {
  const _MappingPanel(
      {required this.preview,
      required this.filename,
      required this.onBack,
      required this.onImport});
  final ImportPreview preview;
  final String filename;
  final VoidCallback onBack;
  final void Function(Map<String, String> mapping, String timezone) onImport;

  @override
  State<_MappingPanel> createState() => _MappingPanelState();
}

class _MappingPanelState extends State<_MappingPanel> {
  String timezone = 'America/New_York';
  late Map<String, String> mapping;
  final labels = const {
    'symbol': 'Symbol',
    'side': 'Side',
    'quantity': 'Quantity',
    'price': 'Price',
    'executed_at': 'Execution time',
    'execution_id': 'Execution ID',
    'commission': 'Commission',
    'fees': 'Fees',
    'account_reference': 'Account',
    'asset_type': 'Asset type'
  };

  @override
  void initState() {
    super.initState();
    mapping = Map<String, String>.from(widget.preview.mapping);
  }

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      const _PageHeading(
          kicker: 'Import preview',
          title: 'Confirm the execution fields',
          detail:
              'We detected a custom CSV with high confidence. Nothing has been saved yet.'),
      const SizedBox(height: 28),
      Card(
          child: Padding(
              padding: const EdgeInsets.all(24),
              child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      const Icon(Icons.description_outlined),
                      const SizedBox(width: 10),
                      Expanded(
                          child: Text(widget.filename,
                              style: const TextStyle(
                                  fontWeight: FontWeight.w700))),
                      Text('${widget.preview.headers.length} columns')
                    ]),
                    const Divider(height: 34),
                    Text('COLUMN MAPPING',
                        style: TextStyle(
                            fontSize: 11,
                            letterSpacing: 1.2,
                            fontWeight: FontWeight.w800,
                            color: Theme.of(context)
                                .colorScheme
                                .onSurfaceVariant)),
                    const SizedBox(height: 14),
                    ...labels.entries.map((value) => Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: Row(children: [
                          Expanded(
                              child: Text(value.value,
                                  overflow: TextOverflow.ellipsis)),
                          const Icon(Icons.arrow_forward, size: 16),
                          const SizedBox(width: 18),
                          Expanded(
                              child: DropdownButtonFormField<String>(
                                  isExpanded: true,
                                  initialValue:
                                      mapping[value.key] ?? 'Not mapped',
                                  items: [
                                    ...widget.preview.headers,
                                    'Not mapped'
                                  ]
                                      .map((label) => DropdownMenuItem(
                                          value: label, child: Text(label)))
                                      .toList(),
                                  onChanged: (header) => setState(() {
                                        if (header == null ||
                                            header == 'Not mapped') {
                                          mapping.remove(value.key);
                                        } else {
                                          mapping[value.key] = header;
                                        }
                                      })))
                        ]))),
                    const SizedBox(height: 4),
                    DropdownButtonFormField<String>(
                        isExpanded: true,
                        initialValue: timezone,
                        decoration: const InputDecoration(
                            labelText: 'Timezone for offset-less timestamps'),
                        items: const [
                          'America/New_York',
                          'America/Chicago',
                          'America/Denver',
                          'America/Los_Angeles'
                        ]
                            .map((label) => DropdownMenuItem(
                                value: label, child: Text(label)))
                            .toList(),
                        onChanged: (value) =>
                            setState(() => timezone = value ?? timezone)),
                    const SizedBox(height: 14),
                    Text(
                        'Ambiguous or nonexistent daylight-saving times are rejected instead of guessed.',
                        style: TextStyle(
                            fontSize: 12,
                            color: Theme.of(context)
                                .colorScheme
                                .onSurfaceVariant)),
                    const SizedBox(height: 24),
                    Wrap(spacing: 12, runSpacing: 10, children: [
                      FilledButton(
                          onPressed: () => widget.onImport(mapping, timezone),
                          child: const Text('Import and analyze')),
                      OutlinedButton(
                          onPressed: widget.onBack,
                          child: const Text('Choose another file'))
                    ])
                  ])))
    ]);
  }
}

class _ProgressPanel extends StatelessWidget {
  const _ProgressPanel(
      {required this.title, required this.detail, required this.progress});
  final String title;
  final String detail;
  final double progress;

  @override
  Widget build(BuildContext context) {
    return Semantics(
        liveRegion: true,
        label: '$title, ${(progress * 100).round()} percent',
        child: Center(
            child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 620),
                child: Padding(
                    padding: const EdgeInsets.only(top: 100),
                    child: Column(children: [
                      SizedBox(
                          width: 44,
                          height: 44,
                          child: CircularProgressIndicator(
                              strokeWidth: 3, value: progress)),
                      const SizedBox(height: 28),
                      Text(title,
                          style: Theme.of(context)
                              .textTheme
                              .headlineMedium
                              ?.copyWith(fontWeight: FontWeight.w700)),
                      const SizedBox(height: 10),
                      Text(detail,
                          textAlign: TextAlign.center,
                          style: TextStyle(
                              color: Theme.of(context)
                                  .colorScheme
                                  .onSurfaceVariant,
                              height: 1.5)),
                      const SizedBox(height: 28),
                      LinearProgressIndicator(
                          value: progress,
                          borderRadius: BorderRadius.circular(2)),
                      const SizedBox(height: 16),
                      const Text(
                          'You can safely leave this screen. In-process jobs are a local foundation limitation.',
                          textAlign: TextAlign.center,
                          style: TextStyle(fontSize: 12))
                    ])))));
  }
}

class _ResultView extends StatelessWidget {
  const _ResultView(
      {required this.result, required this.wide, required this.onReset});
  final AnalysisResult result;
  final bool wide;
  final VoidCallback onReset;

  @override
  Widget build(BuildContext context) {
    final content = [
      _ScorePanel(result: result),
      _EvidencePanel(rules: result.rules),
    ];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Expanded(
            child: _PageHeading(
                kicker: 'Completed-minute reconstruction',
                title: '${result.symbol} · ${result.strategyName}',
                detail:
                    'Entry ${result.entryTime.toUtc().toIso8601String()} · Strategy version ${result.strategyVersion}')),
        IconButton(
            onPressed: onReset,
            icon: const Icon(Icons.close),
            tooltip: 'Close analysis')
      ]),
      const SizedBox(height: 26),
      if (wide)
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          SizedBox(width: 340, child: content[0]),
          const SizedBox(width: 20),
          Expanded(child: content[1])
        ])
      else
        Column(children: [content[0], const SizedBox(height: 18), content[1]]),
      const SizedBox(height: 20),
      _FeedbackPanel(result: result),
      const SizedBox(height: 20),
      Card(
          child: Padding(
              padding: const EdgeInsets.all(22),
              child:
                  Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Icon(Icons.query_stats,
                    color: Theme.of(context).colorScheme.primary),
                const SizedBox(width: 14),
                const Expanded(
                    child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                      Text('Comparison with your history',
                          style: TextStyle(fontWeight: FontWeight.w700)),
                      SizedBox(height: 5),
                      Text(
                          'Insufficient sample. At least 20 analyzed trades are required before showing a personal-history comparison.')
                    ]))
              ]))),
      const SizedBox(height: 18),
      const _BoundaryNote()
    ]);
  }
}

class _ScorePanel extends StatelessWidget {
  const _ScorePanel({required this.result});
  final AnalysisResult result;

  @override
  Widget build(BuildContext context) {
    final score = result.score;
    return Card(
        child: Padding(
            padding: const EdgeInsets.all(24),
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('ADHERENCE SCORE',
                  style: TextStyle(
                      fontSize: 11,
                      letterSpacing: 1.2,
                      fontWeight: FontWeight.w800,
                      color: Theme.of(context).colorScheme.onSurfaceVariant)),
              const SizedBox(height: 18),
              if (score != null)
                Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                  Text('$score',
                      style: const TextStyle(
                          fontSize: 66,
                          fontWeight: FontWeight.w600,
                          height: 1)),
                  const Padding(
                      padding: EdgeInsets.only(bottom: 8),
                      child: Text('/ 100', style: TextStyle(fontSize: 18)))
                ])
              else
                const Text('Unavailable',
                    style:
                        TextStyle(fontSize: 34, fontWeight: FontWeight.w600)),
              const SizedBox(height: 20),
              ClipRRect(
                  borderRadius: BorderRadius.circular(2),
                  child: LinearProgressIndicator(
                      value: score == null ? 0 : score / 100,
                      minHeight: 7,
                      color: score == null
                          ? Theme.of(context).colorScheme.outline
                          : Theme.of(context).colorScheme.primary)),
              const SizedBox(height: 20),
              Text(
                  score == null
                      ? 'Critical market history was incomplete, so the score is withheld.'
                      : '${result.rules.where((value) => value.status == RuleStatus.passed).length} of ${result.rules.where((value) => value.status != RuleStatus.notApplicable && value.status != RuleStatus.insufficient).length} evaluated rules passed.',
                  style: TextStyle(
                      height: 1.45,
                      color: Theme.of(context).colorScheme.onSurfaceVariant)),
              const Divider(height: 36),
              _MetricLine('Market data', result.provider.replaceAll('_', ' ')),
              const _MetricLine('Bars used', 'Completed only'),
              const _MetricLine('Granularity', '1 minute')
            ])));
  }
}

class _MetricLine extends StatelessWidget {
  const _MetricLine(this.label, this.value);
  final String label;
  final String value;
  @override
  Widget build(BuildContext context) => Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(children: [
        Expanded(
            child: Text(label,
                style: TextStyle(
                    color: Theme.of(context).colorScheme.onSurfaceVariant))),
        Text(value, style: const TextStyle(fontWeight: FontWeight.w600))
      ]));
}

class _EvidencePanel extends StatelessWidget {
  const _EvidencePanel({required this.rules});
  final List<RuleEvidence> rules;

  @override
  Widget build(BuildContext context) {
    return Card(
        child: Padding(
            padding: const EdgeInsets.all(24),
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('Rule evidence',
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
              const SizedBox(height: 5),
              Text(
                  'Every outcome comes from the selected strategy version and reconstructed context.',
                  style: TextStyle(
                      color: Theme.of(context).colorScheme.onSurfaceVariant)),
              const SizedBox(height: 22),
              ...rules.map((rule) => _RuleRow(rule: rule))
            ])));
  }
}

class _RuleRow extends StatelessWidget {
  const _RuleRow({required this.rule});
  final RuleEvidence rule;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final (icon, label, color) = switch (rule.status) {
      RuleStatus.passed => (
          Icons.check_circle,
          'Passed',
          const Color(0xff32715e)
        ),
      RuleStatus.failed => (Icons.cancel, 'Failed', colors.error),
      RuleStatus.insufficient => (
          Icons.help,
          'Insufficient data',
          const Color(0xff9a6a1b)
        ),
      RuleStatus.notApplicable => (
          Icons.remove_circle_outline,
          'Not applicable',
          colors.onSurfaceVariant
        ),
    };
    return Semantics(
        label:
            '${rule.label}, $label, measured ${rule.measurement}, threshold ${rule.threshold}',
        child: Container(
            padding: const EdgeInsets.symmetric(vertical: 14),
            decoration: BoxDecoration(
                border: Border(top: BorderSide(color: colors.outlineVariant))),
            child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Icon(icon, size: 20, color: color),
              const SizedBox(width: 12),
              Expanded(
                  flex: 5,
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(rule.label,
                            style:
                                const TextStyle(fontWeight: FontWeight.w600)),
                        const SizedBox(height: 3),
                        Text('$label · Weight ${rule.weight}',
                            style: TextStyle(fontSize: 12, color: color))
                      ])),
              Expanded(
                  flex: 4,
                  child: Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [
                        Text(rule.measurement,
                            textAlign: TextAlign.right,
                            style:
                                const TextStyle(fontWeight: FontWeight.w600)),
                        Text(rule.threshold,
                            textAlign: TextAlign.right,
                            style: TextStyle(
                                fontSize: 12, color: colors.onSurfaceVariant))
                      ]))
            ])));
  }
}

class _FeedbackPanel extends StatelessWidget {
  const _FeedbackPanel({required this.result});
  final AnalysisResult result;

  @override
  Widget build(BuildContext context) {
    final unavailable = result.score == null;
    String sentences(String category, String fallback) {
      final values = result.feedback
          .where((value) => value['category'] == category)
          .map((value) => value['sentence'])
          .whereType<String>();
      return values.isEmpty ? fallback : values.join(' ');
    }

    return Card(
        child: Padding(
            padding: const EdgeInsets.all(24),
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              const Text('Deterministic feedback',
                  style: TextStyle(fontSize: 20, fontWeight: FontWeight.w700)),
              const SizedBox(height: 20),
              _FeedbackSection(
                  icon: Icons.check,
                  title: 'Matched',
                  text: unavailable
                      ? 'No match claims are made without sufficient critical data.'
                      : sentences('matched',
                          'No configured rules were recorded as matched.')),
              const SizedBox(height: 18),
              _FeedbackSection(
                  icon: unavailable ? Icons.search : Icons.close,
                  title: unavailable ? 'Review' : 'Missed',
                  text: unavailable
                      ? sentences('review',
                          'Add enough completed regular-session minute history to evaluate the setup.')
                      : sentences('missed',
                          'No configured rules were recorded as missed.')),
              const SizedBox(height: 18),
              const _FeedbackSection(
                  icon: Icons.info_outline,
                  title: 'Interpretation',
                  text:
                      'This evaluates strategy adherence from historical data. It is not investment advice and does not predict future results.')
            ])));
  }
}

class _FeedbackSection extends StatelessWidget {
  const _FeedbackSection(
      {required this.icon, required this.title, required this.text});
  final IconData icon;
  final String title;
  final String text;
  @override
  Widget build(BuildContext context) =>
      Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Icon(icon, size: 20, color: Theme.of(context).colorScheme.primary),
        const SizedBox(width: 12),
        Expanded(
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(title.toUpperCase(),
              style: const TextStyle(
                  fontSize: 11,
                  letterSpacing: 1.1,
                  fontWeight: FontWeight.w800)),
          const SizedBox(height: 5),
          Text(text, style: const TextStyle(height: 1.45))
        ]))
      ]);
}

class _ErrorPanel extends StatelessWidget {
  const _ErrorPanel(
      {required this.title,
      required this.detail,
      required this.action,
      required this.onAction});
  final String title;
  final String detail;
  final String action;
  final VoidCallback onAction;
  @override
  Widget build(BuildContext context) {
    return Semantics(
      liveRegion: true,
      child: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 620),
          child: Padding(
            padding: const EdgeInsets.only(top: 80),
            child: Card(
              child: Padding(
                padding: const EdgeInsets.all(30),
                child: Column(
                  children: [
                    Icon(Icons.error_outline,
                        size: 42, color: Theme.of(context).colorScheme.error),
                    const SizedBox(height: 20),
                    Text(title,
                        textAlign: TextAlign.center,
                        style: const TextStyle(
                            fontSize: 25, fontWeight: FontWeight.w700)),
                    const SizedBox(height: 10),
                    Text(detail,
                        textAlign: TextAlign.center,
                        style: const TextStyle(height: 1.5)),
                    const SizedBox(height: 24),
                    FilledButton(onPressed: onAction, child: Text(action)),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _PageHeading extends StatelessWidget {
  const _PageHeading(
      {required this.kicker, required this.title, required this.detail});
  final String kicker;
  final String title;
  final String detail;
  @override
  Widget build(BuildContext context) =>
      Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(kicker.toUpperCase(),
            style: TextStyle(
                fontSize: 11,
                letterSpacing: 1.3,
                fontWeight: FontWeight.w800,
                color: Theme.of(context).colorScheme.primary)),
        const SizedBox(height: 9),
        Text(title,
            style: Theme.of(context)
                .textTheme
                .headlineLarge
                ?.copyWith(fontWeight: FontWeight.w700, letterSpacing: -.8)),
        const SizedBox(height: 9),
        Text(detail,
            style: TextStyle(
                fontSize: 16,
                height: 1.5,
                color: Theme.of(context).colorScheme.onSurfaceVariant))
      ]);
}

class _BoundaryNote extends StatelessWidget {
  const _BoundaryNote();
  @override
  Widget build(BuildContext context) => Card(
      child: Padding(
          padding: const EdgeInsets.all(18),
          child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            const Icon(Icons.access_time, size: 19),
            const SizedBox(width: 11),
            Expanded(
                child: Text(
                    'Minute bars cannot establish intrabar event order. Results show completed-minute evidence and retain that limitation.',
                    style: TextStyle(
                        fontSize: 13,
                        color: Theme.of(context).colorScheme.onSurfaceVariant)))
          ])));
}
