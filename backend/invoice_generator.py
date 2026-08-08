import io
import datetime
from decimal import Decimal
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

def generate_order_pdf_bytes(order) -> bytes:
    """
    Generates a professional PDF Tax Invoice for an Order instance.
    Returns the PDF content as bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        'InvoiceTitle',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#1E293B'),
        fontName='Helvetica-Bold',
        alignment=0
    )

    sub_title_style = ParagraphStyle(
        'InvoiceSubTitle',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#64748B'),
        fontName='Helvetica'
    )

    section_header = ParagraphStyle(
        'SectionHeader',
        parent=styles['Heading2'],
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#0F172A'),
        fontName='Helvetica-Bold'
    )

    normal_style = ParagraphStyle(
        'NormalText',
        parent=styles['Normal'],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#334155')
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontSize=9,
        leading=11,
        textColor=colors.white,
        fontName='Helvetica-Bold'
    )

    story = []

    # Title & Header
    story.append(Paragraph("TAX INVOICE", title_style))
    story.append(Paragraph("OrderBot Supply Chain & Wholesale Distribution", sub_title_style))
    story.append(Spacer(1, 12))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#3B82F6'), spaceAfter=15))

    # Order Meta & Customer Info side by side
    customer = order.customer
    created_date = order.created_at.strftime("%d %b %Y, %H:%M") if order.created_at else datetime.datetime.now().strftime("%d %b %Y, %H:%M")
    order_type_display = "Sales Order" if order.order_type == "sales" else "Advance Purchase Order"

    cust_info = [
        [Paragraph("<b>Billed To:</b>", section_header), Paragraph("<b>Invoice Details:</b>", section_header)],
        [
            Paragraph(f"<b>{customer.name}</b><br/>"
                      f"Business: {customer.business_name or 'N/A'}<br/>"
                      f"Phone: {customer.phone}<br/>"
                      f"State Code: {customer.state_code}<br/>"
                      f"GSTIN: {customer.gstin or 'N/A'}", normal_style),
            Paragraph(f"<b>Invoice #:</b> {order.voucher_no}<br/>"
                      f"<b>Date:</b> {created_date}<br/>"
                      f"<b>Order Type:</b> {order_type_display}<br/>"
                      f"<b>Status:</b> {order.status.upper()}<br/>"
                      f"<b>Payment:</b> {order.payment_status.upper()}", normal_style)
        ]
    ]

    info_table = Table(cust_info, colWidths=[260, 260])
    info_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 15))

    # Line Items Table Header
    items_data = [
        [
            Paragraph("#", table_header_style),
            Paragraph("Item Description", table_header_style),
            Paragraph("SKU", table_header_style),
            Paragraph("Unit Type", table_header_style),
            Paragraph("Qty", table_header_style),
            Paragraph("Rate (₹)", table_header_style),
            Paragraph("GST %", table_header_style),
            Paragraph("Total (₹)", table_header_style),
        ]
    ]

    items = order.items.select_related('product').all()
    for idx, item in enumerate(items, 1):
        prod_name = item.product.name if item.product else "N/A"
        sku = item.product.sku if item.product else "N/A"
        unit_type = item.unit_type.replace('_', ' ').title()
        
        items_data.append([
            Paragraph(str(idx), normal_style),
            Paragraph(prod_name, normal_style),
            Paragraph(sku, normal_style),
            Paragraph(unit_type, normal_style),
            Paragraph(str(item.quantity), normal_style),
            Paragraph(f"{float(item.unit_price):,.2f}", normal_style),
            Paragraph(f"{float(item.gst_rate):.1f}%", normal_style),
            Paragraph(f"{float(item.total_amount or item.taxable_amount):,.2f}", normal_style),
        ])

    items_table = Table(items_data, colWidths=[25, 150, 75, 70, 35, 55, 45, 65])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E293B')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('ALIGN', (4, 1), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')])
    ]))
    story.append(items_table)
    story.append(Spacer(1, 15))

    # Financial Summary Table
    is_intra_state = (customer.state_code == "08")
    
    totals_data = [
        [Paragraph("<b>Subtotal (Taxable Amount):</b>", normal_style), Paragraph(f"₹{float(order.subtotal):,.2f}", normal_style)]
    ]

    if is_intra_state:
        totals_data.append([Paragraph("<b>CGST:</b>", normal_style), Paragraph(f"₹{float(order.cgst_amount):,.2f}", normal_style)])
        totals_data.append([Paragraph("<b>SGST:</b>", normal_style), Paragraph(f"₹{float(order.sgst_amount):,.2f}", normal_style)])
    else:
        totals_data.append([Paragraph("<b>IGST:</b>", normal_style), Paragraph(f"₹{float(order.igst_amount):,.2f}", normal_style)])

    grand_total_style = ParagraphStyle('GrandTotal', parent=normal_style, fontSize=11, fontName='Helvetica-Bold', textColor=colors.HexColor('#1E293B'))
    totals_data.append([Paragraph("<b>Grand Total:</b>", grand_total_style), Paragraph(f"<b>₹{float(order.total_amount):,.2f}</b>", grand_total_style)])

    totals_table = Table(totals_data, colWidths=[200, 100])
    totals_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor('#1E293B')),
    ]))

    # Position totals on the right side
    summary_wrapper = Table([[Paragraph("", normal_style), totals_table]], colWidths=[220, 300])
    summary_wrapper.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
    ]))
    story.append(summary_wrapper)
    story.append(Spacer(1, 30))

    # Footer Notes
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#CBD5E1'), spaceAfter=10))
    story.append(Paragraph("<b>Terms & Conditions:</b> Goods once sold will not be taken back or exchanged. Payment due as per credit terms.", sub_title_style))
    story.append(Spacer(1, 4))
    story.append(Paragraph("<i>This is a computer-generated tax invoice. No signature required. Thank you for your business!</i>", sub_title_style))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
