def pytest_configure(config):
    config.addinivalue_line("markers", "slow: hits real APIs (LLM, GitHub)")


def pytest_collection_modifyitems(config, items):
    if config.option.markexpr:
        return
    skip_slow = __import__("pytest").mark.skip(reason="need -m slow to run")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)
