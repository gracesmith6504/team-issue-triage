import time

from app.cache.section_cache import SectionCache


def test_get_empty():
    cache = SectionCache()
    assert cache.get("issues") is None


def test_set_and_get():
    cache = SectionCache()
    cache.set("issues", {"total": 5}, ttl_seconds=3600)
    entry = cache.get("issues")
    assert entry is not None
    assert entry.data == {"total": 5}
    assert entry.ttl_seconds == 3600
    assert entry.generated_at is not None


def test_is_stale_missing():
    cache = SectionCache()
    assert cache.is_stale("issues") is True


def test_is_stale_fresh():
    cache = SectionCache()
    cache.set("issues", {"total": 5}, ttl_seconds=3600)
    assert cache.is_stale("issues") is False


def test_is_stale_expired():
    cache = SectionCache()
    cache.set("issues", {"total": 5}, ttl_seconds=0)
    time.sleep(0.01)
    assert cache.is_stale("issues") is True


def test_invalidate():
    cache = SectionCache()
    cache.set("issues", {"total": 5}, ttl_seconds=3600)
    cache.invalidate("issues")
    assert cache.get("issues") is None


def test_invalidate_nonexistent():
    cache = SectionCache()
    cache.invalidate("issues")


def test_all_meta():
    cache = SectionCache()
    cache.set("issues", {"total": 5}, ttl_seconds=3600)
    cache.set("pr_health", {"count": 3}, ttl_seconds=7200)
    meta = cache.all_meta()
    assert "issues" in meta
    assert "pr_health" in meta
    assert meta["issues"]["ttl_seconds"] == 3600
    assert meta["pr_health"]["ttl_seconds"] == 7200


def test_persist_and_load(tmp_path):
    cache = SectionCache(persist_dir=tmp_path)
    cache.set("issues", {"total": 5}, ttl_seconds=3600)
    assert (tmp_path / "issues.json").exists()

    cache2 = SectionCache(persist_dir=tmp_path)
    cache2.load_persisted()
    entry = cache2.get("issues")
    assert entry is not None
    assert entry.data == {"total": 5}
    assert entry.ttl_seconds == 3600


def test_invalidate_removes_persisted_file(tmp_path):
    cache = SectionCache(persist_dir=tmp_path)
    cache.set("issues", {"total": 5}, ttl_seconds=3600)
    assert (tmp_path / "issues.json").exists()
    cache.invalidate("issues")
    assert cache.get("issues") is None
    assert not (tmp_path / "issues.json").exists()

    cache2 = SectionCache(persist_dir=tmp_path)
    cache2.load_persisted()
    assert cache2.get("issues") is None
