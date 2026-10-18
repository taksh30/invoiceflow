"""IMAP email ingestion source fetching attachments over SSL."""

import email
import email.message
import imaplib
import socket
from collections.abc import Iterator
from email.header import decode_header
from pathlib import Path
from typing import Self

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from invoiceflow.errors import IngestError
from invoiceflow.models import DocumentSource, RawDocument
from invoiceflow.utils.logging import get_logger

logger = get_logger("sources.email_imap")

SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
TRANSIENT_CONNECTION_ERRORS = (
    imaplib.IMAP4.abort,
    OSError,
    socket.error,
    TimeoutError,
    ConnectionError,
)


def decode_mime_header(header_val: str | None) -> str:
    """Decode RFC 2047 encoded email header or filename."""
    if not header_val:
        return ""
    fragments = decode_header(header_val)
    parts: list[str] = []
    for fragment, enc in fragments:
        if isinstance(fragment, bytes):
            parts.append(fragment.decode(enc or "utf-8", errors="replace"))
        else:
            parts.append(str(fragment))
    return "".join(parts)


@retry(
    retry=retry_if_exception_type(TRANSIENT_CONNECTION_ERRORS),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True,
)
def _connect_ssl_with_retry(host: str, port: int) -> imaplib.IMAP4_SSL:
    """Establish SSL IMAP connection with tenacity retries on network errors."""
    return imaplib.IMAP4_SSL(host=host, port=port)


class ImapEmailSource:
    """Monitors an IMAP mailbox over SSL for new invoice email attachments."""

    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        port: int = 993,
        folder: str = "INBOX",
        mark_seen: bool = True,
        seen_uids: set[str] | None = None,
    ) -> None:
        """Initialize IMAP email source with mailbox credentials."""
        self.host = host
        self.user = user
        self.password = password
        self.port = port
        self.folder = folder
        self.mark_seen = mark_seen
        self._seen_uids: set[str] = set(seen_uids or ())
        self._client: imaplib.IMAP4_SSL | None = None

    def connect(self) -> imaplib.IMAP4_SSL:
        """Connect over SSL and authenticate to the IMAP server."""
        if self._client is not None:
            return self._client
        try:
            client = _connect_ssl_with_retry(self.host, self.port)
            client.login(self.user, self.password)
            self._client = client
            logger.info("Connected and logged in to IMAP server", extra={"host": self.host})
            return client
        except imaplib.IMAP4.error as err:
            raise IngestError(
                f"IMAP authentication failed for {self.user}@{self.host}: {err}"
            ) from err
        except Exception as err:
            raise IngestError(f"IMAP connection failed for {self.host}:{self.port}: {err}") from err

    def disconnect(self) -> None:
        """Gracefully logout and close the IMAP session."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            try:
                self._client.logout()
            except Exception:
                pass
            self._client = None

    def __enter__(self) -> Self:
        """Enter context manager, connecting to IMAP server."""
        self.connect()
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        """Exit context manager, disconnecting from IMAP server."""
        self.disconnect()

    def _extract_attachments(self, msg_bytes: bytes, uid: str) -> list[RawDocument]:
        """Parse RFC 822 email message bytes and extract supported file attachments."""
        msg = email.message_from_bytes(msg_bytes)
        documents: list[RawDocument] = []

        for part in msg.walk():
            if part.is_multipart():
                continue

            raw_name = part.get_filename()
            if not raw_name:
                continue

            filename = decode_mime_header(raw_name).strip()
            ext = Path(filename).suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            payload = part.get_payload(decode=True)
            if not isinstance(payload, bytes) or not payload:
                continue

            ref = f"imap://{self.user}@{self.host}/{self.folder}#uid={uid}&file={filename}"
            documents.append(
                RawDocument(
                    content=payload,
                    filename=filename,
                    source=DocumentSource.EMAIL,
                    source_ref=ref,
                )
            )

        return documents

    def _search_unseen_uids(self, client: imaplib.IMAP4_SSL) -> list[str]:
        """Select configured mailbox folder and search for unseen message UIDs."""
        status, _ = client.select(self.folder)
        if status != "OK":
            raise IngestError(f"Failed to select IMAP folder '{self.folder}'")

        status, data = client.uid("SEARCH", "UNSEEN")
        if status != "OK" or not data or not data[0]:
            return []

        uid_list = data[0].decode("ascii", errors="replace").split()
        return [uid for uid in uid_list if uid and uid not in self._seen_uids]

    def _fetch_message_bytes(self, client: imaplib.IMAP4_SSL, uid: str) -> bytes | None:
        """Fetch raw RFC 822 message body for a given message UID."""
        status, data = client.uid("FETCH", uid, "(RFC822)")
        if status != "OK" or not data:
            return None

        for item in data:
            if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
                return item[1]
        return None

    def scan(self) -> Iterator[RawDocument]:
        """Scan IMAP folder for unseen messages and yield extracted attachments."""
        client = self.connect()
        uids = self._search_unseen_uids(client)

        for uid in uids:
            msg_bytes = self._fetch_message_bytes(client, uid)
            if not msg_bytes:
                continue

            docs = self._extract_attachments(msg_bytes, uid)
            yield from docs

            if self.mark_seen:
                client.uid("STORE", uid, "+FLAGS", "(\\Seen)")
            self._seen_uids.add(uid)

    def fetch_documents(self) -> list[RawDocument]:
        """Fetch all attachments from unseen messages as a list."""
        return list(self.scan())
