import pytest

from rootlane_toolbox.core.guards import (
    GuardError,
    assert_approved,
    assert_read_only_sql,
    assert_verify_passed,
    diff_hash,
    resolve_source_path,
)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM http_requests LIMIT 10",
        "  with recent as (select 1) select * from recent  ",
    ],
)
def test_read_only_sql_allows_selects(sql):
    assert assert_read_only_sql(sql)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1; INSERT INTO http_requests VALUES (1)",
        "INSERT INTO http_requests VALUES (1)",
        "ALTER TABLE http_requests DELETE WHERE 1",
        "DROP TABLE http_requests",
        "SELECT 1 -- ; and a comment",
        "",
    ],
)
def test_read_only_sql_rejects_writes_and_multistatement(sql):
    with pytest.raises(GuardError):
        assert_read_only_sql(sql)


def test_path_guard_allows_repo_relative(tmp_path):
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "insecurity.ts").write_text("x")
    assert resolve_source_path(str(tmp_path), "lib/insecurity.ts").name == "insecurity.ts"


@pytest.mark.parametrize("bad", ["../etc/passwd", "/etc/passwd", "lib/../../x", "..%2fx"])
def test_path_guard_rejects_escapes(tmp_path, bad):
    with pytest.raises(GuardError):
        resolve_source_path(str(tmp_path), bad)


def test_verify_gate_requires_passing_verify_for_this_diff():
    diff = "--- a\n+++ b\n@@ -1 +1 @@\n-x\n+y\n"
    assert assert_verify_passed({"hash": diff_hash(diff), "passed": True}, diff) is None
    for bad in (
        None,
        {"hash": diff_hash(diff), "passed": False},
        {"hash": "p_other", "passed": True},
    ):
        with pytest.raises(GuardError):
            assert_verify_passed(bad, diff)


def test_approval_gate_requires_matching_approve():
    assert assert_approved({"decision": "approve", "proposal_hash": "p_1"}, "p_1") is None
    for bad in (
        None,
        {"decision": "reject", "proposal_hash": "p_1"},
        {"decision": "approve", "proposal_hash": "p_2"},
    ):
        with pytest.raises(GuardError):
            assert_approved(bad, "p_1")


@pytest.mark.parametrize(
    "fn",
    ["url", "s3", "s3Cluster", "file", "remote", "remoteSecure", "cluster", "clusterAllReplicas",
     "executable", "mysql", "postgresql", "jdbc", "odbc", "hdfs", "azureBlobStorage", "input",
     "numbers", "numbers_mt", "zeros", "generateRandom", "merge", "dictionary"],
)
def test_read_only_sql_rejects_table_functions(fn):
    for call in (f"SELECT * FROM {fn}('x')", f"SELECT * FROM {fn.upper()} ('x')"):
        with pytest.raises(GuardError):
            assert_read_only_sql(call)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1 SETTINGS max_threads = 1",
        "SELECT * FROM http_requests INTO OUTFILE '/tmp/x'",
        "SELECT * FROM http_requests FORMAT CSV",
        "SELECT 1 # trailing comment",
    ],
)
def test_read_only_sql_rejects_settings_outfile_format_and_hash_comments(sql):
    with pytest.raises(GuardError):
        assert_read_only_sql(sql)


def test_read_only_sql_keeps_allowing_similar_looking_names():
    assert assert_read_only_sql("SELECT formatDateTime(ts, '%Y') FROM http_requests")
    assert assert_read_only_sql("SELECT count() FROM http_requests WHERE route = 'numbers'")


def test_path_guard_rejects_embedded_nul(tmp_path):
    with pytest.raises(GuardError):
        resolve_source_path(str(tmp_path), "lib/a\x00b")


def test_verify_gate_requires_boolean_true():
    diff = "d"
    with pytest.raises(GuardError):
        assert_verify_passed({"hash": diff_hash(diff), "passed": "false"}, diff)
