/**
 * How each MCP client is pointed at this controller, with a new API key.
 *
 * Formats as each vendor documents them (October 2026); they drift, so keep
 * this list the only place they are written down. Only Claude Code was tried
 * against a controller; the rest follow their documentation.
 *
 * The chat apps (ChatGPT, claude.ai, the Gemini app) are not here on purpose:
 * they reach MCP servers from the vendor's cloud, which needs a public address
 * and OAuth - a controller on a home network with an API key has neither.
 */

export type CaHint = 'node' | 'codex' | 'system';

export interface McpClient {
  id: string;
  label: string;
  /** Where the snippet goes: a translation key under api_keys.mcp_where_*. */
  where: string;
  /** How the client is told to trust a self-signed certificate. */
  ca: CaHint;
  snippet: (url: string, secret: string) => string;
}

const json = (value: unknown) => JSON.stringify(value, null, 2);

export const MCP_CLIENTS: McpClient[] = [
  {
    id: 'claude_code',
    label: 'Claude Code',
    where: 'terminal',
    ca: 'node',
    snippet: (url, secret) =>
      `claude mcp add --scope user --transport http boneio ${url} --header "Authorization: Bearer ${secret}"`,
  },
  {
    id: 'codex',
    label: 'Codex (OpenAI)',
    where: 'codex',
    ca: 'codex',
    snippet: (url, secret) =>
      `# ~/.codex/config.toml\n[mcp_servers.boneio]\nurl = "${url}"\nbearer_token_env_var = "BONEIO_API_KEY"\n\n` +
      `# shell profile (~/.bashrc, ~/.zshrc)\nexport BONEIO_API_KEY="${secret}"`,
  },
  {
    id: 'gemini_cli',
    label: 'Gemini CLI',
    where: 'terminal',
    ca: 'node',
    snippet: (url, secret) =>
      `gemini mcp add -s user --transport http --header "Authorization: Bearer ${secret}" boneio ${url}`,
  },
  {
    id: 'antigravity',
    label: 'Antigravity',
    where: 'antigravity',
    ca: 'system',
    snippet: (url, secret) =>
      json({ mcpServers: { boneio: { serverUrl: url, headers: { Authorization: `Bearer ${secret}` } } } }),
  },
  {
    id: 'cursor',
    label: 'Cursor',
    where: 'cursor',
    ca: 'system',
    snippet: (url, secret) =>
      json({ mcpServers: { boneio: { url, headers: { Authorization: `Bearer ${secret}` } } } }),
  },
  {
    // The key is asked for once and kept by VS Code, not written to a
    // settings file that Settings Sync would carry to the cloud.
    id: 'vscode',
    label: 'VS Code (Copilot)',
    where: 'vscode',
    ca: 'system',
    snippet: (url) =>
      json({
        inputs: [{ type: 'promptString', id: 'boneio-key', description: 'boneIO API key', password: true }],
        servers: { boneio: { type: 'http', url, headers: { Authorization: 'Bearer ${input:boneio-key}' } } },
      }),
  },
  {
    // Claude Desktop runs only local servers from its config file; mcp-remote
    // (a community npm package) bridges to the controller. The header has no
    // space in args because some launchers on Windows split on it.
    id: 'claude_desktop',
    label: 'Claude Desktop',
    where: 'claude_desktop',
    ca: 'node',
    snippet: (url, secret) =>
      json({
        mcpServers: {
          boneio: {
            command: 'npx',
            args: ['-y', 'mcp-remote', url, '--transport', 'http-only', '--header', 'Authorization:${AUTH_HEADER}'],
            env: { AUTH_HEADER: `Bearer ${secret}` },
          },
        },
      }),
  },
];
