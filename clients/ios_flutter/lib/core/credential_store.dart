import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class StoredSession {
  const StoredSession({required this.refreshToken, required this.email});

  final String refreshToken;
  final String email;
}

abstract class CredentialStore {
  Future<StoredSession?> readSession();
  Future<void> writeSession(String refreshToken, String email);
  Future<void> clear();
}

class SecureCredentialStore implements CredentialStore {
  SecureCredentialStore({FlutterSecureStorage? storage})
      : storage = storage ?? const FlutterSecureStorage();

  final FlutterSecureStorage storage;

  static const refreshTokenKey = 'rulemirror.refresh_token';
  static const emailKey = 'rulemirror.account_email';

  @override
  Future<StoredSession?> readSession() async {
    final values = await storage.readAll();
    final refreshToken = values[refreshTokenKey];
    final email = values[emailKey];
    if (refreshToken == null || email == null) return null;
    return StoredSession(refreshToken: refreshToken, email: email);
  }

  @override
  Future<void> writeSession(String refreshToken, String email) async {
    await Future.wait([
      storage.write(key: refreshTokenKey, value: refreshToken),
      storage.write(key: emailKey, value: email),
    ]);
  }

  @override
  Future<void> clear() async {
    await Future.wait([
      storage.delete(key: refreshTokenKey),
      storage.delete(key: emailKey),
    ]);
  }
}
