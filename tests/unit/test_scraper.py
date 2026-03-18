"""Tests for web scraper."""

from unittest.mock import MagicMock, patch

import pytest
from rag.scraper import ScrapedPage, scrape_page

SAMPLE_HTML = """
<html>
<head><title>About Us</title></head>
<body>
  <nav>Navigation here</nav>
  <main>
    <h1>About Our Organization</h1>
    <p>We help communities through donations.</p>
    <img src="logo.png" alt="Organization logo showing community hands">
    <p>Founded in 2005, we have served 100,000 people.</p>
  </main>
  <footer>Footer content</footer>
</body>
</html>
"""


class TestScrapePage:
    @patch("rag.scraper.httpx")
    def test_extracts_text_content(self, mock_httpx):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_HTML
        mock_response.url = "https://example.com/about"
        mock_httpx.get.return_value = mock_response

        page = scrape_page("https://example.com/about")
        assert "We help communities through donations" in page.text
        assert "Founded in 2005" in page.text

    @patch("rag.scraper.httpx")
    def test_extracts_alt_text_from_images(self, mock_httpx):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_HTML
        mock_response.url = "https://example.com/about"
        mock_httpx.get.return_value = mock_response

        page = scrape_page("https://example.com/about")
        assert "Organization logo showing community hands" in page.text

    @patch("rag.scraper.httpx")
    def test_strips_nav_and_footer(self, mock_httpx):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_HTML
        mock_response.url = "https://example.com/about"
        mock_httpx.get.return_value = mock_response

        page = scrape_page("https://example.com/about")
        assert "Navigation here" not in page.text
        assert "Footer content" not in page.text

    @patch("rag.scraper.httpx")
    def test_returns_title(self, mock_httpx):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_HTML
        mock_response.url = "https://example.com/about"
        mock_httpx.get.return_value = mock_response

        page = scrape_page("https://example.com/about")
        assert page.title == "About Us"

    @patch("rag.scraper.httpx")
    def test_returns_url(self, mock_httpx):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_HTML
        mock_response.url = "https://example.com/about"
        mock_httpx.get.return_value = mock_response

        page = scrape_page("https://example.com/about")
        assert page.url == "https://example.com/about"

    @patch("rag.scraper.httpx")
    def test_returns_raw_html(self, mock_httpx):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = SAMPLE_HTML
        mock_response.url = "https://example.com"
        mock_httpx.get.return_value = mock_response

        page = scrape_page("https://example.com")
        assert page.raw_html == SAMPLE_HTML

    @patch("rag.scraper.httpx")
    def test_http_error_raises(self, mock_httpx):
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = Exception("Not Found")
        mock_httpx.get.return_value = mock_response

        with pytest.raises(Exception, match="Not Found"):
            scrape_page("https://example.com/404")

    def test_scraped_page_is_frozen(self):
        page = ScrapedPage(
            url="https://example.com",
            title="Test",
            text="content",
            raw_html="<html>",
        )
        with pytest.raises(AttributeError):
            page.text = "modified"
