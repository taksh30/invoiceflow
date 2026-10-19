"""HTML and HTMX template components for the InvoiceFlow review interface."""

import html

from invoiceflow.db.tables import DocumentRow, InvoiceRow


def _base_html(title: str, body_content: str) -> str:
    """Wrap body content in a modern HTML layout with embedded HTMX and styling."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{html.escape(title)} - InvoiceFlow Review</title>
    <script src="https://unpkg.com/htmx.org@1.9.12"></script>
    <style>
        :root {{
            --bg: #0f172a;
            --surface: #1e293b;
            --border: #334155;
            --text: #f8fafc;
            --text-muted: #94a3b8;
            --primary: #3b82f6;
            --primary-hover: #2563eb;
            --accent: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: var(--bg);
            color: var(--text);
            line-height: 1.5;
            min-height: 100vh;
        }}
        header {{
            background-color: var(--surface);
            border-bottom: 1px solid var(--border);
            padding: 1rem 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        header h1 a {{
            color: var(--text);
            text-decoration: none;
            font-size: 1.25rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        .badge {{
            display: inline-block;
            padding: 0.25rem 0.5rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
        }}
        .badge-warning {{
            background-color: rgba(245, 158, 11, 0.2);
            color: #fbbf24;
            border: 1px solid rgba(245, 158, 11, 0.4);
        }}
        .badge-success {{
            background-color: rgba(16, 185, 129, 0.2);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.4);
        }}
        .badge-info {{
            background-color: rgba(59, 130, 246, 0.2);
            color: #60a5fa;
            border: 1px solid rgba(59, 130, 246, 0.4);
        }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 2rem; }}
        .table-card {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            overflow: hidden;
        }}
        table {{ width: 100%; border-collapse: collapse; text-align: left; }}
        th, td {{
            padding: 0.85rem 1.25rem;
            border-bottom: 1px solid var(--border);
            font-size: 0.9rem;
        }}
        th {{ background: rgba(0,0,0,0.2); color: var(--text-muted); font-weight: 600; }}
        tr:hover {{ background: rgba(255,255,255,0.02); }}
        .btn {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0.5rem 1rem;
            background-color: var(--primary);
            color: white;
            text-decoration: none;
            border-radius: 6px;
            font-size: 0.875rem;
            font-weight: 500;
            border: none;
            cursor: pointer;
            transition: background 0.15s;
        }}
        .btn:hover {{ background-color: var(--primary-hover); }}
        .btn-success {{ background-color: var(--accent); }}
        .btn-success:hover {{ background-color: #059669; }}
        .split-view {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5rem;
            height: calc(100vh - 120px);
            padding: 1.5rem 2rem;
        }}
        .viewer-pane, .form-pane {{
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 8px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }}
        .pane-header {{
            padding: 0.75rem 1.25rem;
            background: rgba(0,0,0,0.2);
            border-bottom: 1px solid var(--border);
            font-weight: 600;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .viewer-content {{ flex: 1; width: 100%; height: 100%; }}
        .form-content {{ padding: 1.5rem; overflow-y: auto; flex: 1; }}
        .form-group {{ margin-bottom: 1rem; }}
        .form-group label {{
            display: block;
            font-size: 0.8rem;
            font-weight: 600;
            color: var(--text-muted);
            margin-bottom: 0.35rem;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .form-control {{
            width: 100%;
            padding: 0.65rem 0.85rem;
            background-color: rgba(15, 23, 42, 0.6);
            border: 1px solid var(--border);
            border-radius: 6px;
            color: var(--text);
            font-size: 0.95rem;
            outline: none;
        }}
        .form-control:focus {{ border-color: var(--primary); }}
        .form-grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
        .form-grid-3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem; }}
        .checkbox-label {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            cursor: pointer;
            font-size: 0.875rem;
            margin-top: 0.5rem;
        }}
        .toast {{
            padding: 1rem;
            border-radius: 6px;
            background: rgba(16, 185, 129, 0.15);
            border: 1px solid var(--accent);
            color: #34d399;
            margin-bottom: 1rem;
        }}
    </style>
</head>
<body>
    <header>
        <h1><a href="/">🧾 InvoiceFlow <span class="badge badge-warning">Review</span></a></h1>
        <div>
            <a href="/" class="btn" style="background:transparent; border:1px solid var(--border);">
                Queue
            </a>
        </div>
    </header>
    <main>
        {body_content}
    </main>
</body>
</html>
"""


def render_review_queue_page(items: list[tuple[DocumentRow, InvoiceRow | None]]) -> str:
    """Render table of documents pending human review."""
    rows_html: list[str] = []
    if not items:
        rows_html.append(
            '<tr><td colspan="7" style="text-align: center; padding: 3rem; '
            'color: var(--text-muted);">'
            "🎉 No invoices currently require review! All documents are processed.</td></tr>"
        )
    for doc, inv in items:
        vendor = html.escape(inv.vendor_name if inv else "Unidentified")
        total = f"{inv.currency} {inv.total:.2f}" if inv else "-"
        conf = f"{inv.overall_confidence:.0%}" if inv else "0%"
        reason = html.escape(doc.error or "Low confidence / arithmetic mismatch")
        rows_html.append(
            f"""<tr>
                <td><strong>#{doc.id}</strong></td>
                <td>{html.escape(doc.original_name)}</td>
                <td>{vendor}</td>
                <td>{total}</td>
                <td><span class="badge badge-warning">{conf}</span></td>
                <td style="color: var(--text-muted); font-size: 0.85rem;">{reason}</td>
                <td><a href="/review/{doc.id}" class="btn">Review Document</a></td>
            </tr>"""
        )

    content = f"""
    <div class="container">
        <div style="margin-bottom: 1.5rem; display: flex; justify-content: space-between;">
            <div>
                <h2 style="font-size: 1.5rem; font-weight: 700;">Human Review Queue</h2>
                <p style="color: var(--text-muted); font-size: 0.9rem;">
                    Invoices flagged due to confidence &lt; 0.60 or arithmetic discrepancies.
                </p>
            </div>
            <span class="badge badge-warning" style="font-size: 0.9rem; padding: 0.4rem 0.8rem;">
                {len(items)} Items Pending
            </span>
        </div>
        <div class="table-card">
            <table>
                <thead>
                    <tr>
                        <th>Doc ID</th>
                        <th>Original File</th>
                        <th>Identified Vendor</th>
                        <th>Total Amount</th>
                        <th>Confidence</th>
                        <th>Flag Reason</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(rows_html)}
                </tbody>
            </table>
        </div>
    </div>
    """
    return _base_html("Review Queue", content)


def render_review_workspace(
    doc: DocumentRow,
    inv: InvoiceRow | None,
    raw_url: str,
) -> str:
    """Render side-by-side view with document viewer and editable correction form."""
    is_pdf = doc.original_name.lower().endswith(".pdf")
    if is_pdf:
        viewer_embed = (
            f'<iframe src="{raw_url}" class="viewer-content" style="border: none;"></iframe>'
        )
    else:
        viewer_embed = (
            f'<div style="overflow:auto; height:100%; display:flex; justify-content:center; '
            f'padding:1rem;"><img src="{raw_url}" style="max-width:100%; max-height:100%; '
            f'object-fit:contain;" alt="Invoice Image" /></div>'
        )

    vendor = html.escape(inv.vendor_name if inv else "")
    tax_id = html.escape(inv.vendor_tax_id or "") if inv else ""
    inv_num = html.escape(inv.invoice_number or "") if inv else ""
    inv_date = str(inv.invoice_date) if inv and inv.invoice_date else ""
    currency = html.escape(inv.currency if inv else "INR")
    total = f"{inv.total:.2f}" if inv else "0.00"
    subtotal = f"{inv.subtotal:.2f}" if inv and inv.subtotal is not None else ""
    tax_total = f"{inv.tax_total:.2f}" if inv and inv.tax_total is not None else ""
    cgst = f"{inv.cgst:.2f}" if inv and inv.cgst is not None else ""
    sgst = f"{inv.sgst:.2f}" if inv and inv.sgst is not None else ""
    igst = f"{inv.igst:.2f}" if inv and inv.igst is not None else ""

    reasons_badge = ""
    if doc.error:
        reasons_badge = (
            f'<div style="margin-bottom:1rem; padding:0.75rem; background:rgba(239,68,68,0.1); '
            f"border:1px solid rgba(239,68,68,0.3); border-radius:6px; color:#f87171; "
            f'font-size:0.85rem;"><strong>Review Flags:</strong> {html.escape(doc.error)}</div>'
        )

    content = f"""
    <div class="split-view">
        <div class="viewer-pane">
            <div class="pane-header">
                <span>📄 Source Document: {html.escape(doc.original_name)}</span>
                <a href="{raw_url}" target="_blank" class="badge badge-info"
                   style="text-decoration:none;">Open in Tab ↗</a>
            </div>
            {viewer_embed}
        </div>
        <div class="form-pane">
            <div class="pane-header">
                <span>✍️ Correct Invoice Fields</span>
                <span class="badge badge-warning">Doc #{doc.id}</span>
            </div>
            <div class="form-content">
                <div id="form-feedback"></div>
                {reasons_badge}
                <form hx-post="/review/{doc.id}/save" hx-target="#form-feedback"
                      hx-swap="innerHTML">
                    <div class="form-group">
                        <label for="vendor_name">Vendor Legal Name *</label>
                        <input type="text" id="vendor_name" name="vendor_name"
                               value="{vendor}" required class="form-control" />
                    </div>
                    <div class="form-grid-2">
                        <div class="form-group">
                            <label for="vendor_tax_id">Tax ID / GSTIN / VAT</label>
                            <input type="text" id="vendor_tax_id" name="vendor_tax_id"
                                   value="{tax_id}" class="form-control" />
                        </div>
                        <div class="form-group">
                            <label for="invoice_number">Invoice / Bill Number</label>
                            <input type="text" id="invoice_number" name="invoice_number"
                                   value="{inv_num}" class="form-control" />
                        </div>
                    </div>
                    <div class="form-grid-2">
                        <div class="form-group">
                            <label for="invoice_date">Invoice Date (YYYY-MM-DD)</label>
                            <input type="date" id="invoice_date" name="invoice_date"
                                   value="{inv_date}" class="form-control" />
                        </div>
                        <div class="form-group">
                            <label for="currency">Currency (3-Letter ISO)</label>
                            <input type="text" id="currency" name="currency"
                                   value="{currency}" maxlength="3" class="form-control" />
                        </div>
                    </div>
                    <div class="form-grid-2">
                        <div class="form-group">
                            <label for="subtotal">Subtotal (Net)</label>
                            <input type="number" step="0.01" id="subtotal" name="subtotal"
                                   value="{subtotal}" class="form-control" />
                        </div>
                        <div class="form-group">
                            <label for="tax_total">Total Tax</label>
                            <input type="number" step="0.01" id="tax_total" name="tax_total"
                                   value="{tax_total}" class="form-control" />
                        </div>
                    </div>
                    <div class="form-grid-3">
                        <div class="form-group">
                            <label for="cgst">CGST</label>
                            <input type="number" step="0.01" id="cgst" name="cgst"
                                   value="{cgst}" class="form-control" />
                        </div>
                        <div class="form-group">
                            <label for="sgst">SGST</label>
                            <input type="number" step="0.01" id="sgst" name="sgst"
                                   value="{sgst}" class="form-control" />
                        </div>
                        <div class="form-group">
                            <label for="igst">IGST</label>
                            <input type="number" step="0.01" id="igst" name="igst"
                                   value="{igst}" class="form-control" />
                        </div>
                    </div>
                    <div class="form-group">
                        <label for="total" style="color: #60a5fa; font-size: 0.9rem;">
                            Grand Total *
                        </label>
                        <input type="number" step="0.01" id="total" name="total"
                               value="{total}" required class="form-control"
                               style="font-weight:700; font-size:1.1rem;" />
                    </div>
                    <div class="form-group">
                        <label class="checkbox-label">
                            <input type="checkbox" name="save_as_rule" value="true" checked />
                            <span>Save corrections as extraction training example / rule</span>
                        </label>
                    </div>
                    <div style="margin-top: 1.5rem; display: flex; gap: 1rem;">
                        <button type="submit" class="btn btn-success"
                                style="flex: 1; padding: 0.75rem;">
                            ✓ Save &amp; Promote to Processed
                        </button>
                        <a href="/" class="btn"
                           style="background: transparent; border: 1px solid var(--border);">
                            Back
                        </a>
                    </div>
                </form>
            </div>
        </div>
    </div>
    """
    return _base_html(f"Review #{doc.id}", content)


def render_save_success_toast(doc_id: int) -> str:
    """Render HTMX inline success feedback after saving corrections."""
    return f"""
    <div class="toast">
        <strong>Success!</strong> Invoice #{doc_id} corrections saved, document promoted
        to <code>processed</code>, and training example stored.
        <div style="margin-top: 0.5rem;">
            <a href="/" style="color: white; text-decoration: underline; font-weight: 600;">
                Return to Review Queue &rarr;
            </a>
        </div>
    </div>
    """
