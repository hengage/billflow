from django.http import JsonResponse
from .responses import build_envelope


def handler400(request, exception):
    return JsonResponse(
        build_envelope(
            data=None,
            message="Bad request.",
            error={"detail": str(exception)},
            url=request.path,
        ),
        status=400,
    )


def handler403(request, exception):
    return JsonResponse(
        build_envelope(
            data=None,
            message="You do not have permission to perform this action.",
            error={"detail": str(exception)},
            url=request.path,
        ),
        status=403,
    )


def handler404(request, exception):
    return JsonResponse(
        build_envelope(
            data=None,
            message="The requested resource does not exist.",
            error={"detail": f"Not found: {request.path}"},
            url=request.path,
        ),
        status=404,
    )


def handler500(request):
    return JsonResponse(
        build_envelope(
            data=None,
            message="An unexpected server error occurred.",
            error={"detail": "Internal server error."},
            url=request.path,
        ),
        status=500,
    )

__all__ = [
    'handler400',
    'handler403',
    'handler404',
    'handler500',
]