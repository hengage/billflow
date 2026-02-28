from rest_framework.permissions import BasePermission


class IsAdmin(BasePermission):
    """
    Allows access only to users with the admin role.
    Used on endpoints like POST /api/plans/ that only admins should write to.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'admin')


class IsCustomer(BasePermission):
    """
    Allows access only to users with the customer role.
    """
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == 'customer')


class IsOwnerOrAdmin(BasePermission):
    """
    Object-level permission — allows access if the user owns the object or is an admin.
    Used on endpoints like GET /api/wallet/ where a customer can only see their own wallet,
    but an admin can see any wallet.

    The view must call self.check_object_permissions(request, obj) for this to run.
    """
    def has_object_permission(self, request, view, obj):
        if request.user.role == 'admin':
            return True
        
        # checks if the user is the owner of the object — works for Wallet, Subscription, Payment etc.
        return obj.user == request.user