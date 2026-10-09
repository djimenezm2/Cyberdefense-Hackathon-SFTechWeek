import json
import subprocess

import pytest

from rootlane_toolbox.integrations.sandbox import PatchError, normalize_diff, normalize_rule
from rootlane_toolbox.integrations.semgrep_runner import rule_errors

SOURCE = (
    "export function login () {\n"
    "  return (req: Request, res: Response, next: NextFunction) => {\n"
    "    verifyPreLoginChallenges(req) // vuln-code-snippet hide-line\n"
    "    models.sequelize.query(`SELECT * FROM Users WHERE email = '${req.body.email || ''}' AND password = '${security.hash(req.body.password || '')}' AND deletedAt IS NULL`, { model: UserModel, plain: true }) // vuln-code-snippet vuln-line loginAdminChallenge\n"
    "      .then((authenticatedUser) => {\n"
    "        res.json(authenticatedUser)\n"
    "      })\n"
    "  }\n"
    "}\n"
)
QUERY = "models.sequelize.query(`SELECT * FROM Users WHERE email = '${req.body.email || ''}' AND password = '${security.hash(req.body.password || '')}' AND deletedAt IS NULL`, { model: UserModel, plain: true })"
# The agent's verify_patch diff from the live session: bare @@, no context, no trailing comment.
LIVE_DIFF = (
    "--- a/routes/login.ts\n+++ b/routes/login.ts\n@@\n"
    f"-  {QUERY}\n"
    "+  models.sequelize.query(\n"
    "+    'SELECT * FROM Users WHERE email = $email AND password = $password AND deletedAt IS NULL',\n"
    "+    { bind: { email: req.body.email || '', password: security.hash(req.body.password || '') }, model: UserModel, plain: true }\n"
    "+  )\n"
)
# The agent's first rule from the live session: an unquoted flow mapping breaks the YAML.
LIVE_BAD_RULE = (
    "rules:\n  - id: sequelize-raw-query-string-interpolation\n    languages: [typescript]\n"
    "    severity: ERROR\n    message: raw query\n    patterns:\n"
    "      - pattern: $M.sequelize.query(`...${...}...`, ...)\n"
    "      - pattern-not: $M.sequelize.query(\"...\", {..., bind: $BIND, ...})\n"
)
GOOD_RULE = (
    "rules:\n  - id: sequelize-raw-query-string-interpolation\n    languages: [typescript]\n"
    "    severity: ERROR\n    message: raw query\n"
    "    pattern: $M.sequelize.query(`...${...}...`, ...)\n"
)


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "routes").mkdir()
    (tmp_path / "routes" / "login.ts").write_text(SOURCE)
    return tmp_path


def _apply(repo, diff):
    proc = subprocess.run(["git", "apply", "--recount", "-p1", "-"], cwd=repo, input=diff,
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return (repo / "routes" / "login.ts").read_text()


def test_live_diff_with_bare_hunk_and_wrong_indent_applies(repo):
    out = _apply(repo, normalize_diff(LIVE_DIFF, str(repo)))
    assert "$email" in out and "vuln-line" not in out
    assert "    models.sequelize.query(\n      'SELECT" in out
    assert "      .then((authenticatedUser)" in out


@pytest.mark.parametrize("wrap", [
    lambda d: "```diff\n" + d + "```\n",
    lambda d: d.replace("\n", "\r\n"),
    lambda d: d.replace("--- a/", "--- ").replace("+++ b/", "+++ "),
    lambda d: d.rstrip("\n"),
])
def test_fences_crlf_missing_prefixes_and_newline_are_normalized(repo, wrap):
    out = _apply(repo, normalize_diff(wrap(LIVE_DIFF), str(repo)))
    assert "$email" in out


def test_valid_hunk_headers_are_left_alone(repo):
    diff = ("--- a/routes/login.ts\n+++ b/routes/login.ts\n@@ -5,3 +5,3 @@\n"
            "       .then((authenticatedUser) => {\n"
            "-        res.json(authenticatedUser)\n+        res.json({})\n"
            "       })\n")
    assert normalize_diff(diff, str(repo)) == diff
    assert "res.json({})" in _apply(repo, diff)


def test_hunk_that_matches_nothing_is_a_patch_error_naming_the_line(repo):
    diff = "--- a/routes/login.ts\n+++ b/routes/login.ts\n@@\n-  notInTheFile()\n+  x()\n"
    with pytest.raises(PatchError, match="notInTheFile"):
        normalize_diff(diff, str(repo))


def test_paths_outside_the_tree_are_still_refused(repo):
    diff = "--- a/../etc/x\n+++ b/../etc/x\n@@\n-a\n+b\n"
    with pytest.raises(PatchError):
        normalize_diff(diff, str(repo))


def test_rule_fences_and_crlf_are_stripped():
    assert normalize_rule("```yaml\r\n" + GOOD_RULE.replace("\n", "\r\n") + "```") == GOOD_RULE


def test_rule_errors_reports_semgreps_message_for_the_live_rule(tmp_path):
    path = tmp_path / "rule.yaml"
    path.write_text(LIVE_BAD_RULE)
    message = rule_errors(str(path))
    assert "mapping values are not allowed" in message and len(message) <= 500


def test_rule_errors_is_none_for_a_valid_rule(tmp_path):
    path = tmp_path / "rule.yaml"
    path.write_text(GOOD_RULE)
    assert rule_errors(str(path)) is None


def test_rule_errors_uses_the_runner_output():
    out = json.dumps({"errors": [{"level": "error", "message": "bad pattern"}]})
    assert rule_errors("r.yaml", runner=lambda args, cwd: (7, out)) == "bad pattern"
    assert rule_errors("r.yaml", runner=lambda args, cwd: (2, "not json")) == "semgrep exited with code 2"
