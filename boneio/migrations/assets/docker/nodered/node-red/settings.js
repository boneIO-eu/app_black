/**
 * Node-RED settings for boneIO.
 *
 * The 1.5.0 pentest's worst finding (F-01) was here: with no `adminAuth`, the
 * Node-RED admin API was open to anyone who could reach the device, and
 * deploying a flow containing an `exec` node is arbitrary code execution as the
 * container user. Two unauthenticated HTTP calls, no credentials anywhere.
 *
 * Authentication now delegates to boneIO itself rather than keeping a second
 * set of credentials here. Reasons, in order:
 *
 *   - One account list. An admin added or removed in the boneIO panel gains or
 *     loses Node-RED with it; nothing to keep in sync, nothing to forget.
 *   - No second copy of the password hashing. boneIO stores scrypt hashes in
 *     its own format, and reimplementing that check in JavaScript would mean
 *     two implementations that must agree forever.
 *   - The real login path is reused, including its rate limiting, so guessing
 *     against Node-RED is throttled exactly as guessing against the panel is.
 *
 * Only administrators are admitted. A read-only boneIO account has no business
 * in the flow editor: deploying a flow is code execution, which is the whole
 * point of this file.
 *
 * If boneIO is unreachable the answer is "no". That is the right way round —
 * an authentication source that cannot be consulted must not be assumed to
 * have said yes. The refusal is logged, so a misconfigured address shows up in
 * `docker logs` rather than as a silent inability to sign in.
 *
 * The API address assumes boneIO's default port. A device serving the panel on
 * a different `web.port` has to say so, by setting BONEIO_API_URL on the
 * node-red service in docker-compose.yaml. That is deliberately not written
 * into the compose file by the migration: cloud registration edits that same
 * file, and replacing it to carry one optional variable is a poor trade.
 */

const BONEIO_API =
  process.env.BONEIO_API_URL || "http://host.docker.internal:8090";

/**
 * Administrators seen to authenticate recently.
 *
 * Node-RED calls `users(username)` to re-resolve the account behind a token it
 * already issued, at a point where no password is available to check. The
 * entry is only ever created after a successful `authenticate`, so this grants
 * nothing that was not just proven; the expiry bounds how long a demoted or
 * deleted account keeps an open editor session.
 */
const recentAdmins = new Map();
const ADMIN_CACHE_MS = 5 * 60 * 1000;

function rememberAdmin(username) {
  recentAdmins.set(username, Date.now() + ADMIN_CACHE_MS);
}

function recallAdmin(username) {
  const expires = recentAdmins.get(username);
  if (!expires) {
    return null;
  }
  if (expires < Date.now()) {
    recentAdmins.delete(username);
    return null;
  }
  return { username: username, permissions: "*" };
}

/**
 * Ask boneIO whether these credentials belong to one of its administrators.
 *
 * @param {string} username
 * @param {string} password
 * @returns {Promise<object|null>} A Node-RED user, or null to refuse.
 */
async function authenticateWithBoneIO(username, password) {
  if (!username || !password) {
    return null;
  }

  let response;
  try {
    response = await fetch(BONEIO_API + "/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: username, password: password }),
      signal: AbortSignal.timeout(15000),
    });
  } catch (err) {
    // Unreachable, timed out, DNS gone. Refuse: an auth source that cannot be
    // asked has not said yes.
    console.warn("boneIO auth unreachable:", err.message);
    return null;
  }

  if (!response.ok) {
    // 401 wrong credentials, 429 throttled, 403 device not set up yet.
    return null;
  }

  let body;
  try {
    body = await response.json();
  } catch (err) {
    console.warn("boneIO auth returned unreadable body:", err.message);
    return null;
  }

  if (body.role !== "admin") {
    // A viewer may watch the panel; the flow editor is code execution.
    console.warn("Refused Node-RED access to non-admin account:", username);
    return null;
  }

  const resolved = body.username || username;
  rememberAdmin(resolved);
  return { username: resolved, permissions: "*" };
}

module.exports = {
  httpAdminRoot: "/nodered",
  httpNodeRoot: "/nodered",
  ui: { path: "ui" },

  adminAuth: {
    type: "credentials",
    authenticate: authenticateWithBoneIO,
    users: function (username) {
      return Promise.resolve(recallAdmin(username));
    },
    // No `default`: without it Node-RED grants anonymous users nothing, which
    // is exactly what F-01 was about.
  },
};
