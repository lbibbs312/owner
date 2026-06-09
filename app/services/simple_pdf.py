import base64
import binascii
import re
import struct
import zlib

LETTER = (612, 792)
LANDSCAPE_LETTER = (792, 612)


def _escape_pdf_text(value):
    text = "" if value is None else str(value)
    text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return text


def _normalize_rgb(color):
    if color is None:
        return None
    red, green, blue = color
    values = [float(red), float(green), float(blue)]
    if any(value > 1 for value in values):
        values = [value / 255 for value in values]
    values = [min(1, max(0, value)) for value in values]
    return " ".join(f"{value:.3f}" for value in values)


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


def _paeth_predictor(left, up, up_left):
    estimate = left + up - up_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    up_left_distance = abs(estimate - up_left)
    if left_distance <= up_distance and left_distance <= up_left_distance:
        return left
    if up_distance <= up_left_distance:
        return up
    return up_left


def _png_data_url_to_rgb(data_url):
    if not data_url or not str(data_url).startswith("data:image/png;base64,"):
        return None
    try:
        png = base64.b64decode(str(data_url).split(",", 1)[1], validate=True)
    except (binascii.Error, ValueError):
        return None

    if not png.startswith(b"\x89PNG\r\n\x1a\n"):
        return None

    offset = 8
    width = height = bit_depth = color_type = compression = filter_method = interlace = None
    idat_parts = []
    while offset + 8 <= len(png):
        chunk_len = struct.unpack(">I", png[offset : offset + 4])[0]
        chunk_type = png[offset + 4 : offset + 8]
        chunk_data = png[offset + 8 : offset + 8 + chunk_len]
        offset += 12 + chunk_len
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
                ">IIBBBBB", chunk_data
            )
        elif chunk_type == b"IDAT":
            idat_parts.append(chunk_data)
        elif chunk_type == b"IEND":
            break

    channel_counts = {0: 1, 2: 3, 4: 2, 6: 4}
    channels = channel_counts.get(color_type)
    if (
        not width
        or not height
        or bit_depth != 8
        or compression != 0
        or filter_method != 0
        or interlace != 0
        or channels is None
        or not idat_parts
    ):
        return None

    try:
        raw = zlib.decompress(b"".join(idat_parts))
    except zlib.error:
        return None

    stride = width * channels
    rows = []
    pos = 0
    prev = bytearray(stride)
    for _ in range(height):
        if pos >= len(raw):
            return None
        filter_type = raw[pos]
        pos += 1
        row = bytearray(raw[pos : pos + stride])
        pos += stride
        if len(row) != stride:
            return None
        for idx in range(stride):
            left = row[idx - channels] if idx >= channels else 0
            up = prev[idx]
            up_left = prev[idx - channels] if idx >= channels else 0
            if filter_type == 1:
                row[idx] = (row[idx] + left) & 0xFF
            elif filter_type == 2:
                row[idx] = (row[idx] + up) & 0xFF
            elif filter_type == 3:
                row[idx] = (row[idx] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                row[idx] = (row[idx] + _paeth_predictor(left, up, up_left)) & 0xFF
            elif filter_type != 0:
                return None
        rows.append(bytes(row))
        prev = row

    rgb = bytearray()
    for row in rows:
        for px in range(0, len(row), channels):
            if color_type == 0:
                gray = row[px]
                rgb.extend((gray, gray, gray))
            elif color_type == 2:
                rgb.extend(row[px : px + 3])
            elif color_type == 4:
                gray, alpha = row[px], row[px + 1]
                blended = ((gray * alpha) + (255 * (255 - alpha))) // 255
                rgb.extend((blended, blended, blended))
            elif color_type == 6:
                red, green, blue, alpha = row[px : px + 4]
                rgb.extend(
                    (
                        ((red * alpha) + (255 * (255 - alpha))) // 255,
                        ((green * alpha) + (255 * (255 - alpha))) // 255,
                        ((blue * alpha) + (255 * (255 - alpha))) // 255,
                    )
                )
    return width, height, bytes(rgb)


def _jpeg_dimensions(jpeg_bytes):
    if not jpeg_bytes.startswith(b"\xff\xd8"):
        return None
    pos = 2
    sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
    while pos + 4 < len(jpeg_bytes):
        if jpeg_bytes[pos] != 0xFF:
            pos += 1
            continue
        while pos < len(jpeg_bytes) and jpeg_bytes[pos] == 0xFF:
            pos += 1
        if pos >= len(jpeg_bytes):
            break
        marker = jpeg_bytes[pos]
        pos += 1
        if marker in {0xD8, 0xD9}:
            continue
        if marker == 0xDA or pos + 2 > len(jpeg_bytes):
            break
        segment_len = struct.unpack(">H", jpeg_bytes[pos : pos + 2])[0]
        if segment_len < 2 or pos + segment_len > len(jpeg_bytes):
            break
        if marker in sof_markers and segment_len >= 7:
            height = struct.unpack(">H", jpeg_bytes[pos + 3 : pos + 5])[0]
            width = struct.unpack(">H", jpeg_bytes[pos + 5 : pos + 7])[0]
            components = jpeg_bytes[pos + 7] if pos + 7 < len(jpeg_bytes) else 3
            if width and height and components in {1, 3}:
                return width, height, "/DeviceGray" if components == 1 else "/DeviceRGB"
            return None
        pos += segment_len
    return None


def _image_dimensions(image_bytes):
    """Return (width, height) in pixels for a PNG or baseline JPEG, else None."""
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        if len(image_bytes) >= 24:
            width, height = struct.unpack(">II", image_bytes[16:24])
            if width and height:
                return width, height
        return None
    jpeg = _jpeg_dimensions(image_bytes)
    if jpeg:
        return jpeg[0], jpeg[1]
    return None


class SimplePdf:
    def __init__(self, title="MoveDefense Document", pagesize=LETTER):
        self.title = title
        self.pagesize = pagesize
        self.pages = []
        self.current = None
        self.images = []
        self.width, self.height = pagesize
        self.add_page(pagesize)

    def add_page(self, pagesize=None):
        self.pagesize = pagesize or self.pagesize
        self.width, self.height = self.pagesize
        self.current = []
        self.pages.append((self.width, self.height, self.current))

    def text(self, x, y, value, size=10, bold=False, color=None, font=None):
        if font == "signature":
            font_ref = "F3"
        else:
            font_ref = "F2" if bold else "F1"
        command = f"BT /{font_ref} {size} Tf {x:.2f} {y:.2f} Td ({_escape_pdf_text(value)}) Tj ET"
        rgb = _normalize_rgb(color)
        if rgb:
            command = f"q {rgb} rg {command} Q"
        self.current.append(command)

    def brand_signature(self, x=None, y=None):
        x = self.width - 158 if x is None else x
        y = self.height - 28 if y is None else y
        self.text(x, y, "MOVEDEFENSE", size=12, bold=True, color=(31, 78, 163))

    def multiline_text(
        self, x, y, value, width_chars=40, size=9, leading=11, bold=False, max_lines=3, color=None
    ):
        lines = _wrap_text(value, width_chars)[:max_lines]
        for idx, line in enumerate(lines):
            self.text(x, y - (idx * leading), line, size=size, bold=bold, color=color)
        return y - (len(lines) * leading)

    def line(self, x1, y1, x2, y2, width=0.5):
        self.current.append(f"{width:.2f} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S")

    def rect(self, x, y, w, h, width=0.5):
        self.current.append(f"{width:.2f} w {x:.2f} {y:.2f} {w:.2f} {h:.2f} re S")

    def fill_rect(self, x, y, w, h, gray=0.9):
        self.current.append(f"q {gray:.3f} g {x:.2f} {y:.2f} {w:.2f} {h:.2f} re f Q")


    def image_png_data_url(self, data_url, x, y, w, h):
        parsed = _png_data_url_to_rgb(data_url)
        if parsed is None:
            return False
        image_width, image_height, rgb_bytes = parsed
        name = f"Im{len(self.images) + 1}"
        self.images.append(
            {
                "name": name,
                "width": image_width,
                "height": image_height,
                "color_space": "/DeviceRGB",
                "filter": "/FlateDecode",
                "stream": zlib.compress(rgb_bytes),
            }
        )
        self.current.append(f"q {w:.2f} 0 0 {h:.2f} {x:.2f} {y:.2f} cm /{name} Do Q")
        return True

    def image_file(self, path, x, y, w, h):
        try:
            with open(path, "rb") as fh:
                image_bytes = fh.read()
        except OSError:
            return False
        if image_bytes.startswith(b"\x89PNG"):
            data_url = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
            return self.image_png_data_url(data_url, x, y, w, h)
        jpeg = _jpeg_dimensions(image_bytes)
        if jpeg is None:
            return False
        image_width, image_height, color_space = jpeg
        name = f"Im{len(self.images) + 1}"
        self.images.append(
            {
                "name": name,
                "width": image_width,
                "height": image_height,
                "color_space": color_space,
                "filter": "/DCTDecode",
                "stream": image_bytes,
            }
        )
        self.current.append(f"q {w:.2f} 0 0 {h:.2f} {x:.2f} {y:.2f} cm /{name} Do Q")
        return True

    def image_file_fit(self, path, x, top_y, max_w, max_h):
        """Embed an image scaled to fit within max_w x max_h while preserving aspect ratio.

        (x, top_y) is the top-left anchor; the image is drawn downward from top_y.
        JPEG bytes are embedded without recompression and PNG losslessly, so the
        result keeps the uploaded document's full resolution. Returns the drawn
        height in points, or 0.0 if the file is missing or not a supported image.
        """
        try:
            with open(path, "rb") as fh:
                image_bytes = fh.read()
        except OSError:
            return 0.0
        dimensions = _image_dimensions(image_bytes)
        if not dimensions:
            return 0.0
        intrinsic_w, intrinsic_h = dimensions
        if intrinsic_w <= 0 or intrinsic_h <= 0:
            return 0.0
        scale = min(max_w / intrinsic_w, max_h / intrinsic_h)
        draw_w = intrinsic_w * scale
        draw_h = intrinsic_h * scale
        if self.image_file(path, x, top_y - draw_h, draw_w, draw_h):
            return draw_h
        return 0.0

    def table(self, x, y, col_widths, row_height, headers, rows, font_size=8, header_gray=0.9, max_lines=2):
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
                if isinstance(value, (list, tuple)):
                    # Pre-split lines (e.g. stacked Arrive/Depart/Wait); drawn as-is.
                    for line_idx, line in enumerate(value[:max_lines]):
                        self.text(cx + 3, y - 11 - line_idx * 9, line, size=font_size)
                else:
                    self.multiline_text(cx + 3, y - 11, value, max(6, int(width / 4.6)), size=font_size, leading=9, max_lines=max_lines)
                cx += width
            self.line(cx, y, cx, y - row_height)
            y -= row_height
        return y

    def build(self):
        objects = []
        objects.append("<< /Type /Catalog /Pages 2 0 R >>")
        first_page_obj = 6 + len(self.images)
        page_refs = " ".join(f"{first_page_obj + i * 2} 0 R" for i in range(len(self.pages)))
        objects.append(f"<< /Type /Pages /Kids [{page_refs}] /Count {len(self.pages)} >>")
        objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")
        objects.append("<< /Type /Font /Subtype /Type1 /BaseFont /ZapfChancery-MediumItalic >>")
        for idx, image in enumerate(self.images, start=6):
            image["object_id"] = idx
            stream = image["stream"].decode("latin-1")
            objects.append(
                f"<< /Type /XObject /Subtype /Image /Width {image['width']} "
                f"/Height {image['height']} /ColorSpace {image.get('color_space', '/DeviceRGB')} /BitsPerComponent 8 "
                f"/Filter {image.get('filter', '/FlateDecode')} /Length {len(image['stream'])} >>\n"
                f"stream\n{stream}\nendstream"
            )
        xobject_resources = ""
        if self.images:
            image_refs = " ".join(
                f"/{image['name']} {image['object_id']} 0 R" for image in self.images
            )
            xobject_resources = f" /XObject << {image_refs} >>"
        for index, (width, height, commands) in enumerate(self.pages):
            page_obj = first_page_obj + index * 2
            content_obj = page_obj + 1
            stream = "\n".join(commands)
            page = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width:.2f} {height:.2f}] "
                f"/Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >>{xobject_resources} >> "
                f"/Contents {content_obj} 0 R >>"
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
