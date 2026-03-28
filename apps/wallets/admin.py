from django.contrib import admin
from .models import Wallet, WalletTransaction


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ('user', 'balance', 'currency', 'updated_at')
    search_fields = ('user__email',)
    readonly_fields = ('id', 'updated_at')


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ('wallet', 'type', 'amount', 'reference', 'created_at')
    list_filter = ('type',)
    search_fields = ('wallet__user__email', 'reference')
    readonly_fields = ('id', 'created_at')
    
    # Transactions are immutable — no adding or deleting from admin
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False