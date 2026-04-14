from django.contrib import admin
from django.utils.html import format_html
from .models import Plan, Subscription


class SubscriptionInline(admin.TabularInline):
    model = Subscription
    fields = ('user', 'billing_cycle', 'status', 'start_date_utc', 'end_date_utc')
    readonly_fields = ('user', 'billing_cycle', 'status', 'start_date_utc', 'end_date_utc')
    extra = 0
    can_delete = False
    max_num = 0


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'monthly_price_ngn', 'yearly_price_ngn', 'is_active', 'subscription_count', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'description')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [SubscriptionInline]
    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'description', 'is_active')
        }),
        ('Pricing', {
            'fields': ('monthly_price_ngn', 'yearly_price_ngn')
        }),
        ('Features', {
            'fields': ('features',),
            'description': 'List of features included in this plan (JSON format)'
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    def subscription_count(self, obj):
        count = obj.subscriptions.count()
        if count:
            return format_html('<a href="/admin/subscriptions/subscription/?plan__id__exact={}">{} subscriptions</a>', obj.id, count)
        return '0 subscriptions'
    subscription_count.short_description = 'Subscriptions'


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan_link', 'billing_cycle', 'status', 'start_date_utc', 'end_date_utc', 'cancelled_at')
    list_filter = ('status', 'billing_cycle', 'plan')
    search_fields = ('user__email', 'user__first_name', 'user__last_name', 'plan__name')
    readonly_fields = ('created_at', 'renewal_attempts', 'last_renewal_attempt_at', 'plan_link')
    raw_id_fields = ('user',)  # Makes user searchable with popup

    def plan_link(self, obj):
        return format_html('<a href="/admin/subscriptions/plan/{}/change/">{}</a>', obj.plan.id, obj.plan.name)
    plan_link.short_description = 'Plan'
    plan_link.admin_order_field = 'plan__name'

    fieldsets = (
        ('User & Plan', {
            'fields': ('user', 'plan_link', 'plan', 'billing_cycle')
        }),
        ('Status & Dates', {
            'fields': ('status', 'start_date_utc', 'end_date_utc', 'cancelled_at')
        }),
        ('Payment', {
            'fields': ('amount_paid', 'payment')
        }),
        ('Auto-renewal', {
            'fields': ('renewal_attempts', 'last_renewal_attempt_at'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
