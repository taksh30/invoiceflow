"""Unit tests for the IMAP email source adapter and attachment extraction."""

import imaplib
from email.message import EmailMessage
from unittest.mock import MagicMock, call, patch

import pytest

from invoiceflow.errors import IngestError
from invoiceflow.models import DocumentSource, RawDocument
from invoiceflow.sources.email_imap import ImapEmailSource, decode_mime_header


def _create_mime_message(
    subject: str = "Invoice attached",
    attachments: list[tuple[str, str, bytes]] | None = None,
) -> bytes:
    """Helper to build a multipart RFC 822 email payload with attachments."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = "billing@vendor.com"
    msg["To"] = "invoices@company.com"
    msg.set_content("Please find your monthly invoice attached.")

    for filename, maintype, content in attachments or []:
        subtype = "pdf" if filename.endswith(".pdf") else "png"
        msg.add_attachment(content, maintype=maintype, subtype=subtype, filename=filename)

    return msg.as_bytes()


def test_decode_mime_header() -> None:
    """Verify decoding of plain, empty, and RFC 2047 encoded email headers."""
    assert decode_mime_header(None) == ""
    assert decode_mime_header("clean_invoice.pdf") == "clean_invoice.pdf"

    # RFC 2047 base64 encoded "invoice_test.pdf"
    encoded = "=?utf-8?b?aW52b2ljZV90ZXN0LnBkZg==?="
    assert decode_mime_header(encoded) == "invoice_test.pdf"


def test_connect_and_disconnect_lifecycle() -> None:
    """Verify SSL connection, authentication, and graceful cleanup."""
    source = ImapEmailSource(
        host="imap.example.com",
        user="testuser",
        password="secretpassword",
        port=993,
    )

    mock_client = MagicMock(spec=imaplib.IMAP4_SSL)

    with patch("imaplib.IMAP4_SSL", return_value=mock_client) as mock_ssl:
        client = source.connect()
        assert client is mock_client
        mock_ssl.assert_called_once_with(host="imap.example.com", port=993)
        mock_client.login.assert_called_once_with("testuser", "secretpassword")

        # Disconnect closes session
        source.disconnect()
        mock_client.close.assert_called_once()
        mock_client.logout.assert_called_once()


def test_context_manager_connects_and_disconnects() -> None:
    """Verify context manager calls connect and disconnect."""
    source = ImapEmailSource(
        host="imap.example.com",
        user="testuser",
        password="secretpassword",
    )
    mock_client = MagicMock(spec=imaplib.IMAP4_SSL)

    with patch("imaplib.IMAP4_SSL", return_value=mock_client):
        with source as src:
            assert src._client is mock_client
        mock_client.logout.assert_called_once()


def test_connect_auth_failure_raises_ingest_error() -> None:
    """Verify IMAP authentication failure raises IngestError."""
    source = ImapEmailSource(
        host="imap.example.com",
        user="testuser",
        password="wrongpassword",
    )
    mock_client = MagicMock(spec=imaplib.IMAP4_SSL)
    mock_client.login.side_effect = imaplib.IMAP4.error("AUTHENTICATIONFAILED")

    match_err = "IMAP authentication failed for testuser@imap.example.com"
    with patch("imaplib.IMAP4_SSL", return_value=mock_client):
        with pytest.raises(IngestError, match=match_err):
            source.connect()


def test_connect_transient_network_error_retried() -> None:
    """Verify tenacity retries on transient network socket errors."""
    source = ImapEmailSource(
        host="imap.example.com",
        user="testuser",
        password="secretpassword",
    )
    mock_client = MagicMock(spec=imaplib.IMAP4_SSL)

    # Fail twice with ConnectionResetError, then succeed
    attempts = [
        ConnectionResetError("Connection reset by peer"),
        ConnectionResetError("Connection reset by peer"),
        mock_client,
    ]

    with patch("imaplib.IMAP4_SSL", side_effect=attempts) as mock_ssl:
        with patch("tenacity.nap.time.sleep", return_value=None):
            client = source.connect()
            assert client is mock_client
            assert mock_ssl.call_count == 3


def test_search_unseen_uids_and_seen_tracking() -> None:
    """Verify selecting folder, searching UNSEEN UIDs, and deduplicating seen UIDs."""
    source = ImapEmailSource(
        host="imap.example.com",
        user="testuser",
        password="secretpassword",
        folder="INBOX",
        seen_uids={"101"},
    )
    mock_client = MagicMock(spec=imaplib.IMAP4_SSL)
    mock_client.select.return_value = ("OK", [b"42"])
    mock_client.uid.return_value = ("OK", [b"101 102 103"])

    uids = source._search_unseen_uids(mock_client)
    mock_client.select.assert_called_once_with("INBOX")
    mock_client.uid.assert_called_once_with("SEARCH", "UNSEEN")
    # 101 was already seen, so only 102 and 103 should be returned
    assert uids == ["102", "103"]


def test_search_unseen_folder_selection_failure() -> None:
    """Verify failure selecting folder raises IngestError."""
    source = ImapEmailSource(
        host="imap.example.com",
        user="testuser",
        password="secretpassword",
        folder="MISSING_FOLDER",
    )
    mock_client = MagicMock(spec=imaplib.IMAP4_SSL)
    mock_client.select.return_value = ("NO", [b"Mailbox doesn't exist"])

    with pytest.raises(IngestError, match="Failed to select IMAP folder 'MISSING_FOLDER'"):
        source._search_unseen_uids(mock_client)


def test_scan_and_extract_supported_attachments() -> None:
    """Verify message fetching, attachment parsing, and setting \\Seen flag."""
    source = ImapEmailSource(
        host="imap.example.com",
        user="billing@company.com",
        password="password",
        mark_seen=True,
    )

    pdf_bytes = b"%PDF-1.4 sample pdf content"
    png_bytes = b"\x89PNG\r\n\x1a\n sample png content"
    txt_bytes = b"sample text ignored"

    raw_email = _create_mime_message(
        attachments=[
            ("invoice.pdf", "application", pdf_bytes),
            ("receipt.png", "image", png_bytes),
            ("notes.txt", "text", txt_bytes),
        ]
    )

    mock_client = MagicMock(spec=imaplib.IMAP4_SSL)
    mock_client.select.return_value = ("OK", [b"1"])
    mock_client.uid.side_effect = [
        ("OK", [b"501"]),  # UID SEARCH UNSEEN
        ("OK", [(b"501 (RFC822)", raw_email)]),  # UID FETCH 501
        ("OK", [b"STORE"]),  # UID STORE 501 +FLAGS (\Seen)
    ]

    with patch.object(source, "connect", return_value=mock_client):
        docs = list(source.scan())

    assert len(docs) == 2
    assert isinstance(docs[0], RawDocument)
    assert docs[0].filename == "invoice.pdf"
    assert docs[0].content == pdf_bytes
    assert docs[0].source == DocumentSource.EMAIL
    assert "uid=501" in docs[0].source_ref

    assert docs[1].filename == "receipt.png"
    assert docs[1].content == png_bytes
    assert docs[1].source == DocumentSource.EMAIL

    # Assert \Seen flag was set and UID tracked
    mock_client.uid.assert_has_calls([call("STORE", "501", "+FLAGS", "(\\Seen)")])
    assert "501" in source._seen_uids


def test_fetch_documents_convenience_method() -> None:
    """Verify fetch_documents returns a list from scan generator."""
    source = ImapEmailSource(
        host="imap.example.com",
        user="testuser",
        password="secretpassword",
    )
    with patch.object(source, "scan", return_value=iter([])):
        docs = source.fetch_documents()
        assert docs == []
