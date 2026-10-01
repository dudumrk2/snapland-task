import { describe, it, expect } from 'vitest';
import { escapeHtml } from '../../../src/utils/escapeHtml';

describe('escapeHtml', () => {
  it('escapes &, <, >, ", and \'', () => {
    const raw = `<script>alert("XSS" & 'test')</script>`;
    const escaped = escapeHtml(raw);
    expect(escaped).toBe('&lt;script&gt;alert(&quot;XSS&quot; &amp; &#39;test&#39;)&lt;/script&gt;');
  });

  it('handles empty string and falsy input', () => {
    expect(escapeHtml('')).toBe('');
    expect(escapeHtml(null as unknown as string)).toBe('');
    expect(escapeHtml(undefined as unknown as string)).toBe('');
  });

  it('leaves clean strings untouched', () => {
    expect(escapeHtml('Tel Aviv Zone 1')).toBe('Tel Aviv Zone 1');
  });
});
