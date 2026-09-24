import io
import re
import zipfile
from collections import Counter
from pathlib import PurePath
from typing import Protocol

MAX_BYTES = 20 * 1024 * 1024
MAX_PAGES = 200
MAX_TEXT = 2_000_000


class EncryptedDocumentError(ValueError):
    """A known recovery condition, safe to describe without exposing parser input."""


class OCRProvider(Protocol):
    def __call__(self, image: bytes) -> tuple[str, float]: ...


def tesseract_ocr(image: bytes) -> tuple[str, float]:
    import pytesseract
    from PIL import Image

    result = pytesseract.image_to_data(
        Image.open(io.BytesIO(image)), output_type=pytesseract.Output.DICT, timeout=30
    )
    rows: dict[tuple, list[str]] = {}
    confidences = []
    for i, word in enumerate(result['text']):
        if word.strip():
            key = tuple(result[k][i] for k in ('block_num', 'par_num', 'line_num'))
            rows.setdefault(key, []).append(word)
            confidences.append(max(0, float(result['conf'][i])) / 100)
    return '\n'.join(' '.join(words) for words in rows.values()), sum(confidences) / max(1, len(confidences))


def _page(
    number: int, text: str, *, quality: float = 1, ocr: bool = False, warning: str | None = None, blocks=None
) -> dict:
    if not text.strip():
        quality = 0
        warning = warning or 'No readable text was extracted on this page.'
    elif text.count('\ufffd') / max(1, len(text)) > 0.01:
        quality = min(quality, 0.4)
        warning = warning or 'Some characters could not be decoded. Compare against the original.'
    return dict(number=number, text=text, quality=quality, ocr=ocr, warning=warning, blocks=blocks or [])


def _remove_repeated_margins(pages: list[dict]) -> None:
    if len(pages) < 3:
        return
    margins = Counter()
    for page in pages:
        lines = page['text'].splitlines()
        if len(lines) > 4:
            margins.update(set((lines[0].strip(), lines[-1].strip())))
    repeated = {line for line, n in margins.items() if n >= max(3, len(pages) * 0.7) and len(line) < 150}
    for page in pages:
        lines = page['text'].splitlines()
        if len(lines) > 4:
            if lines[0].strip() in repeated:
                lines = lines[1:]
            if lines and lines[-1].strip() in repeated:
                lines = lines[:-1]
            page['text'] = '\n'.join(lines)


def extract_document(data: bytes, filename: str, media_type: str, ocr_provider=None) -> list[dict]:
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Upload a non-empty document no larger than 20 MB.')
    suffix = PurePath(filename).suffix.lower()
    expected = {
        '.pdf': 'application/pdf',
        '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        '.txt': 'text/plain',
    }
    if suffix not in expected or media_type not in (expected.get(suffix), 'application/octet-stream'):
        raise ValueError('The file extension and media type must identify PDF, DOCX, or TXT.')
    pages = []
    if suffix == '.pdf':
        if not data.startswith(b'%PDF-'):
            raise ValueError('The uploaded file does not contain a PDF signature.')
        import fitz

        with fitz.open(stream=data, filetype='pdf') as document:
            if document.is_encrypted:
                raise EncryptedDocumentError('Password-protected PDF')
            if len(document) > MAX_PAGES:
                raise ValueError('Documents are limited to 200 pages.')
            for number, source in enumerate(document, 1):
                text = source.get_text('text', sort=True)
                blocks = [
                    {'text': b[4], 'bbox': list(b[:4])}
                    for b in source.get_text('blocks', sort=True)
                    if len(b) > 4 and isinstance(b[4], str)
                ]
                needs_ocr = len(re.sub(r'\s', '', text)) < 25
                quality, warning = 1.0, None
                if needs_ocr:
                    provider = ocr_provider or tesseract_ocr
                    try:
                        if source.rect.width * source.rect.height * 2.25 > 20_000_000:
                            raise ValueError('Page dimensions exceed the OCR raster safety limit.')
                        pix = source.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
                        if pix.width * pix.height > 20_000_000:
                            raise ValueError('Page raster exceeds the OCR safety limit.')
                        ocr_text, quality = provider(pix.tobytes('png'))
                        if len(ocr_text.strip()) > len(text.strip()):
                            text, blocks = ocr_text, []
                        warning = 'OCR text: verify numbers, names, and punctuation against the original.'
                        if quality < 0.75:
                            warning = 'Low-confidence OCR on this page. Review the original before relying on this analysis.'
                    except (ImportError, RuntimeError, OSError, ValueError) as error:
                        quality = 0.1
                        warning = f'OCR was required but could not complete ({type(error).__name__}). Install/configure Tesseract or upload a text-based copy.'
                pages.append(
                    _page(number, text, quality=quality, ocr=needs_ocr, warning=warning, blocks=blocks)
                )
                if sum(len(item['text']) for item in pages) > MAX_TEXT:
                    raise ValueError('Extracted PDF content exceeds 2 million characters.')
    elif suffix == '.docx':
        if not data.startswith(b'PK'):
            raise ValueError('The uploaded file does not contain a DOCX signature.')
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                items = archive.infolist()
                if len(items) > 5000 or sum(x.file_size for x in items) > 50 * 1024 * 1024:
                    raise ValueError('DOCX decompressed content exceeds the safety limit.')
                if 'word/document.xml' not in archive.namelist() or any(
                    x.filename.lower().endswith('vbaproject.bin') for x in items
                ):
                    raise ValueError('Upload a standard DOCX without macros.')
                if b'<!DOCTYPE' in archive.read('word/document.xml').upper():
                    raise ValueError('DOCX external document declarations are unsupported.')
            from docx import Document
            from docx.oxml.ns import qn

            document = Document(io.BytesIO(data))
            paragraphs = []
            for item in document.element.body:
                if item.tag == qn('w:p'):
                    text = ''.join(x.text or '' for x in item.iter(qn('w:t')))
                    paragraphs.append(text)
                elif item.tag == qn('w:tbl'):
                    for row in item.findall(qn('w:tr')):
                        paragraphs.append(
                            ' | '.join(
                                ' '.join(x.text or '' for x in cell.iter(qn('w:t')))
                                for cell in row.findall(qn('w:tc'))
                            )
                        )
            # DOCX has no stable printed pagination without a layout engine. These are explicit logical pages.
            text = '\n\n'.join(paragraphs)
            pages = [
                _page(
                    1,
                    text,
                    warning='DOCX uses logical page 1; printed pagination requires rendering in Word. Paragraph and table order are preserved.',
                )
            ]
        except (zipfile.BadZipFile, KeyError) as error:
            raise ValueError('This DOCX is damaged or incomplete.') from error
    else:
        if b'\x00' in data and not data.startswith((b'\xff\xfe', b'\xfe\xff')):
            raise ValueError('TXT files must contain readable text, not binary content.')
        try:
            text = data.decode('utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig')
        except UnicodeDecodeError as error:
            raise ValueError('Save the text file as UTF-8 or UTF-16 and upload again.') from error
        pages = [
            _page(
                i,
                text_part,
                warning='Text-file page numbers follow form-feed separators, not printed pagination.',
            )
            for i, text_part in enumerate(text.split('\f'), 1)
        ]
    if len(pages) > MAX_PAGES or sum(len(x['text']) for x in pages) > MAX_TEXT:
        raise ValueError('Extracted content exceeds 200 pages or 2 million characters.')
    _remove_repeated_margins(pages)
    return pages
