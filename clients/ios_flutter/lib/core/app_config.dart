class AppConfig {
  static const displayName = String.fromEnvironment(
    'APP_DISPLAY_NAME',
    defaultValue: 'Rule Mirror',
  );
  static const apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000/api/v1',
  );
}
