from service.settings_rules import interval_issues, mask_dsn, mask_secret, merge_secrets, present


def test_mask_keeps_ends():
    assert mask_secret("sk-b84edfc1358742ae8c5250b7ca35725f") == "sk-****725f"
    assert mask_secret("") == ""
    assert mask_secret("abcd") == "****"


def test_mask_dsn_password():
    shown = mask_dsn("postgresql://vcos:vcos@127.0.0.1:5432/vcos")
    assert "vcos@" not in shown.split("://", 1)[1].split("@", 1)[0] or "****" in shown
    assert shown.startswith("postgresql://vcos:")
    assert shown.endswith("@127.0.0.1:5432/vcos")
    assert "****" in shown


def test_unchanged_secret_is_kept():
    stored = {
        "source": "sim",
        "cluster": {"token": "cluster-token-9f2a"},
        "sim": {"base_url": "https://cluster.simuoss.cn/api", "speed": 1},
        "jobs": [],
        "storage": {"dsn": "postgresql://vcos:vcos@127.0.0.1:5432/vcos"},
        "ai": {"api_key": "sk-b84edfc1358742ae8c5250b7ca35725f"},
        "rules": {},
    }
    shown = present(stored)
    merged = merge_secrets({**shown, "source": "sim"}, stored)
    assert merged["cluster"]["token"] == "cluster-token-9f2a"
    assert merged["ai"]["api_key"] == stored["ai"]["api_key"]
    assert merged["storage"]["dsn"] == stored["storage"]["dsn"]


def test_new_secret_replaces():
    stored = {
        "source": "cluster",
        "cluster": {"token": "old-token"},
        "sim": {},
        "jobs": [],
        "storage": {"dsn": "postgresql://vcos:old@127.0.0.1:5432/vcos"},
        "ai": {"api_key": "old-key"},
        "rules": {},
    }
    incoming = present(stored)
    incoming["cluster"]["token"] = "new-token-value"
    incoming["ai"]["api_key"] = "new-api-key"
    incoming["storage"]["dsn"] = "postgresql://vcos:newpass@127.0.0.1:5432/vcos"
    merged = merge_secrets(incoming, stored)
    assert merged["cluster"]["token"] == "new-token-value"
    assert merged["ai"]["api_key"] == "new-api-key"
    assert merged["storage"]["dsn"].endswith(":newpass@127.0.0.1:5432/vcos")


def test_interval_floor():
    jobs = [
        {"key": key, "interval_s": 5, "enabled": True}
        for key in ("fleet", "slots", "machine", "runs", "samples", "plans", "batches", "calib", "agg")
    ]
    assert interval_issues(jobs) == []
    jobs[0]["interval_s"] = 0
    issues = interval_issues(jobs)
    assert issues[0]["field"] == "jobs.fleet.interval_s"
    jobs[0]["enabled"] = False
    assert interval_issues(jobs) == []


def test_job_keys_must_match():
    issues = interval_issues([{"key": "fleet", "interval_s": 5, "enabled": True}])
    assert issues[0]["field"] == "jobs"
