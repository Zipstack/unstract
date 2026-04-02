"""
Tests for LLMWhisperer document extraction integration.
"""

from unittest.mock import patch, Mock

from django.test import TestCase
from django.conf import settings

from ...integrations.llmwhisperer_client import (
    LLMWhispererClient,
    ExtractionStatus
)


class LLMWhispererClientTest(TestCase):
    """Test cases for LLMWhispererClient."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock settings
        self.settings_patcher = patch.multiple(
            settings,
            LLMWHISPERER_BASE_URL='https://test.llmwhisperer.com',
            LLMWHISPERER_API_KEY='test-api-key'
        )
        self.settings_patcher.start()

        # Mock requests
        self.requests_patcher = patch('lookup.integrations.llmwhisperer_client.requests')
        self.mock_requests = self.requests_patcher.start()

        # Initialize client
        self.client = LLMWhispererClient()

    def tearDown(self):
        """Clean up patches."""
        self.settings_patcher.stop()
        self.requests_patcher.stop()

    def test_initialization(self):
        """Test client initialization."""
        self.assertEqual(self.client.base_url, 'https://test.llmwhisperer.com')
        self.assertEqual(self.client.api_key, 'test-api-key')
        self.assertIsNotNone(self.client.session)

    def test_extract_text_success(self):
        """Test successful text extraction."""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'extraction_id': 'test-id-123',
            'status': 'processing'
        }
        self.mock_requests.post.return_value = mock_response

        # Test extraction
        file_content = b"PDF content here"
        file_name = "test.pdf"

        extraction_id, status = self.client.extract_text(
            file_content,
            file_name
        )

        # Verify
        self.assertEqual(extraction_id, 'test-id-123')
        self.assertEqual(status, ExtractionStatus.PROCESSING.value)

        # Check API call
        self.mock_requests.post.assert_called_once()
        call_args = self.mock_requests.post.call_args

        self.assertIn('/v1/extract', call_args[0][0])
        self.assertIn('files', call_args[1])
        self.assertIn('data', call_args[1])

    def test_extract_text_failure(self):
        """Test extraction failure."""
        # Mock failed response
        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad request"
        self.mock_requests.post.return_value = mock_response

        # Test extraction
        extraction_id, status = self.client.extract_text(
            b"content",
            "test.pdf"
        )

        # Verify
        self.assertEqual(extraction_id, "")
        self.assertEqual(status, ExtractionStatus.FAILED.value)

    def test_check_extraction_status_complete(self):
        """Test checking completed extraction status."""
        # Mock status response
        mock_status_response = Mock()
        mock_status_response.status_code = 200
        mock_status_response.json.return_value = {
            'status': 'completed',
            'extraction_id': 'test-id'
        }

        # Mock result response
        mock_result_response = Mock()
        mock_result_response.status_code = 200
        mock_result_response.text = "Extracted text content"

        # Set up session mock
        self.client.session.get = Mock(side_effect=[
            mock_status_response,
            mock_result_response
        ])

        # Test status check
        status, text = self.client.check_extraction_status('test-id')

        # Verify
        self.assertEqual(status, ExtractionStatus.COMPLETE.value)
        self.assertEqual(text, "Extracted text content")

    def test_check_extraction_status_processing(self):
        """Test checking processing extraction status."""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'status': 'processing'
        }
        self.client.session.get = Mock(return_value=mock_response)

        # Test status check
        status, text = self.client.check_extraction_status('test-id')

        # Verify
        self.assertEqual(status, ExtractionStatus.PROCESSING.value)
        self.assertIsNone(text)

    def test_check_extraction_status_failed(self):
        """Test checking failed extraction status."""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'status': 'failed',
            'error': 'Extraction error'
        }
        self.client.session.get = Mock(return_value=mock_response)

        # Test status check
        status, text = self.client.check_extraction_status('test-id')

        # Verify
        self.assertEqual(status, ExtractionStatus.FAILED.value)
        self.assertIsNone(text)

    @patch('time.sleep')
    def test_wait_for_extraction_success(self, mock_sleep):
        """Test waiting for extraction completion."""
        # Mock status checks
        mock_responses = [
            (ExtractionStatus.PROCESSING.value, None),
            (ExtractionStatus.PROCESSING.value, None),
            (ExtractionStatus.COMPLETE.value, "Extracted text")
        ]

        self.client.check_extraction_status = Mock(
            side_effect=mock_responses
        )

        # Test wait
        status, text = self.client.wait_for_extraction(
            'test-id',
            max_wait_seconds=60,
            poll_interval=5
        )

        # Verify
        self.assertEqual(status, ExtractionStatus.COMPLETE.value)
        self.assertEqual(text, "Extracted text")
        self.assertEqual(self.client.check_extraction_status.call_count, 3)

    @patch('time.sleep')
    @patch('time.time')
    def test_wait_for_extraction_timeout(self, mock_time, mock_sleep):
        """Test extraction timeout."""
        # Mock time to simulate timeout
        mock_time.side_effect = [0, 10, 20, 35, 40]  # Exceeds 30 second limit

        self.client.check_extraction_status = Mock(
            return_value=(ExtractionStatus.PROCESSING.value, None)
        )

        # Test wait with short timeout
        status, text = self.client.wait_for_extraction(
            'test-id',
            max_wait_seconds=30,
            poll_interval=5
        )

        # Verify
        self.assertEqual(status, ExtractionStatus.FAILED.value)
        self.assertIsNone(text)

    def test_extract_and_wait(self):
        """Test combined extract and wait."""
        # Mock extraction
        self.client.extract_text = Mock(
            return_value=('test-id', ExtractionStatus.PROCESSING.value)
        )

        # Mock wait
        self.client.wait_for_extraction = Mock(
            return_value=(ExtractionStatus.COMPLETE.value, "Extracted text")
        )

        # Test
        success, text = self.client.extract_and_wait(
            b"content",
            "test.pdf"
        )

        # Verify
        self.assertTrue(success)
        self.assertEqual(text, "Extracted text")

    def test_is_extraction_needed(self):
        """Test checking if extraction is needed."""
        # Files that need extraction
        extractable = [
            'document.pdf',
            'image.png',
            'photo.jpg',
            'scan.tiff',
            'presentation.pptx',
            'spreadsheet.xlsx'
        ]

        for filename in extractable:
            self.assertTrue(
                self.client.is_extraction_needed(filename),
                f"{filename} should need extraction"
            )

        # Files that don't need extraction
        non_extractable = [
            'data.json',
            'script.py',
            'text.txt',
            'config.yml'
        ]

        for filename in non_extractable:
            self.assertFalse(
                self.client.is_extraction_needed(filename),
                f"{filename} should not need extraction"
            )

    def test_get_extraction_config_for_file(self):
        """Test getting extraction config based on file type."""
        # Test PDF config
        pdf_config = self.client.get_extraction_config_for_file('test.pdf')
        self.assertEqual(pdf_config['processing_mode'], 'ocr')
        self.assertTrue(pdf_config['force_text_processing'])

        # Test image config
        img_config = self.client.get_extraction_config_for_file('test.jpg')
        self.assertEqual(img_config['processing_mode'], 'ocr')
        self.assertFalse(img_config['force_text_processing'])

        # Test Word config
        doc_config = self.client.get_extraction_config_for_file('test.docx')
        self.assertEqual(doc_config['processing_mode'], 'text')
        self.assertEqual(doc_config['output_format'], 'markdown')

        # Test Excel config
        xls_config = self.client.get_extraction_config_for_file('test.xlsx')
        self.assertEqual(xls_config['processing_mode'], 'text')
        self.assertEqual(xls_config['line_splitter'], 'paragraph')

    def test_default_config(self):
        """Test default extraction configuration."""
        config = self.client._get_default_config()

        # Verify required fields
        self.assertIn('processing_mode', config)
        self.assertIn('output_format', config)
        self.assertIn('page_separator', config)
        self.assertIn('timeout', config)

        # Verify defaults
        self.assertEqual(config['processing_mode'], 'ocr')
        self.assertEqual(config['output_format'], 'text')
        self.assertEqual(config['timeout'], 300)
