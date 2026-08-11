import unittest
from backend.formatter import markdown_to_telegram_html

class TestFormatter(unittest.TestCase):
    def test_markdown_bold(self):
        text = "Hello **World** and __Telegram__"
        expected = "Hello <b>World</b> and <b>Telegram</b>"
        self.assertEqual(markdown_to_telegram_html(text), expected)

    def test_markdown_bullets(self):
        text = "Items:\n* **Customers:** Onboard\n- **Products:** Catalog"
        expected = "Items:\n• <b>Customers:</b> Onboard\n• <b>Products:</b> Catalog"
        self.assertEqual(markdown_to_telegram_html(text), expected)

    def test_html_escaping(self):
        text = "Price < 50 and & GST"
        expected = "Price &lt; 50 and &amp; GST"
        self.assertEqual(markdown_to_telegram_html(text), expected)

    def test_inline_code(self):
        text = "Run `python test.py` now"
        expected = "Run <code>python test.py</code> now"
        self.assertEqual(markdown_to_telegram_html(text), expected)

if __name__ == "__main__":
    unittest.main()
