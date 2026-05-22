from csi_parser import parse_line


def test_parse_line_valid():
    line = "123456,-52,14,18,21,19,80,22"
    result = parse_line(line)

    assert result is not None
    assert result["timestamp"] == 123456
    assert result["rssi"] == -52
    assert result["csi"] == [14.0, 18.0, 21.0, 19.0, 80.0, 22.0]

    # mean of [14, 18, 21, 19, 80, 22] is 174 / 6 = 29.0
    assert result["raw_signal"] == 29.0


def test_parse_line_invalid_length():
    # Only 7 items instead of 8
    line = "123456,-52,14,18,21,19,80"
    assert parse_line(line) is None

    # 9 items
    line_long = "123456,-52,14,18,21,19,80,22,99"
    assert parse_line(line_long) is None


def test_parse_line_non_numeric():
    # 'error' in place of RSSI
    line = "123456,error,14,18,21,19,80,22"
    assert parse_line(line) is None

    # 'corrupt' in place of subcarrier value
    line_sub = "123456,-52,14,18,corrupt,19,80,22"
    assert parse_line(line_sub) is None


def test_parse_line_empty():
    assert parse_line("") is None


def test_parse_line_ignores_firmware_status_lines(caplog):
    assert parse_line("# REAL_CSI_WIFI_CONNECTING") is None
    assert "Invalid line format" not in caplog.text
    assert parse_line("   ") is None
