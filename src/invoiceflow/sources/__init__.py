"""Ingestion source adapters for folders and email."""

from invoiceflow.sources.email_imap import ImapEmailSource
from invoiceflow.sources.folder import SUPPORTED_EXTENSIONS, FolderSource

__all__ = ["FolderSource", "ImapEmailSource", "SUPPORTED_EXTENSIONS"]
