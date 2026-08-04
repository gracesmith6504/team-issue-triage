from unittest.mock import MagicMock, patch


@patch("app.__main__.run_triage")
@patch("app.__main__.load_config")
def test_main_default_mode(mock_config, mock_triage):
    mock_config.return_value = MagicMock()
    from app.__main__ import main

    with patch("sys.argv", ["app"]):
        main()
    mock_triage.assert_called_once()


@patch("app.__main__.run_review")
@patch("app.__main__.load_config")
def test_main_review_mode(mock_config, mock_review):
    mock_config.return_value = MagicMock()
    from app.__main__ import main

    with patch("sys.argv", ["app", "--mode", "review"]):
        main()
    mock_review.assert_called_once()


@patch("app.__main__.run_digest")
@patch("app.__main__.load_config")
def test_main_digest_mode(mock_config, mock_digest):
    mock_config.return_value = MagicMock()
    from app.__main__ import main

    with patch("sys.argv", ["app", "--mode", "digest"]):
        main()
    mock_digest.assert_called_once()


@patch("app.__main__.run_review")
@patch("app.__main__.load_config")
def test_main_review_with_filters(mock_config, mock_review):
    mock_config.return_value = MagicMock()
    from app.__main__ import main

    with patch(
        "sys.argv", ["app", "--mode", "review", "--since", "48", "--team", "agent-ops"]
    ):
        main()
    mock_review.assert_called_once_with(
        mock_config.return_value,
        since_hours=48,
        team_filter="agent-ops",
    )
