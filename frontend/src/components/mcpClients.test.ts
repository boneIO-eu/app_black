import { describe, expect, it } from 'vitest';
import { MCP_CLIENTS } from './mcpClients';

const URL = 'https://192.168.1.10:8443/api/mcp';
const SECRET = 'boneio_pat_abc123';

describe('MCP client snippets', () => {
  it.each(MCP_CLIENTS.map((c) => [c.id, c]))('%s names the endpoint', (_, client) => {
    expect(client.snippet(URL, SECRET)).toContain(URL);
  });

  it.each(MCP_CLIENTS.filter((c) => c.snippet(URL, SECRET).trimStart().startsWith('{')).map((c) => [c.id, c]))(
    '%s is valid JSON with the key in an Authorization header',
    (id, client) => {
      const text = client.snippet(URL, SECRET);
      expect(() => JSON.parse(text)).not.toThrow();
      // VS Code asks for the key itself rather than storing it in the file.
      if (id === 'vscode') expect(text).not.toContain(SECRET);
      else expect(text).toContain(`Bearer ${SECRET}`);
    },
  );

  it('the command-line clients carry the key', () => {
    for (const id of ['claude_code', 'gemini_cli', 'codex']) {
      expect(MCP_CLIENTS.find((c) => c.id === id)!.snippet(URL, SECRET)).toContain(SECRET);
    }
  });
});
