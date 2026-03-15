from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from dj_rest_auth.serializers import PasswordResetConfirmSerializer
from users.models import User

class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for user profile display and updates.
    Email and role are read-only for security.
    """
    email = serializers.EmailField(read_only=True)
    role = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = ('id', 'email', 'first_name', 'last_name', 'role', 'notification_preferences', 'date_joined')
        read_only_fields = ('id', 'date_joined')
        

class LoginSerializer(serializers.Serializer):
    """
    Serializer for user login.
    Validates credentials and returns tokens.
    """
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True)

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if email and password:
            user = authenticate(request=self.context.get('request'),
                              username=email,
                              password=password)
            
            if not user:
                raise serializers.ValidationError('Invalid credentials')
            
            if not user.is_active:
                raise serializers.ValidationError('User account is disabled')
            
            attrs['user'] = user
            return attrs
        
        raise serializers.ValidationError('Both email and password are required')


class RegisterSerializer(serializers.ModelSerializer):
    """
    Serializer for user registration.
    Creates new user accounts with email and password.
    """
    password = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = User
        fields = ('email', 'first_name', 'last_name', 'password')

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError('A user with this email already exists.')
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class CustomPasswordResetConfirmSerializer(PasswordResetConfirmSerializer):
    new_password = serializers.CharField(write_only=True, required=True)
    
    # explicitly remove the dj-rest-auth fields
    new_password1 = None
    new_password2 = None

   
    def validate(self, attrs):
        # dj-rest-auth's validate() needs new_password1 and new_password2 to set self.user
        # Inject new_password as both so the parent can do its uid/token validation
        # without having to rewrite the logic
        attrs['new_password1'] = attrs['new_password']
        attrs['new_password2'] = attrs['new_password']
        super().validate(attrs)

        # Now run our own password validation
        validate_password(attrs['new_password'])
        return attrs

    def save(self):
        self.user.set_password(self.validated_data['new_password'])
        self.user.save()
        return self.user