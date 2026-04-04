from rest_framework import serializers


def create_success_envelope(data_serializer_class):
    """
    Factory that creates a success envelope serializer class.
    Usage: create_success_envelope(PaymentInitiateResponseSerializer)
    """
    class SuccessEnvelopeSerializer(serializers.Serializer):
        status = serializers.BooleanField(default=True)
        message = serializers.CharField()
        data = data_serializer_class()
        error = serializers.CharField(allow_null=True, default=None)
        url = serializers.CharField()

    return SuccessEnvelopeSerializer


def create_error_envelope(error_serializer_class=None):
    """
    Factory that creates an error envelope serializer class.
    Usage: create_error_envelope() or create_error_envelope(ValidationErrorSerializer)
    """
    class ErrorEnvelopeSerializer(serializers.Serializer):
        status = serializers.BooleanField(default=False)
        message = serializers.CharField()
        data = serializers.CharField(allow_null=True, default=None)
        error = (error_serializer_class() if error_serializer_class 
                 else serializers.DictField())
        url = serializers.CharField()

    return ErrorEnvelopeSerializer
