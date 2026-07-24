from unittest.mock import MagicMock, patch


@patch("app.__main__.run_triage")
@patch("app.__main__.load_config")
def test_main_triage_mode(mock_load_config, mock_run_triage):
    mock_config = MagicMock()
    mock_load_config.return_value = mock_config

    with patch("sys.argv", ["app", "--mode", "triage"]):
        from app.__main__ import main

        main()

    mock_load_config.assert_called_once()
    mock_run_triage.assert_called_once_with(mock_config)


@patch("app.__main__.run_digest")
@patch("app.__main__.load_config")
def test_main_digest_mode(mock_load_config, mock_run_digest):
    mock_config = MagicMock()
    mock_load_config.return_value = mock_config

    with patch("sys.argv", ["app", "--mode", "digest"]):
        from app.__main__ import main

        main()

    mock_load_config.assert_called_once()
    mock_run_digest.assert_called_once_with(mock_config)


@patch("app.__main__.run_triage")
@patch("app.__main__.load_config")
def test_main_default_mode_is_triage(mock_load_config, mock_run_triage):
    mock_load_config.return_value = MagicMock()

    with patch("sys.argv", ["app"]):
        from app.__main__ import main

        main()

    mock_run_triage.assert_called_once()
