from django.contrib import admin
from apps.core.models import Tenant, Customer, Product, Order, Transport

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

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("id", "sku", "name", "category", "base_price", "gst_rate", "soft_deleted")
    list_filter = ("category", "gst_rate", "soft_deleted")
    search_fields = ("sku", "name")

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "voucher_no", "customer", "transport", "gst_enabled", "custom_gst_rate", "subtotal", "packing_charge", "discount_amount", "total_amount", "status", "created_at", "soft_deleted")
    list_filter = ("status", "gst_enabled", "transport", "soft_deleted")
    search_fields = ("voucher_no", "customer__name")
