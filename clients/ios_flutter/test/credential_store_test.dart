import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:strategy_audit_app/core/credential_store.dart';
import 'package:strategy_audit_app/features/analysis/analysis_gateway.dart';

class MemoryCredentialStore implements CredentialStore {
  String? token;
  String? email;

  @override
  Future<void> clear() async {
    token = null;
    email = null;
  }

  @override
  Future<StoredSession?> readSession() async {
    if (token == null || email == null) return null;
    return StoredSession(refreshToken: token!, email: email!);
  }

  @override
  Future<void> writeSession(String refreshToken, String accountEmail) async {
    token = refreshToken;
    email = accountEmail;
  }
}

void main() {
  test('restores and rotates a stored refresh session', () async {
    final store = MemoryCredentialStore()
      ..token = 'stored-refresh'
      ..email = 'person@example.com';
    final gateway = HttpAnalysisGateway(
        credentialStore: store,
        client: MockClient((request) async => http.Response(
            jsonEncode({
              'access_token': 'restored-access',
              'refresh_token': 'rotated-refresh'
            }),
            200)));

    expect(await gateway.restoreSession(), isTrue);
    expect(gateway.accessToken, 'restored-access');
    expect(gateway.refreshToken, 'rotated-refresh');
    expect(store.token, 'rotated-refresh');
  });

  test('failed restore clears unusable stored credentials', () async {
    final store = MemoryCredentialStore()
      ..token = 'expired-refresh'
      ..email = 'person@example.com';
    final gateway = HttpAnalysisGateway(
        credentialStore: store,
        client: MockClient((request) async => http.Response('{}', 401)));

    expect(await gateway.restoreSession(), isFalse);
    expect(store.token, isNull);
    expect(store.email, isNull);
  });

  test('logout and account deletion clear stored credentials', () async {
    for (final operation in ['logout', 'delete']) {
      final store = MemoryCredentialStore()
        ..token = 'refresh-token'
        ..email = 'person@example.com';
      final gateway = HttpAnalysisGateway(
          credentialStore: store,
          client: MockClient((request) async => http.Response('', 204)))
        ..accessToken = 'access-token'
        ..refreshToken = 'refresh-token'
        ..accountEmail = 'person@example.com';

      if (operation == 'logout') {
        await gateway.logout();
      } else {
        await gateway.deleteAccount();
      }

      expect(store.token, isNull);
      expect(store.email, isNull);
      expect(gateway.accessToken, isNull);
      expect(gateway.refreshToken, isNull);
    }
  });
}
