import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, test } from 'vitest';
import { LEGAL_LAST_UPDATED } from '../src/legal';

describe('legal revision', () => {
  test('terms and privacy pages share the app revision', () => {
    const root = resolve(import.meta.dirname, '..', 'public');
    for (const page of ['terms.html', 'privacy.html']) {
      expect(readFileSync(resolve(root, page), 'utf8')).toContain(
          `Last updated: ${LEGAL_LAST_UPDATED}`);
    }
  });
});
