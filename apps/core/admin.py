from django.contrib import admin
from apps.core.models import Tenant, Customer, Product, Order, OrderItem, Transport

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "state_code", "gstin", "soft_deleted")
    list_filter = ("soft_deleted", "state_code")
    search_fields = ("name", "gstin")

@admin.register(Transport)
class TransportAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "phone", "contact_person", "vehicle_number", "destination_notes", "is_active", "soft_deleted")
    list_filter = ("is_active", "soft_deleted")
    search_fields = ("name", "phone", "contact_person", "destination_notes")

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "phone", "state_code", "transport", "balance_amount", "status", "soft_deleted")
    list_filter = ("status", "transport", "soft_deleted", "state_code")
    search_fields = ("name", "phone", "business_name")

from django.utils.html import format_html

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "photo_thumbnail",
        "name",
        "colors",
        "group_alias",
        "category_alias",
        "opening_qty",
        "closing_qty",
        "base_price",
        "gst_rate",
        "is_active",
        "soft_deleted"
    )
    list_filter = ("group_alias", "category_alias", "is_active", "soft_deleted")
    search_fields = ("name", "sku", "colors", "group_alias", "category_alias")
    readonly_fields = ("photo_preview",)
    fieldsets = (
        ("Product Identity & Aliases", {
            "fields": ("name", "sku", "group_alias", "category_alias", "category", "colors", "is_active")
        }),
        ("Product Media / Photo", {
            "fields": ("photo", "photo_preview", "image_url")
        }),
        ("Ledger Stock Quantities", {
            "fields": ("opening_qty", "closing_qty")
        }),
        ("Pricing & GST", {
            "fields": (
                "base_price", "loose_price", "full_carton_price", "half_carton_price",
                "full_carton_quantity", "gst_rate", "hsn_code"
            )
        }),
    )

    def photo_thumbnail(self, obj):
        url = obj.photo_url
        if url:
            return format_html('<img src="{}" style="width: 44px; height: 44px; object-fit: cover; border-radius: 6px; border: 1px solid #ccc;" />', url)
        return format_html('<span style="color: #999; font-size: 11px;">No Photo</span>')
    photo_thumbnail.short_description = "Photo"

    def photo_preview(self, obj):
        url = obj.photo_url
        if url:
            return format_html('<img src="{}" style="max-width: 220px; max-height: 220px; object-fit: contain; border-radius: 8px; border: 1px solid #ccc; box-shadow: 0 2px 6px rgba(0,0,0,0.15);" />', url)
        return "Upload a photo or provide an Image URL to preview."
    photo_preview.short_description = "Photo Preview"

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    fields = ("product", "quantity", "unit_price", "pricing_tier", "color", "item_total")
    readonly_fields = ("item_total",)

    def item_total(self, obj):
        return obj.total_price
    item_total.short_description = "Total"

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "voucher_no", "customer", "whatsapp_invoice_btn", "notes", "hide_product_rate", "transport", "gst_enabled", "custom_gst_rate", "subtotal", "packing_charge", "discount_amount", "total_amount", "status", "created_at", "soft_deleted")
    list_filter = ("status", "hide_product_rate", "gst_enabled", "transport", "soft_deleted")
    search_fields = ("voucher_no", "customer__name", "notes")
    readonly_fields = ("whatsapp_invoice_btn",)
    inlines = [OrderItemInline]

    def whatsapp_invoice_btn(self, obj):
        if not obj or not obj.id or not obj.customer:
            return "-"
        from apps.api.api import generate_whatsapp_invoice_data
        wa_data = generate_whatsapp_invoice_data(obj)
        wa_url = wa_data.get("whatsapp_url", "")
        if not wa_url:
            return format_html('<span style="color:#94a3b8; font-size:11px;">No Phone</span>')
        return format_html(
            '<a href="{}" target="_blank" style="background: #25D366; color: #fff; padding: 3px 8px; border-radius: 6px; text-decoration: none; font-weight: 700; font-size: 11px; display: inline-flex; align-items: center; gap: 4px; box-shadow: 0 1px 3px rgba(0,0,0,0.2);">'
            '📲 WhatsApp</a>',
            wa_url
        )
    whatsapp_invoice_btn.short_description = "WhatsApp"
