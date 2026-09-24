import io
import zipfile
from pathlib import Path
from fastapi import HTTPException

MIME = {
    '.pdf': 'application/pdf',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.txt': 'text/plain',
}


def validate_upload(data: bytes, name: str, supplied_mime: str) -> str:
    suffix = Path(name).suffix.lower()
    if suffix not in MIME:
        raise HTTPException(415, 'Unsupported file. Upload a PDF, DOCX, or UTF-8 TXT document.')
    expected = MIME[suffix]
    if supplied_mime not in (expected, 'application/octet-stream', ''):
        raise HTTPException(
            415, 'The file type does not match its extension. Export the original as PDF, DOCX, or TXT.'
        )
    if not data:
        raise HTTPException(422, 'The document is empty.')
    if suffix == '.pdf' and not data.startswith(b'%PDF-'):
        raise HTTPException(415, 'This file does not contain a valid PDF header.')
    if suffix == '.docx':
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                entries = archive.infolist()
                if len(entries) > 2000 or sum(item.file_size for item in entries) > 80 * 1024 * 1024:
                    raise HTTPException(413, 'The expanded DOCX is too large to process safely.')
                if any(item.flag_bits & 1 for item in entries):
                    raise HTTPException(415, 'Encrypted DOCX files are not supported.')
                if any(
                    '..' in Path(item.filename).parts or item.filename.startswith('/') for item in entries
                ):
                    raise HTTPException(415, 'The document contains unsafe archive paths.')
                names = archive.namelist()
                if (
                    'word/document.xml' not in names
                    or '[Content_Types].xml' not in names
                    or any('vbaProject' in n for n in names)
                ):
                    raise HTTPException(415, 'Upload a standard DOCX without embedded macros.')
        except zipfile.BadZipFile:
            raise HTTPException(415, 'The DOCX archive is invalid.') from None
    if suffix == '.txt':
        try:
            text = data.decode('utf-8-sig')
        except UnicodeDecodeError:
            raise HTTPException(415, 'Save text documents using UTF-8 encoding and upload again.') from None
        if not text.strip():
            raise HTTPException(422, 'The document has no readable text. Add text or upload another file.')
        if '\x00' in text or sum(ord(c) < 32 and c not in '\n\r\t\f' for c in text) > 3:
            raise HTTPException(415, 'The TXT document contains binary content.')
    return expected
