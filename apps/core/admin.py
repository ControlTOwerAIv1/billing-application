from django.contrib import admin
from apps.core.models import Tenant, Customer, Product, Order

@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "state_code", "gstin", "soft_deleted")
    list_filter = ("soft_deleted", "state_code")
    search_fields = ("name", "gstin")

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "phone", "state_code", "balance_amount", "status", "soft_deleted")
    list_filter = ("status", "soft_deleted", "state_code")
    search_fields = ("name", "phone", "business_name")

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("id", "sku", "name", "category", "base_price", "gst_rate", "soft_deleted")
    list_filter = ("category", "gst_rate", "soft_deleted")
    search_fields = ("sku", "name")

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "voucher_no", "customer", "total_amount", "status", "created_at", "soft_deleted")
    list_filter = ("status", "soft_deleted")
    search_fields = ("voucher_no", "customer__name")
