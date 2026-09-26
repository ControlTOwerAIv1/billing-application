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
    list_display = ("id", "voucher_no", "customer", "transport", "gst_enabled", "custom_gst_rate", "subtotal", "packing_charge", "discount_amount", "total_amount", "status", "created_at", "soft_deleted")
    list_filter = ("status", "gst_enabled", "transport", "soft_deleted")
    search_fields = ("voucher_no", "customer__name")
    inlines = [OrderItemInline]
