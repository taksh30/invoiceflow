"""Generate 30 synthetic benchmark invoice and receipt fixtures with expected ground truth JSON."""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FIXTURES_DIR = Path("tests/fixtures/invoices")
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)


def create_text_pdf(path: Path, lines: list[str]) -> None:
    """Generate a valid single-page digital text PDF using raw PDF stream syntax."""
    stream_content = ["BT", "/F1 12 Tf", "50 720 Td"]
    for idx, line in enumerate(lines):
        clean = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        if idx > 0:
            stream_content.append(f"0 -22 Td ({clean}) Tj")
        else:
            stream_content.append(f"({clean}) Tj")
    stream_content.append("ET")
    stream_bytes = "\n".join(stream_content).encode("utf-8")

    pdf_body = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /Resources 4 0 R "
        b"/MediaBox [0 0 612 792] /Contents 5 0 R >> endobj\n"
        b"4 0 obj << /Font << /F1 << /Type /Font /Subtype /Type1 "
        b"/BaseFont /Helvetica >> >> >> endobj\n"
        b"5 0 obj << /Length "
        + str(len(stream_bytes)).encode("ascii")
        + b" >> stream\n"
        + stream_bytes
        + b"\nendstream\nendobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000222 00000 n \n"
        b"0000000309 00000 n \n"
        b"trailer << /Size 6 /Root 1 0 R >>\n"
        b"startxref\n" + str(330 + len(stream_bytes)).encode("ascii") + b"\n%%EOF\n"
    )
    path.write_bytes(pdf_body)


def create_raster_file(path: Path, lines: list[str], is_pdf: bool = False) -> None:
    """Generate an image or raster PDF without digital text layer."""
    font = ImageFont.load_default(size=20)
    img = Image.new("RGB", (800, 600), color="white")
    draw = ImageDraw.Draw(img)
    y = 40
    for line in lines:
        draw.text((40, y), line, fill="black", font=font)
        y += 36

    if is_pdf:
        img.save(path, "PDF")
    elif path.suffix.lower() == ".jpg" or path.suffix.lower() == ".jpeg":
        img.save(path, "JPEG")
    else:
        img.save(path, "PNG")


def main() -> None:
    """Generate 30 benchmark fixtures."""
    indian_samples = [
        (
            "Reliance Retail Ltd",
            "27AAACR1234F1Z5",
            "INV/2024/001",
            "15/05/2024",
            "2024-05-15",
            "INR",
            "1000.00",
            "180.00",
            "1180.00",
            "pdf",
        ),
        (
            "Tata Consultancy Services",
            "27AAACT2727Q1ZW",
            "TCS-9942",
            "12/04/2024",
            "2024-04-12",
            "INR",
            "50000.00",
            "9000.00",
            "59000.00",
            "pdf",
        ),
        (
            "Infosys Limited",
            "29AAACI4567M1ZV",
            "INF-2024-10",
            "20/05/2024",
            "2024-05-20",
            "INR",
            "25000.00",
            "4500.00",
            "29500.00",
            "pdf",
        ),
        (
            "Flipkart Internet Pvt Ltd",
            "29AAACF9988G1Z1",
            "FK-88310",
            "02/06/2024",
            "2024-06-02",
            "INR",
            "1500.00",
            "270.00",
            "1770.00",
            "pdf",
        ),
        (
            "Zomato Limited",
            "07AAACZ1122K1Z9",
            "ZOM-4512",
            "18/05/2024",
            "2024-05-18",
            "INR",
            "450.00",
            "22.50",
            "472.50",
            "pdf",
        ),
        (
            "Swiggy India",
            "29AABCS8899D1Z3",
            "SWG-1102",
            "22/05/2024",
            "2024-05-22",
            "INR",
            "600.00",
            "30.00",
            "630.00",
            "pdf",
        ),
        (
            "Bharti Airtel Ltd",
            "07AAACB2233N1Z8",
            "AIR-7741",
            "05/06/2024",
            "2024-06-05",
            "INR",
            "999.00",
            "179.82",
            "1178.82",
            "pdf",
        ),
        (
            "HDFC Bank Ltd",
            "27AAACH1111Q1Z2",
            "HDFC-332",
            "01/05/2024",
            "2024-05-01",
            "INR",
            "2000.00",
            "360.00",
            "2360.00",
            "pdf",
        ),
        (
            "Wipro Enterprises",
            "29AAACW5566L1Z4",
            "WIP-5541",
            "10/05/2024",
            "2024-05-10",
            "INR",
            "12000.00",
            "2160.00",
            "14160.00",
            "pdf",
        ),
        (
            "Larsen & Toubro Ltd",
            "27AAACL3344R1Z7",
            "LT-9921",
            "28/05/2024",
            "2024-05-28",
            "INR",
            "85000.00",
            "15300.00",
            "100300.00",
            "pdf",
        ),
        (
            "Adani Enterprises",
            "24AAACA5555M1Z6",
            "AD-1002",
            "14/05/2024",
            "2024-05-14",
            "INR",
            "32000.00",
            "5760.00",
            "37760.00",
            "scanned_pdf",
        ),
        (
            "ITC Limited",
            "19AAACI2222E1Z5",
            "ITC-881",
            "19/05/2024",
            "2024-05-19",
            "INR",
            "4200.00",
            "756.00",
            "4956.00",
            "scanned_pdf",
        ),
        (
            "Titan Company Ltd",
            "29AAACT9999M1Z0",
            "TTN-4412",
            "21/05/2024",
            "2024-05-21",
            "INR",
            "15400.00",
            "462.00",
            "15862.00",
            "png",
        ),
        (
            "Asian Paints Ltd",
            "27AAACA1212P1Z9",
            "AP-7731",
            "27/05/2024",
            "2024-05-27",
            "INR",
            "8900.00",
            "1602.00",
            "10502.00",
            "png",
        ),
        (
            "Bajaj Auto Ltd",
            "27AAACB3333F1Z1",
            "BAJ-6651",
            "30/05/2024",
            "2024-05-30",
            "INR",
            "65000.00",
            "18200.00",
            "83200.00",
            "jpg",
        ),
    ]

    us_samples = [
        (
            "Amazon Web Services Inc",
            None,
            "AWS-99120",
            "05/10/2024",
            "2024-05-10",
            "USD",
            "150.00",
            "12.00",
            "162.00",
            "pdf",
        ),
        (
            "Google LLC",
            None,
            "GGL-4410",
            "05/15/2024",
            "2024-05-15",
            "USD",
            "500.00",
            "40.00",
            "540.00",
            "pdf",
        ),
        (
            "Microsoft Corporation",
            None,
            "MSFT-883",
            "05/01/2024",
            "2024-05-01",
            "USD",
            "1200.00",
            "96.00",
            "1296.00",
            "pdf",
        ),
        (
            "Stripe Inc",
            None,
            "STR-2210",
            "05/18/2024",
            "2024-05-18",
            "USD",
            "75.00",
            "0.00",
            "75.00",
            "pdf",
        ),
        (
            "Adobe Systems",
            None,
            "ADB-7741",
            "05/22/2024",
            "2024-05-22",
            "USD",
            "52.99",
            "4.24",
            "57.23",
            "pdf",
        ),
        (
            "Slack Technologies",
            None,
            "SLK-3310",
            "05/25/2024",
            "2024-05-25",
            "USD",
            "120.00",
            "9.60",
            "129.60",
            "pdf",
        ),
        (
            "GitHub Inc",
            None,
            "GH-55410",
            "05/28/2024",
            "2024-05-28",
            "USD",
            "21.00",
            "0.00",
            "21.00",
            "pdf",
        ),
        (
            "Zoom Video Communications",
            None,
            "ZM-8891",
            "06/01/2024",
            "2024-06-01",
            "USD",
            "149.90",
            "11.99",
            "161.89",
            "pdf",
        ),
        (
            "Twilio Inc",
            None,
            "TW-1140",
            "05/05/2024",
            "2024-05-05",
            "USD",
            "85.50",
            "6.84",
            "92.34",
            "png",
        ),
        (
            "DigitalOcean LLC",
            None,
            "DO-9941",
            "05/12/2024",
            "2024-05-12",
            "USD",
            "48.00",
            "3.84",
            "51.84",
            "jpg",
        ),
    ]

    eu_samples = [
        (
            "SAP SE",
            "DE123456789",
            "SAP-4410",
            "10.05.2024",
            "2024-05-10",
            "EUR",
            "2500.00",
            "475.00",
            "2975.00",
            "pdf",
        ),
        (
            "Spotify AB",
            "SE556703748501",
            "SPOT-992",
            "15.05.2024",
            "2024-05-15",
            "EUR",
            "9.99",
            "2.00",
            "11.99",
            "pdf",
        ),
        (
            "Siemens AG",
            "DE987654321",
            "SIE-1102",
            "20.05.2024",
            "2024-05-20",
            "EUR",
            "18500.00",
            "3515.00",
            "22015.00",
            "pdf",
        ),
        (
            "Airbus SE",
            "NL809564288B01",
            "AIR-8841",
            "25.05.2024",
            "2024-05-25",
            "EUR",
            "45000.00",
            "8550.00",
            "53550.00",
            "pdf",
        ),
        (
            "Schneider Electric",
            "FR12345678901",
            "SCH-662",
            "28.05.2024",
            "2024-05-28",
            "EUR",
            "3200.00",
            "640.00",
            "3840.00",
            "scanned_pdf",
        ),
    ]

    all_specs = [
        ("in", indian_samples),
        ("us", us_samples),
        ("eu", eu_samples),
    ]

    count = 0
    for prefix, group in all_specs:
        for idx, item in enumerate(group, start=1):
            vendor, tax_id, inv_no, date_str, iso_date, curr, subtotal, tax, total, ftype = item
            count += 1
            filename_base = f"inv_{prefix}_{idx:02d}"

            lines = [
                vendor,
                f"TAX ID: {tax_id}" if tax_id else "",
                f"Invoice No: {inv_no}",
                f"Invoice Date: {date_str}",
                f"Currency: {curr}",
                f"Subtotal: {subtotal}",
                f"Tax: {tax}",
                f"Grand Total: {total}",
            ]
            lines = [line_item for line_item in lines if line_item]

            expected = {
                "vendor_name": vendor,
                "invoice_number": inv_no,
                "invoice_date": iso_date,
                "currency": curr,
                "subtotal": subtotal,
                "tax_total": tax,
                "total": total,
                "vendor_tax_id": tax_id,
            }

            if ftype == "pdf":
                file_path = FIXTURES_DIR / f"{filename_base}.pdf"
                create_text_pdf(file_path, lines)
            elif ftype == "scanned_pdf":
                file_path = FIXTURES_DIR / f"{filename_base}.pdf"
                create_raster_file(file_path, lines, is_pdf=True)
            elif ftype == "png":
                file_path = FIXTURES_DIR / f"{filename_base}.png"
                create_raster_file(file_path, lines, is_pdf=False)
            elif ftype == "jpg":
                file_path = FIXTURES_DIR / f"{filename_base}.jpg"
                create_raster_file(file_path, lines, is_pdf=False)

            json_path = FIXTURES_DIR / f"{filename_base}.expected.json"
            json_path.write_text(json.dumps(expected, indent=2), encoding="utf-8")

    print(f"Generated {count} benchmark fixture files and expected JSONs.")


if __name__ == "__main__":
    main()
