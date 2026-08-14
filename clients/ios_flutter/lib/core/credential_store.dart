import 'package:flutter_secure_storage/flutter_secure_storage.dart';

abstract class CredentialStore {
  Future<String?> readRefreshToken();
  Future<String?> readEmail();
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
  Future<String?> readRefreshToken() => storage.read(key: refreshTokenKey);

  @override
  Future<String?> readEmail() => storage.read(key: emailKey);

  @override
  Future<void> writeSession(String refreshToken, String email) async {
    await storage.write(key: refreshTokenKey, value: refreshToken);
    await storage.write(key: emailKey, value: email);
  }

  @override
  Future<void> clear() async {
    await storage.delete(key: refreshTokenKey);
    await storage.delete(key: emailKey);
  }
}
