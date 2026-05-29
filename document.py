"""
document.py — Hujjat moduli:
4. PDF Summarizer
5. Invoice Generator (PDF)
6. OCR (AI Vision orqali)
"""
import os
import io
import logging
import tempfile
from datetime import datetime

logger = logging.getLogger("jarvis.document")


# ─────────────────────────────────────────
# 4. PDF SUMMARIZER
# ─────────────────────────────────────────

def extract_pdf_text(pdf_bytes: bytes) -> str:
    """PDF dan matn ajratib olish."""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = []
            for page in pdf.pages[:30]:  # max 30 sahifa
                text = page.extract_text()
                if text:
                    pages.append(text)
            return "\n\n".join(pages)
    except ImportError:
        pass
    # Fallback: pypdf
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        texts = []
        for page in reader.pages[:30]:
            texts.append(page.extract_text() or "")
        return "\n\n".join(texts)
    except Exception as e:
        return f"PDF o'qishda xatolik: {e}"


def prepare_summary_prompt(text: str, instruction: str = "") -> str:
    """AI uchun xulosa promptini tayyorlash."""
    max_chars = 12000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[Matn qisqartirildi — davomi bor]"
    base = (
        "Quyidagi hujjatni o'qib, O'zbek tilida qisqacha va aniq xulosa chiqar.\n"
        "Xulosada quyidagilarni ko'rsat:\n"
        "1. Hujjat nima haqida (1-2 gap)\n"
        "2. Asosiy bandlar / shartlar / g'oyalar (ro'yxat)\n"
        "3. Muhim sanalar, summalar, raqamlar (agar bo'lsa)\n"
        "4. Xavfli yoki e'tiborli bandlar (agar bo'lsa)\n\n"
    )
    if instruction:
        base += f"Qo'shimcha: {instruction}\n\n"
    base += f"HUJJAT MATNI:\n{text}"
    return base


# ─────────────────────────────────────────
# 5. INVOICE GENERATOR
# ─────────────────────────────────────────

def generate_invoice(
    client_name: str,
    services: list[dict],  # [{"name": "...", "qty": 1, "price": 500}]
    currency: str = "USD",
    invoice_number: str = None,
    company_name: str = "Isroiljon Abdullayev",
    company_details: str = "isroiljohnabdullayev@gmail.com",
    note: str = "",
) -> bytes:
    """Professional PDF hisob-faktura yaratish."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT, TA_CENTER, TA_LEFT

    if not invoice_number:
        invoice_number = f"INV-{datetime.now().strftime('%Y%m%d%H%M')}"

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            rightMargin=20*mm, leftMargin=20*mm,
                            topMargin=20*mm, bottomMargin=20*mm)

    styles = getSampleStyleSheet()
    story = []

    # Sarlavha
    title_style = ParagraphStyle("title", fontSize=24, fontName="Helvetica-Bold",
                                  textColor=colors.HexColor("#1a1a2e"), spaceAfter=2*mm)
    story.append(Paragraph("INVOICE", title_style))

    # Kompaniya va mijoz ma'lumotlari
    info_data = [
        [Paragraph(f"<b>{company_name}</b>", styles["Normal"]),
         Paragraph(f"<b>Invoice #:</b> {invoice_number}", styles["Normal"])],
        [Paragraph(company_details, styles["Normal"]),
         Paragraph(f"<b>Sana:</b> {datetime.now().strftime('%d.%m.%Y')}", styles["Normal"])],
        ["",
         Paragraph(f"<b>Mijoz:</b> {client_name}", styles["Normal"])],
    ]
    info_table = Table(info_data, colWidths=[90*mm, 80*mm])
    info_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 8*mm))

    # Xizmatlar jadvali
    table_data = [["Xizmat nomi", "Miqdor", "Narx", "Jami"]]
    total = 0
    for svc in services:
        qty = svc.get("qty", 1)
        price = float(svc.get("price", 0))
        amount = qty * price
        total += amount
        table_data.append([
            svc.get("name", ""),
            str(qty),
            f"{price:,.2f} {currency}",
            f"{amount:,.2f} {currency}",
        ])

    # Jami qator
    table_data.append(["", "", "JAMI:", f"{total:,.2f} {currency}"])

    col_widths = [90*mm, 20*mm, 40*mm, 40*mm]
    svc_table = Table(table_data, colWidths=col_widths)
    svc_table.setStyle(TableStyle([
        # Sarlavha
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a1a2e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 11),
        ("ALIGN", (0, 0), (-1, 0), "CENTER"),
        # Ma'lumotlar
        ("FONTSIZE", (0, 1), (-1, -2), 10),
        ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f5f5f5")]),
        ("GRID", (0, 0), (-1, -2), 0.5, colors.HexColor("#dddddd")),
        # Jami
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, -1), (-1, -1), 12),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#e8f4fd")),
        ("LINEABOVE", (0, -1), (-1, -1), 1.5, colors.HexColor("#1a1a2e")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(svc_table)

    if note:
        story.append(Spacer(1, 6*mm))
        story.append(Paragraph(f"<i>Izoh: {note}</i>", styles["Normal"]))

    # Pastki qism
    story.append(Spacer(1, 10*mm))
    footer_style = ParagraphStyle("footer", fontSize=9,
                                   textColor=colors.grey, alignment=TA_CENTER)
    story.append(Paragraph("Rahmat! To'lov uchun bog'laning.", footer_style))

    doc.build(story)
    return buffer.getvalue()


def parse_invoice_request(text: str) -> dict:
    """Tabiiy tildan faktura ma'lumotlarini ajratish uchun prompt."""
    return {
        "prompt": (
            "Foydalanuvchi faktura yaratishni so'rayapti. Quyidagi ma'lumotlarni JSON formatida ajrat:\n"
            "{\n"
            '  "client_name": "...",\n'
            '  "services": [{"name": "...", "qty": 1, "price": 100}],\n'
            '  "currency": "USD",\n'
            '  "note": ""\n'
            "}\n"
            f"So'rov: {text}\n\n"
            "Faqat JSON qaytarilsin, boshqa narsa emas."
        )
    }


# ─────────────────────────────────────────
# 6. QR KOD GENERATOR (17-funksiya ham shu yerda)
# ─────────────────────────────────────────

def generate_qr_code(content: str, title: str = "") -> bytes:
    """QR kod rasmini bytes sifatida yaratish."""
    import qrcode
    from PIL import Image, ImageDraw, ImageFont

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(content)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#1a1a2e", back_color="white").convert("RGB")

    # Sarlavha qo'shish (agar berilsa)
    if title:
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        w, h = img.size
        # Oddiy matn (font mavjud bo'lmasa)
        try:
            draw.text((w // 2, h - 30), title, fill="#1a1a2e", anchor="mm")
        except Exception:
            pass

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()
