"""Unit tests for portfolio_service PnL formatting."""

from fastapistock.services.portfolio_service import _format_pnl_reply


class TestFormatPnlReply:
    def test_both_positive_values(self) -> None:
        result = _format_pnl_reply(1_234_567.0, 890_123.0)
        assert '📈 投資組合未實現損益' in result
        assert '🇹🇼 台股：$+1,234,567 TWD' in result
        assert '🇺🇸 美股：$+890,123 TWD' in result
        assert '合計：$+2,124,690 TWD' in result

    def test_negative_tw_positive_us(self) -> None:
        result = _format_pnl_reply(-123_456.0, 890_123.0)
        assert '🇹🇼 台股：$-123,456 TWD' in result
        assert '🇺🇸 美股：$+890,123 TWD' in result
        assert '合計：$+766,667 TWD' in result

    def test_tw_none_partial_failure(self) -> None:
        result = _format_pnl_reply(None, 890_123.0)
        assert '🇹🇼 台股：無法取得' in result
        assert '🇺🇸 美股：$+890,123 TWD' in result
        assert '合計：無法計算（部分資料缺失）' in result

    def test_us_none_partial_failure(self) -> None:
        result = _format_pnl_reply(1_234_567.0, None)
        assert '🇹🇼 台股：$+1,234,567 TWD' in result
        assert '🇺🇸 美股：無法取得' in result
        assert '合計：無法計算（部分資料缺失）' in result

    def test_both_none_total_failure(self) -> None:
        result = _format_pnl_reply(None, None)
        assert '📈 投資組合未實現損益' in result
        assert '無法取得損益資料，請稍後再試' in result
        assert '台股' not in result
        assert '美股' not in result

    def test_zero_value(self) -> None:
        result = _format_pnl_reply(0.0, 0.0)
        assert '🇹🇼 台股：$+0 TWD' in result
        assert '🇺🇸 美股：$+0 TWD' in result
        assert '合計：$+0 TWD' in result
