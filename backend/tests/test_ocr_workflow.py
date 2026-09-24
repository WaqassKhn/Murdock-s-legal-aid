import io
import shutil

import fitz
import pytest
from PIL import Image, ImageDraw, ImageFont
from test_api import client, register, upload, workspace


@pytest.mark.skipif(shutil.which('tesseract') is None, reason='Run in the Docker image with Tesseract.')
def test_scanned_upload_cited_answer_and_delete(client):
    image = Image.new('RGB', (1800, 700), 'white')
    ImageDraw.Draw(image).multiline_text(
        (40, 60),
        'SYNTHETIC DEMO CONTRACT\n1. Payment\nCustomer must pay USD 500 within 30 days.',
        fill='black',
        font=ImageFont.truetype('DejaVuSans.ttf', 36),
        spacing=20,
    )
    stream = io.BytesIO()
    image.save(stream, format='PNG')
    with fitz.open() as pdf:
        page = pdf.new_page(width=900, height=350)
        page.insert_image(page.rect, stream=stream.getvalue())
        data = pdf.tobytes()
    register(client)
    w = workspace(client)
    document = upload(client, w, data, 'synthetic-scan.pdf', 'application/pdf')
    assert document['pages'][0]['ocr']
    assert document['pages'][0]['quality'] > 0.7
    response = client.post(f'/api/workspaces/{w}/ask', json={'question': 'What must Customer pay?'})
    assert response.status_code == 200
    answer = response.json()
    assert not answer['abstained'] and '500' in answer['direct_answer']
    for citation in answer['citations']:
        assert citation['document_id'] == document['id'] and citation['page'] == 1
        resolved = client.post(f'/api/workspaces/{w}/citations/resolve', json=citation)
        assert resolved.json()['verified']
    assert client.delete(f'/api/workspaces/{w}/documents/{document["id"]}').status_code == 204
