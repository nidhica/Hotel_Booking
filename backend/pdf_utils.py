def _escape_pdf_text(value):
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )


def build_invoice_pdf(lines):
    content_lines = ["BT", "/F1 12 Tf", "40 800 Td", "16 TL"]
    first = True

    for line in lines:
        escaped = _escape_pdf_text(line)
        if first:
            content_lines.append(f"({_escape_pdf_text(line)}) Tj")
            first = False
        else:
            content_lines.append("T*")
            content_lines.append(f"({escaped}) Tj")

    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", "replace")

    objects = []
    objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
    objects.append(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
    objects.append(
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n"
    )
    objects.append(b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")
    objects.append(
        f"5 0 obj << /Length {len(stream)} >> stream\n".encode("latin-1")
        + stream
        + b"\nendstream endobj\n"
    )

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)

    xref_position = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode("latin-1"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))

    pdf.extend(
        (
            f"trailer << /Size {len(offsets)} /Root 1 0 R >>\n"
            f"startxref\n{xref_position}\n%%EOF"
        ).encode("latin-1")
    )
    return bytes(pdf)
