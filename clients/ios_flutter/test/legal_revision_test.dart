import 'package:flutter_test/flutter_test.dart';
import 'package:strategy_audit_app/core/app_config.dart';

void main() {
  test('legal revision is current product revision', () {
    expect(AppConfig.legalLastUpdated, 'August 7, 2026');
  });
}
