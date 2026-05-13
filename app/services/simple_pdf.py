import re

LETTER = (612, 792)
LANDSCAPE_LETTER = (792, 612)


def _escape_pdf_text(value):
    text = "" if value is None else str(value)
    text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return text


def _wrap_text(value, max_chars):
    text = re.sub(r"\s+", " ", "" if value is None else str(value)).strip()
    if not text:
        return [""]
    words = text.split(" ")
    lines = []
    line = ""
    for word in words:
        if not line:
            line = word
        elif len(line) + 1 + len(word) <= max_chars:
            line += " " + word
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


class SimplePdf:
    def __init__(self, title="LacksDrivers Document", pagesize=LETTER):
        self.title = title
        self.pagesize = pagesize
        self.pages = []
        self.current = None
        self.width, self.height = pagesize
        self.add_page(pagesize)

    def add_page(self, pagesize=None):
        self.pagesize = pagesize or self.pagesize
        self.width, self.height = self.pagesize
        self.current = []
        self.pages.append((self.width, self.height, self.current))

    def text(self, x, y, value, size=10, bold=False):
        font = "F2" if bold else "F1"
        self.current.append(
            f"BT /{font} {size} Tf {x:.2f} {y:.2f} Td ({_escape_pdf_text(value)}) Tj ET"
        )

    def multiline_text(self, x, y, value, width_chars=40, size=9, leading=11, bold=False, max_lines=3):
        lines = _wrap_text(value, width_chars)[:max_lines]
        for idx, line in enumerate(lines):
            self.text(x, y - (idx * leading), line, size=size, bold=bold)
        return y - (len(lines) * leading)

    def line(self, x1, y1, x2, y2, width=0.5):
        self.current.append(f"{width:.2f} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def rect(self, x, y, w, h, width=0.5):
        self.current.append(f"{width:.2f} w {x:.2f} {y:.2f} {w:.2f} {h:.2f} re S")

    def fill_rect(self, x, y, w, h, gray=0.9):
        self.current.append(f"q {gray:.3f} g {x:.2f} {y:.2f} {w:.2f} {h:.2f} re f Q")

    def table(self, x, y, col_widths, row_height, headers, rows, font_size=8, header_gray=0.9):
        total_width = sum(col_widths)
        self.fill_rect(x, y - row_height, total_width, row_height, header_gray)
        self.rect(x, y - row_height, total_width, row_height)
        cx = x
        for idx, width in enumerate(col_widths):
            self.line(cx, y, cx, y - row_height)
            self.text(cx + 3, y - row_height + 5, headers[idx], size=font_size, bold=True)
            cx += width
        self.line(cx, y, cx, y - row_height)
        y -= row_height
        for row in rows:
            self.rect(x, y - row_height, total_width, row_height)
            cx = x
            for idx, width in enumerate(col_widths):
                self.line(cx, y, cx, y - row_height)
                value = row[idx] if idx < len(row) else ""
                self.multiline_text(cx + 3, y - 11, value, max(6, int(width / 4.6)), size=font_size, leading=9, max_lines=2)
                cx += width
            self.line(cx, y, cx, y - row_height)
            y -= row_height
        return y

    def build(self):
        objects = []
        objects.append("<< /Type /Catalog /Pages 2 0 R >>")
        first_page_obj = 5
        page_refs = " ".join(f"{first_page_obj + i * 2} 0 R" for i in range(len(self.pages)))
        objects.append(f"<< /Type /Pages /Kids [{page_refs}] /Count {len(self.pages)} >>")
        objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
        for index, (width, height, commands) in enumerate(self.pages):
            page_obj = first_page_obj + index * 2
            content_obj = page_obj + 1
            stream = "\n".join(commands)
            page = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width:.2f} {height:.2f}] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_obj} 0 R >>"
            )
            objects.append(page)
            objects.append(f"<< /Length {len(stream.encode('latin-1', 'replace'))} >>\nstream\n{stream}\nendstream")
        pdf = ["%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
        offsets = [0]
        for idx, obj in enumerate(objects, start=1):
            offsets.append(sum(len(part.encode('latin-1', 'replace')) for part in pdf))
            pdf.append(f"{idx} 0 obj\n{obj}\nendobj\n")
        xref_offset = sum(len(part.encode('latin-1', 'replace')) for part in pdf)
        pdf.append(f"xref\n0 {len(objects) + 1}\n")
        pdf.append("0000000000 65535 f \n")
        for offset in offsets[1:]:
            pdf.append(f"{offset:010d} 00000 n \n")
        pdf.append(
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
        )
        return "".join(pdf).encode("latin-1", "replace")
