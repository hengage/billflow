from rest_framework import status
from .responses import APIResponse


def success(data=None, message="Success"):
    return APIResponse(
        data=data,
        message=message,
        status=status.HTTP_200_OK
    )


def created(data=None, message="Created"):
    return APIResponse(
        data=data,
        message=message,
        status=status.HTTP_201_CREATED
    )


def fail(message="Error", error=None, status_code=400):
    return APIResponse(
        message=message,
        error=error,
        status=status_code
    )
