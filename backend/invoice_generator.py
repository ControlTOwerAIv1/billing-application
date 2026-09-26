import io
import datetime
from decimal import Decimal
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image
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

    company_title_style = ParagraphStyle(
        'CompanyTitle',
        parent=styles['Heading1'],
        fontSize=15,
        leading=19,
        textColor=colors.HexColor('#0F172A'),
        fontName='Helvetica-Bold'
    )

    company_tagline_style = ParagraphStyle(
        'CompanyTagline',
        parent=styles['Normal'],
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor('#15803D'),
        fontName='Helvetica-Bold'
    )

    company_sub_style = ParagraphStyle(
        'CompanySub',
        parent=styles['Normal'],
        fontSize=8,
        leading=11,
        textColor=colors.HexColor('#64748B'),
        fontName='Helvetica'
    )

    invoice_title_right_style = ParagraphStyle(
        'InvoiceTitleRight',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#1E293B'),
        fontName='Helvetica-Bold',
        alignment=2
    )

    invoice_sub_right_style = ParagraphStyle(
        'InvoiceSubRight',
        parent=styles['Normal'],
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor('#64748B'),
        fontName='Helvetica-Bold',
        alignment=2
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

    table_header_center_style = ParagraphStyle(
        'TableHeaderCenter',
        parent=table_header_style,
        alignment=1
    )

    table_header_right_style = ParagraphStyle(
        'TableHeaderRight',
        parent=table_header_style,
        alignment=2
    )

    normal_center_style = ParagraphStyle(
        'NormalCenter',
        parent=normal_style,
        alignment=1
    )

    normal_right_style = ParagraphStyle(
        'NormalRight',
        parent=normal_style,
        alignment=2
    )

    story = []

    # Title & Header with HINDUSTAN PLAST Logo
    logo_file = None
    possible_paths = [
        Path(__file__).resolve().parent / "assets" / "logo.png",
        Path(__file__).resolve().parent.parent / "media" / "logo.png",
        Path(__file__).resolve().parent.parent / "media" / "company_logo.png",
    ]
    for p in possible_paths:
        if p.exists():
            logo_file = str(p)
            break

    tax_sum = (getattr(order, 'cgst_amount', Decimal("0.00")) or Decimal("0.00")) + \
              (getattr(order, 'sgst_amount', Decimal("0.00")) or Decimal("0.00")) + \
              (getattr(order, 'igst_amount', Decimal("0.00")) or Decimal("0.00"))
    custom_rate = getattr(order, 'custom_gst_rate', None)
    has_zero_rate = (custom_rate is not None and custom_rate <= Decimal("0.00"))

    gst_is_active = bool(getattr(order, 'gst_enabled', True)) and (tax_sum > Decimal("0.00")) and (not has_zero_rate)
    inv_title_text = "TAX INVOICE" if gst_is_active else "INVOICE / BILL"
    inv_sub_text = "ORIGINAL FOR RECIPIENT" if gst_is_active else "COMMERCIAL BILL OF SUPPLY"

    if logo_file:
        logo_img = Image(logo_file, width=62, height=62)
        company_col = [
            Paragraph("<b>HINDUSTAN PLAST</b>", company_title_style),
            Spacer(1, 2),
            Paragraph("Shaping Convenience, Crafting Quality", company_tagline_style),
            Spacer(1, 2),
            Paragraph("Wholesale Distribution & Supply Chain", company_sub_style)
        ]
        invoice_col = [
            Paragraph(inv_title_text, invoice_title_right_style),
            Spacer(1, 3),
            Paragraph(inv_sub_text, invoice_sub_right_style)
        ]
        header_table = Table([[logo_img, company_col, invoice_col]], colWidths=[68, 252, 200])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(header_table)
    else:
        header_table = Table([
            [
                [
                    Paragraph("<b>HINDUSTAN PLAST</b>", company_title_style),
                    Paragraph("Shaping Convenience, Crafting Quality", company_tagline_style),
                    Paragraph("Wholesale Distribution & Supply Chain", company_sub_style)
                ],
                [
                    Paragraph(inv_title_text, invoice_title_right_style),
                    Paragraph(inv_sub_text, invoice_sub_right_style)
                ]
            ]
        ], colWidths=[320, 200])
        header_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(header_table)

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#3B82F6'), spaceAfter=14))

    # Order Meta & Customer Info side by side
    customer = order.customer
    created_date = order.created_at.strftime("%d %b %Y, %H:%M") if order.created_at else datetime.datetime.now().strftime("%d %b %Y, %H:%M")
    order_type_display = "Sales Order" if order.order_type == "sales" else "Advance Purchase Order"

    transport_obj = order.transport or customer.transport
    transport_display = transport_obj.name if transport_obj else "Direct / Self"
    if transport_obj and transport_obj.vehicle_number:
        transport_display += f" ({transport_obj.vehicle_number})"

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
                      f"<b>Transport:</b> {transport_display}<br/>"
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

    # Line Items Table Header (Grouped by Category / Master SKU, SKU hidden)
    items_data = [
        [
            Paragraph("#", table_header_center_style),
            Paragraph("Category & Products", table_header_style),
            Paragraph("Rate (₹)", table_header_right_style),
            Paragraph("Total Rate (₹)", table_header_right_style),
        ]
    ]

    # Group order items by product category (Master SKU)
    from collections import OrderedDict
    category_groups = OrderedDict()
    items = order.items.select_related('product').all()
    for item in items:
        cat = item.product.category if (item.product and item.product.category) else "General"
        if cat not in category_groups:
            category_groups[cat] = []
        category_groups[cat].append(item)

    for idx, (cat_name, group_items) in enumerate(category_groups.items(), 1):
        prod_entries = []
        rates = []
        group_total = Decimal("0.00")

        for item in group_items:
            prod_name = item.product.name if item.product else "N/A"
            qty = item.quantity
            color_suffix = f" [{item.color}]" if getattr(item, 'color', None) else ""
            prod_entries.append(f"{prod_name}{color_suffix} (Qty: {qty})")
            rates.append(f"{float(item.unit_price):,.2f}")
            group_total += Decimal(str(item.total_amount if item.total_amount is not None else item.taxable_amount or 0))

        prods_text = ", ".join(prod_entries)
        description_cell = Paragraph(
            f"<b>{cat_name}</b><br/><font color='#475569'>{prods_text}</font>",
            normal_style
        )
        rates_text = ", ".join(rates)
        total_rate_text = f"{float(group_total):,.2f}"

        items_data.append([
            Paragraph(str(idx), normal_center_style),
            description_cell,
            Paragraph(rates_text, normal_right_style),
            Paragraph(total_rate_text, normal_right_style),
        ])

    items_table = Table(items_data, colWidths=[30, 313, 90, 90])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E293B')),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')])
    ]))
    story.append(items_table)
    story.append(Spacer(1, 15))

    # Financial Summary Table
    is_intra_state = (customer.state_code == "08")
    
    subtotal_label = "<b>Subtotal (Taxable Amount):</b>" if gst_is_active else "<b>Subtotal:</b>"
    totals_data = [
        [Paragraph(subtotal_label, normal_style), Paragraph(f"₹{float(order.subtotal):,.2f}", normal_style)]
    ]

    if gst_is_active:
        if is_intra_state:
            cgst_label = f"<b>CGST ({float(order.custom_gst_rate)/2.0:g}%):</b>" if order.custom_gst_rate else "<b>CGST:</b>"
            sgst_label = f"<b>SGST ({float(order.custom_gst_rate)/2.0:g}%):</b>" if order.custom_gst_rate else "<b>SGST:</b>"
            totals_data.append([Paragraph(cgst_label, normal_style), Paragraph(f"₹{float(order.cgst_amount):,.2f}", normal_style)])
            totals_data.append([Paragraph(sgst_label, normal_style), Paragraph(f"₹{float(order.sgst_amount):,.2f}", normal_style)])
        else:
            igst_label = f"<b>IGST ({float(order.custom_gst_rate):g}%):</b>" if order.custom_gst_rate else "<b>IGST:</b>"
            totals_data.append([Paragraph(igst_label, normal_style), Paragraph(f"₹{float(order.igst_amount):,.2f}", normal_style)])

    packing = getattr(order, 'packing_charge', Decimal("0.00")) or Decimal("0.00")
    if packing > Decimal("0.00"):
        totals_data.append([Paragraph("<b>Packing & Handling:</b>", normal_style), Paragraph(f"+ ₹{float(packing):,.2f}", normal_style)])

    discount = getattr(order, 'discount_amount', Decimal("0.00")) or Decimal("0.00")
    if discount > Decimal("0.00"):
        discount_style = ParagraphStyle('DiscountStyle', parent=normal_style, textColor=colors.HexColor('#16A34A'))
        totals_data.append([Paragraph("<b>Discount:</b>", discount_style), Paragraph(f"- ₹{float(discount):,.2f}", discount_style)])

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
    doc_kind = "tax invoice" if gst_is_active else "bill of supply / invoice"
    story.append(Paragraph(f"<i>This is a computer-generated {doc_kind} issued by HINDUSTAN PLAST. No signature required. Thank you for your business!</i>", sub_title_style))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
