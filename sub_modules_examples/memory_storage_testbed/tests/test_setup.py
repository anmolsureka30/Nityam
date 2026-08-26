def test_package_imports():
    import testbed
    from testbed import config

    assert testbed is not None
    assert config.PROJECT_ID == "nityam-506707"
